"""
API surface:
  POST /analyze        upload a .eml or .msg file, get back the parsed report
  GET  /analyses        list past analyses (history view)
  GET  /analyses/{id}    full detail for one past analysis
"""
import tempfile
import os
import json
import base64
import binascii
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # picks up ABUSECH_AUTH_KEY from a .env file in the project root

from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import parser, threat_intel, phishguard_bridge, sandbox_bridge
from .models import Base, Analysis, ExtractedUrl, ExtractedAttachment, ReceivedHop, User
from .security import create_access_token, decode_access_token, hash_password, verify_password
import jwt

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL and os.getenv("RAILWAY_ENVIRONMENT"):
    raise RuntimeError("DATABASE_URL is missing. Link the Railway PostgreSQL DATABASE_URL to this service.")
DATABASE_URL = DATABASE_URL or "sqlite:///./analyzer.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite:"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
with engine.begin() as connection:
    analysis_columns = {column["name"] for column in inspect(engine).get_columns("analyses")}
    if "sandbox_results" not in analysis_columns:
        connection.execute(text("ALTER TABLE analyses ADD COLUMN sandbox_results TEXT"))
    if "owner_user_id" not in analysis_columns:
        connection.execute(text("ALTER TABLE analyses ADD COLUMN owner_user_id INTEGER REFERENCES users(id)"))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_analyses_owner_user_id ON analyses (owner_user_id)"
    ))
print(f"Database schema ready ({engine.dialect.name}).")

app = FastAPI(title="Phishing Email Analyzer")
bearer_scheme = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


@app.post("/auth/register")
def register(credentials: Credentials, db: Session = Depends(get_db)) -> dict:
    username = credentials.username.lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Username is already registered")

    user = User(username=username, password_hash=hash_password(credentials.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username is already registered")
    db.refresh(user)
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "username": user.username,
    }


@app.post("/auth/login")
def login(credentials: Credentials, db: Session = Depends(get_db)) -> dict:
    username = credentials.username.lower()
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "username": user.username,
    }

# Loosen for local dev with a separate React frontend; tighten before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://email-triage-xpk6.vercel.app",
        "https://email-triage-19oh-chi.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/analyze")
async def analyze_email(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    raw_bytes = await file.read()
    suffix = Path(file.filename).suffix.lower()

    if suffix == ".eml":
        parsed = parser.parse_eml(raw_bytes)
    elif suffix == ".msg":
        with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name
        parsed = parser.parse_msg(raw_bytes, tmp_path)
    else:
        raise HTTPException(400, detail="Only .eml and .msg files are supported")

    # Enrich with WHOIS/URLhaus/VirusTotal/AbuseIPDB/ipinfo.io before scoring, so those results count toward flag_count.
    parsed = await threat_intel.enrich(parsed, parser.domain_of, parser.domain_of_url)

    # Bridge to PhishGuard — use the single-scan API for one link and the batch
    # API for multiple links, returning the corresponding PDF. This blocks the
    # request while scanning, so a slow/unreachable PhishGuard instance
    # delays the triage report rather than silently skipping it — but it never
    # raises, so a PhishGuard outage doesn't break email triage itself.
    all_urls = [u["actual_href"] for u in parsed["urls"] if u.get("actual_href")]
    phishguard_result = await phishguard_bridge.get_phishguard_pdf_report(all_urls)
    sandbox_results = await sandbox_bridge.scan_extracted_urls(parsed["urls"])

    flag_count = sum([
        parsed["from_reply_to_mismatch"],
        parsed["from_return_path_mismatch"],
        parsed["spf_result"] == "fail",
        parsed["dkim_result"] == "fail",
        any(u["anchor_href_mismatch"] for u in parsed["urls"]),
        any(a["extension_mismatch"] for a in parsed["attachments"]),
        any(u["urlhaus_flagged"] for u in parsed["urls"]),
        any(a["malwarebazaar_flagged"] for a in parsed["attachments"]),
        any(a["virustotal_flagged"] for a in parsed["attachments"]),
        parsed["sender_domain_age_days"] is not None and parsed["sender_domain_age_days"] < 30,
        parsed["ip_reputation_flagged"],
        any(result.get("risk_detected") for result in sandbox_results.values()),
    ])

    db = SessionLocal()
    try:
        analysis = Analysis(
            uploaded_filename=file.filename,
            owner_user_id=current_user.id,
            sender_from=parsed["sender_from"],
            sender_reply_to=parsed["sender_reply_to"],
            sender_return_path=parsed["sender_return_path"],
            from_reply_to_mismatch=parsed["from_reply_to_mismatch"],
            from_return_path_mismatch=parsed["from_return_path_mismatch"],
            spf_result=parsed["spf_result"],
            dkim_result=parsed["dkim_result"],
            dmarc_result=parsed["dmarc_result"],
            sender_domain_age_days=parsed["sender_domain_age_days"],
            sending_ip=parsed["sending_ip"],
            ip_reputation_flagged=parsed["ip_reputation_flagged"],
            ip_reputation_score=parsed["ip_reputation_score"],
            asn=parsed["asn"],
            geolocation=parsed["geolocation"],
            flag_count=flag_count,
            phishguard_status=phishguard_result["status"],
            phishguard_pdf=phishguard_result["pdf_bytes"],
            sandbox_results=json.dumps(sandbox_results),
        )
        db.add(analysis)
        db.flush()  # get analysis.id before adding children

        for u in parsed["urls"]:
            db.add(ExtractedUrl(analysis_id=analysis.id, **u))
        for a in parsed["attachments"]:
            db.add(ExtractedAttachment(analysis_id=analysis.id, **a))
        for h in parsed["received_hops"]:
            db.add(ReceivedHop(analysis_id=analysis.id, **h))

        db.commit()
        db.refresh(analysis)
        return _serialize_analysis(analysis)
    finally:
        db.close()


@app.get("/analyses")
def list_analyses(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        rows = db.query(Analysis).filter(
            Analysis.owner_user_id == current_user.id
        ).order_by(Analysis.upload_timestamp.desc()).all()
        return [
            {
                "id": r.id,
                "filename": r.uploaded_filename,
                "timestamp": r.upload_timestamp,
                "flag_count": r.flag_count,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(
            Analysis.id == analysis_id,
            Analysis.owner_user_id == current_user.id,
        ).first()
        if not analysis:
            raise HTTPException(404, detail="Analysis not found")
        return _serialize_analysis(analysis)
    finally:
        db.close()


@app.get("/analyses/{analysis_id}/phishguard-report")
def get_phishguard_report(analysis_id: int, current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(
            Analysis.id == analysis_id,
            Analysis.owner_user_id == current_user.id,
        ).first()
        if not analysis:
            raise HTTPException(404, detail="Analysis not found")
        if not analysis.phishguard_pdf:
            raise HTTPException(404, detail=f"No PhishGuard report available (status: {analysis.phishguard_status})")
        return Response(
            content=analysis.phishguard_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="phishguard-report-{analysis_id}.pdf"'},
        )
    finally:
        db.close()


@app.get("/analyses/{analysis_id}/sandbox-screenshot")
def get_sandbox_screenshot(
    analysis_id: int,
    url: str,
    download: bool = False,
    current_user: User = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(
            Analysis.id == analysis_id,
            Analysis.owner_user_id == current_user.id,
        ).first()
        if not analysis:
            raise HTTPException(404, detail="Analysis not found")

        sandbox_results = _load_sandbox_results(analysis)
        encoded_screenshot = sandbox_results.get(url, {}).get("screenshot_base64")
        if not encoded_screenshot:
            raise HTTPException(404, detail="No sandbox screenshot available for this URL")
        try:
            screenshot = base64.b64decode(encoded_screenshot, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(404, detail="Stored sandbox screenshot is invalid")

        disposition = "attachment" if download else "inline"
        return Response(
            content=screenshot,
            media_type="image/png",
            headers={"Content-Disposition": f'{disposition}; filename="sandbox-screenshot.png"'},
        )
    finally:
        db.close()


def _load_sandbox_results(analysis: Analysis) -> dict:
    try:
        return json.loads(analysis.sandbox_results or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _public_sandbox_result(result: dict | None) -> dict | None:
    if not result:
        return None
    return {key: value for key, value in result.items() if key != "screenshot_base64"}


def _serialize_analysis(analysis: Analysis) -> dict:
    sandbox_results = _load_sandbox_results(analysis)

    return {
        "id": analysis.id,
        "filename": analysis.uploaded_filename,
        "timestamp": analysis.upload_timestamp,
        "flag_count": analysis.flag_count,
        "sender_domain_age_days": analysis.sender_domain_age_days,
        "phishguard_status": analysis.phishguard_status,
        "phishguard_report_available": analysis.phishguard_pdf is not None,
        "routing": {
            "sending_ip": analysis.sending_ip,
            "ip_reputation_flagged": analysis.ip_reputation_flagged,
            "ip_reputation_score": analysis.ip_reputation_score,
            "asn": analysis.asn,
            "geolocation": analysis.geolocation,
        },
        "sender": {
            "from": analysis.sender_from,
            "reply_to": analysis.sender_reply_to,
            "return_path": analysis.sender_return_path,
            "from_reply_to_mismatch": analysis.from_reply_to_mismatch,
            "from_return_path_mismatch": analysis.from_return_path_mismatch,
        },
        "auth": {
            "spf": analysis.spf_result,
            "dkim": analysis.dkim_result,
            "dmarc": analysis.dmarc_result,
        },
        "urls": [
            {"anchor_text": u.anchor_text, "actual_href": u.actual_href,
             "mismatch": u.anchor_href_mismatch, "domain_age_days": u.domain_age_days,
             "urlhaus_flagged": u.urlhaus_flagged, "urlhaus_tags": u.urlhaus_tags,
             "urlhaus_host_flagged": u.urlhaus_host_flagged, "urlhaus_host_url_count": u.urlhaus_host_url_count,
             "sandbox": _public_sandbox_result(sandbox_results.get(u.actual_href))}
            for u in analysis.urls
        ],
        "attachments": [
            {"filename": a.filename, "detected_filetype": a.detected_filetype,
             "extension_mismatch": a.extension_mismatch, "sha256": a.sha256,
             "malwarebazaar_flagged": a.malwarebazaar_flagged, "malware_signature": a.malware_signature,
             "virustotal_flagged": a.virustotal_flagged, "virustotal_malicious_count": a.virustotal_malicious_count}
            for a in analysis.attachments
        ],
        "received_chain": [
            {"hop_order": h.hop_order, "from_host": h.from_host,
             "by_host": h.by_host, "timestamp": h.timestamp}
            for h in analysis.received_hops
        ],
    }