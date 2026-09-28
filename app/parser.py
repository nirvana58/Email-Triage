"""
Parses .eml and .msg files into a plain dict of the signals analysts care
about. Never returns the email body text itself — only structural/metadata
findings (headers, links, attachment fingerprints).
"""
import email
import hashlib
import ipaddress
import re
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import urlparse

import tldextract

# Minimal magic-byte signatures so we don't need libmagic installed.
# (filetype, signature bytes at offset 0)
FILE_SIGNATURES = {
    b"\x4D\x5A": "exe/dll (PE)",
    b"\x25\x50\x44\x46": "pdf",
    b"\x50\x4B\x03\x04": "zip/docx/xlsx/pptx",
    b"\xD0\xCF\x11\xE0": "ole (doc/xls/msg)",
    b"\xFF\xD8\xFF": "jpg",
    b"\x89\x50\x4E\x47": "png",
}


def detect_filetype(data: bytes) -> str:
    for sig, filetype in FILE_SIGNATURES.items():
        if data.startswith(sig):
            return filetype
    return "unknown"


def domain_of(address: str) -> str:
    _, addr = parseaddr(address or "")
    return addr.split("@")[-1].lower() if "@" in addr else ""


def parse_auth_results(header_value: str) -> dict:
    """Pulls spf/dkim/dmarc verdicts out of an Authentication-Results header."""
    result = {"spf": None, "dkim": None, "dmarc": None}
    if not header_value:
        return result
    for mechanism in ("spf", "dkim", "dmarc"):
        match = re.search(rf"{mechanism}=(\w+)", header_value, re.IGNORECASE)
        if match:
            result[mechanism] = match.group(1).lower()
    return result


def extract_urls_from_html(html_body: str) -> list[dict]:
    """Finds <a href="..">anchor text</a> pairs and flags anchor/href mismatches."""
    findings = []
    for match in re.finditer(
        r'<a[^>]+href=["\'](.*?)["\'][^>]*>(.*?)</a>', html_body or "", re.IGNORECASE | re.DOTALL
    ):
        href, anchor_text = match.group(1).strip(), re.sub(r"<[^>]+>", "", match.group(2)).strip()
        anchor_looks_like_url = re.match(r"https?://", anchor_text, re.IGNORECASE)
        mismatch = bool(anchor_looks_like_url) and domain_of_url(anchor_text) != domain_of_url(href)
        findings.append({
            "anchor_text": anchor_text,
            "actual_href": href,
            "anchor_href_mismatch": mismatch,
        })
    return findings


def domain_of_url(url: str) -> str:
    try:
        ext = tldextract.extract(url)
        return f"{ext.domain}.{ext.suffix}".lower()
    except Exception:
        return urlparse(url).netloc.lower()


def parse_received_chain(msg) -> list[dict]:
    hops = []
    for i, header in enumerate(msg.get_all("Received", [])):
        from_match = re.search(r"from\s+(\S+)", header)
        by_match = re.search(r"by\s+(\S+)", header)
        date_match = re.search(r";\s*(.+)$", header)
        timestamp = None
        if date_match:
            try:
                timestamp = parsedate_to_datetime(date_match.group(1).strip())
            except Exception:
                pass
        hops.append({
            "hop_order": i,
            "from_host": from_match.group(1) if from_match else None,
            "by_host": by_match.group(1) if by_match else None,
            "timestamp": timestamp,
        })
    return hops


IP_PATTERN = re.compile(r"\[?(\d{1,3}(?:\.\d{1,3}){3})\]?")


def _is_private_ip(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_private
    except ValueError:
        return True  # unparseable — treat as not-useful rather than crash


def extract_sending_ip(msg) -> str | None:
    """
    Walks the Received chain from oldest to newest hop, looking for the first
    public IP — that's typically the originating sender's mail server, since
    each hop prepends a new Received header (so the raw header order is
    newest-first; the oldest, and usually most revealing, hop is last).
    Falls back to any IP found if every hop looks private (common in internal
    test setups), and to None if the chain has no IPs at all.
    """
    received_headers = msg.get_all("Received", [])
    all_ips = []
    for header in reversed(received_headers):
        match = IP_PATTERN.search(header)
        if match:
            ip = match.group(1)
            all_ips.append(ip)
            if not _is_private_ip(ip):
                return ip
    return all_ips[0] if all_ips else None


def parse_eml(raw_bytes: bytes) -> dict:
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)

    from_addr = msg.get("From", "")
    reply_to = msg.get("Reply-To", "")
    return_path = msg.get("Return-Path", "")

    auth = parse_auth_results(msg.get("Authentication-Results", ""))

    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_body = part.get_content()
                break
    elif msg.get_content_type() == "text/html":
        html_body = msg.get_content()

    attachments = []
    for part in msg.iter_attachments():
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename() or "unnamed"
        detected = detect_filetype(payload)
        declared_ext = filename.split(".")[-1].lower() if "." in filename else ""
        extension_mismatch = _extension_looks_spoofed(filename, detected)
        attachments.append({
            "filename": filename,
            "declared_mime": part.get_content_type(),
            "detected_filetype": detected,
            "extension_mismatch": extension_mismatch,
            "sha256": hashlib.sha256(payload).hexdigest() if payload else None,
        })

    return {
        "sender_from": from_addr,
        "sender_reply_to": reply_to,
        "sender_return_path": return_path,
        "from_reply_to_mismatch": bool(reply_to) and domain_of(from_addr) != domain_of(reply_to),
        "from_return_path_mismatch": bool(return_path) and domain_of(from_addr) != domain_of(return_path),
        "spf_result": auth["spf"],
        "dkim_result": auth["dkim"],
        "dmarc_result": auth["dmarc"],
        "urls": extract_urls_from_html(html_body),
        "attachments": attachments,
        "received_hops": parse_received_chain(msg),
        "sending_ip": extract_sending_ip(msg),
    }


def parse_msg(raw_bytes: bytes, tmp_path: str) -> dict:
    """.msg (Outlook binary format) needs a separate parser since it isn't MIME."""
    import extract_msg

    m = extract_msg.Message(tmp_path)
    from_addr = m.sender or ""
    reply_to = getattr(m, "replyTo", "") or ""

    attachments = []
    for att in m.attachments:
        data = att.data or b""
        filename = att.longFilename or att.shortFilename or "unnamed"
        detected = detect_filetype(data)
        attachments.append({
            "filename": filename,
            "declared_mime": None,
            "detected_filetype": detected,
            "extension_mismatch": _extension_looks_spoofed(filename, detected),
            "sha256": hashlib.sha256(data).hexdigest() if data else None,
        })

    return {
        "sender_from": from_addr,
        "sender_reply_to": reply_to,
        "sender_return_path": None,
        "from_reply_to_mismatch": bool(reply_to) and domain_of(from_addr) != domain_of(reply_to),
        "from_return_path_mismatch": False,
        "spf_result": None,   # .msg files rarely retain raw auth headers — flag as unavailable
        "dkim_result": None,
        "dmarc_result": None,
        "urls": extract_urls_from_html(m.htmlBody.decode("utf-8", "ignore") if m.htmlBody else ""),
        "attachments": attachments,
        "received_hops": [],
        "sending_ip": None,  # .msg files typically strip Received headers entirely
    }


def _extension_looks_spoofed(filename: str, detected_filetype: str) -> bool:
    """e.g. invoice.pdf.exe, or a .pdf that's actually a PE executable."""
    lowered = filename.lower()
    if lowered.endswith((".exe", ".scr", ".bat", ".js", ".vbs")) and "." in lowered[:-4]:
        return True  # double extension trick
    if lowered.endswith(".pdf") and detected_filetype == "exe/dll (PE)":
        return True
    return False
