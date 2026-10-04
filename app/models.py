"""
SQLAlchemy models for the phishing email analyzer.
Mirrors the schema sketched during design: one analysis row per uploaded
email, with related findings (urls, attachments, received hops) stored
in child tables so a single email can have many of each.
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, LargeBinary
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(32), nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    analyses = relationship("Analysis", back_populates="owner")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    uploaded_filename = Column(String, nullable=False)
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    analyst_note = Column(Text, nullable=True)

    # Sender identity
    sender_from = Column(String, nullable=True)
    sender_reply_to = Column(String, nullable=True)
    sender_return_path = Column(String, nullable=True)
    from_reply_to_mismatch = Column(Boolean, default=False)
    from_return_path_mismatch = Column(Boolean, default=False)

    # Authentication
    spf_result = Column(String, nullable=True)      # pass / fail / softfail / none
    dkim_result = Column(String, nullable=True)
    dmarc_result = Column(String, nullable=True)

    # Routing / sending IP
    sending_ip = Column(String, nullable=True)
    ip_reputation_flagged = Column(Boolean, default=False)
    ip_reputation_score = Column(Integer, nullable=True)   # AbuseIPDB abuseConfidenceScore, 0-100
    asn = Column(String, nullable=True)
    geolocation = Column(String, nullable=True)

    # Rollup — count of flags raised, NOT a confidence score
    flag_count = Column(Integer, default=0)

    # Threat intel — sender domain age via WHOIS
    sender_domain_age_days = Column(Integer, nullable=True)

    # PhishGuard bridge — PDF report covering every link found in this email
    phishguard_status = Column(String, nullable=True)     # success / no_urls / unreachable / error
    phishguard_pdf = Column(LargeBinary, nullable=True)
    sandbox_results = Column(Text, nullable=True)         # JSON map of URL to remote browser findings

    urls = relationship("ExtractedUrl", back_populates="analysis", cascade="all, delete-orphan")
    attachments = relationship("ExtractedAttachment", back_populates="analysis", cascade="all, delete-orphan")
    received_hops = relationship("ReceivedHop", back_populates="analysis", cascade="all, delete-orphan")
    owner = relationship("User", back_populates="analyses")


class ExtractedUrl(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"))

    anchor_text = Column(String, nullable=True)
    actual_href = Column(String, nullable=True)
    final_destination = Column(String, nullable=True)   # after following redirects
    anchor_href_mismatch = Column(Boolean, default=False)
    domain_age_days = Column(Integer, nullable=True)
    urlhaus_flagged = Column(Boolean, default=False)         # exact URL match — strong signal
    urlhaus_tags = Column(String, nullable=True)              # comma-joined malware family tags, when present
    urlhaus_host_flagged = Column(Boolean, default=False)      # domain has known-malicious history — contextual, weaker signal
    urlhaus_host_url_count = Column(Integer, nullable=True)    # how many malicious URLs URLhaus has seen from this host

    analysis = relationship("Analysis", back_populates="urls")


class ExtractedAttachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"))

    filename = Column(String, nullable=True)
    declared_mime = Column(String, nullable=True)
    detected_filetype = Column(String, nullable=True)   # from magic bytes
    extension_mismatch = Column(Boolean, default=False)
    sha256 = Column(String, nullable=True)
    malwarebazaar_flagged = Column(Boolean, default=False)
    malware_signature = Column(String, nullable=True)
    virustotal_flagged = Column(Boolean, default=False)
    virustotal_malicious_count = Column(Integer, nullable=True)

    analysis = relationship("Analysis", back_populates="attachments")


class ReceivedHop(Base):
    __tablename__ = "received_chain"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"))

    hop_order = Column(Integer, nullable=False)
    from_host = Column(String, nullable=True)
    by_host = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=True)

    analysis = relationship("Analysis", back_populates="received_hops")