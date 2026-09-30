"""
API surface:
  POST /analyze        upload a .eml or .msg file, get back the parsed report
  GET  /analyses        list past analyses (history view)
  GET  /analyses/{id}    full detail for one past analysis
"""
import tempfile
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # picks up ABUSECH_AUTH_KEY from a .env file in the project root

from fastapi import FastAPI, UploadFile, File, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import parser, threat_intel, phishguard_bridge
from .models import Base, Analysis, ExtractedUrl, ExtractedAttachment, ReceivedHop

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
print(f"Database schema ready ({engine.dialect.name}).")

app = FastAPI(title="Phishing Email Analyzer")

# Loosen for local dev with a separate React frontend; tighten before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://email-triage-xpk6.vercel.app/",
        "https://email-triage-19oh-chi.vercel.app/",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/analyze")
async def analyze_email(file: UploadFile = File(...)):
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
    ])

    db = SessionLocal()
    try:
        analysis = Analysis(
            uploaded_filename=file.filename,
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
def list_analyses():
    db = SessionLocal()
    try:
        rows = db.query(Analysis).order_by(Analysis.upload_timestamp.desc()).all()
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
def get_analysis(analysis_id: int):
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).get(analysis_id)
        if not analysis:
            raise HTTPException(404, detail="Analysis not found")
        return _serialize_analysis(analysis)
    finally:
        db.close()


@app.get("/analyses/{analysis_id}/phishguard-report")
def get_phishguard_report(analysis_id: int):
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).get(analysis_id)
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


def _serialize_analysis(analysis: Analysis) -> dict:
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
             "urlhaus_host_flagged": u.urlhaus_host_flagged, "urlhaus_host_url_count": u.urlhaus_host_url_count}
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