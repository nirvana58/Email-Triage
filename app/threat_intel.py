"""
Threat intelligence enrichment — WHOIS (domain age), URLhaus (malicious URL
lookup), MalwareBazaar + VirusTotal (malware hash lookup on attachments),
AbuseIPDB (sending IP reputation), and ipinfo.io (ASN/geolocation).

URLhaus and MalwareBazaar require a free Auth-Key from https://auth.abuse.ch/.
VirusTotal and AbuseIPDB each require their own free API key (virustotal.com,
abuseipdb.com). ipinfo.io works without a token on a limited free tier, or
with one for higher limits. All are read from environment variables — see
.env.example.

VirusTotal is used for file/attachment hashes only, not URLs. A URL lookup
there is read-only (GET, not submit + poll), so a URL VirusTotal has never
scanned before returns "unknown," not "clean" — freshly-registered phishing
domains are exactly the case most likely to be missing, making the check low
value for this use case. URLhaus covers the URL side instead.

All lookups are best-effort: a failed, timed-out, or unauthenticated (missing
key) lookup returns a "not flagged / unknown" result rather than raising, so
one slow or unconfigured service never breaks the whole /analyze request.
"""
import asyncio
import os
from datetime import datetime, timezone

import httpx
import whois

ABUSECH_AUTH_KEY = os.environ.get("ABUSECH_AUTH_KEY", "")
VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", "")
ABUSEIPDB_API_KEY = os.environ.get("ABUSEIPDB_API_KEY", "")
IPINFO_TOKEN = os.environ.get("IPINFO_TOKEN", "")

URLHAUS_URL_ENDPOINT = "https://urlhaus-api.abuse.ch/v1/url/"
URLHAUS_HOST_ENDPOINT = "https://urlhaus-api.abuse.ch/v1/host/"
MALWAREBAZAAR_ENDPOINT = "https://mb-api.abuse.ch/api/v1/"
VT_FILE_ENDPOINT = "https://www.virustotal.com/api/v3/files/{}"
ABUSEIPDB_ENDPOINT = "https://api.abuseipdb.com/api/v2/check"
IPINFO_ENDPOINT = "https://ipinfo.io/{}/json"
REQUEST_TIMEOUT = 8.0
ABUSEIPDB_FLAG_THRESHOLD = 25  # abuseConfidenceScore (0-100); 25+ is a common "worth a look" cutoff, not a hard rule


def _get_domain_age_days_sync(domain: str) -> int | None:
    """Blocking WHOIS lookup — always run through asyncio.to_thread, never called directly from async code."""
    if not domain:
        return None
    try:
        record = whois.whois(domain)
        creation = record.creation_date
        if isinstance(creation, list):
            creation = creation[0]
        if not creation:
            return None
        if creation.tzinfo is None:
            creation = creation.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - creation).days
    except Exception:
        return None


async def get_domain_age_days(domain: str) -> int | None:
    return await asyncio.to_thread(_get_domain_age_days_sync, domain)


async def check_url_urlhaus(url: str, client: httpx.AsyncClient) -> dict:
    """Exact-URL match — the strongest possible signal, but low recall: URLhaus
    requires the full URL (path, query string, everything) to match byte-for-byte
    against what someone else already submitted. A phishing link with a unique
    per-victim tracking param will miss this even if the domain is well known."""
    if not url or not ABUSECH_AUTH_KEY:
        return {"flagged": False, "threat": None, "tags": [], "url_status": None, "date_added": None}
    try:
        resp = await client.post(
            URLHAUS_URL_ENDPOINT,
            data={"url": url},
            headers={"Auth-Key": ABUSECH_AUTH_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        if data.get("query_status") == "ok":
            return {
                "flagged": True,
                "threat": data.get("threat"),
                "tags": data.get("tags") or [],
                "url_status": data.get("url_status"),
                "date_added": data.get("date_added"),
            }
        return {"flagged": False, "threat": None, "tags": [], "url_status": None, "date_added": None}
    except Exception:
        return {"flagged": False, "threat": None, "tags": [], "url_status": None, "date_added": None}


async def check_host_urlhaus(host: str, client: httpx.AsyncClient) -> dict:
    """Host-level match — much higher recall than the exact-URL check, since it
    asks 'has this domain/IP ever hosted a known-malicious URL', not 'is this
    exact URL known'. Weaker signal on its own (a domain with past abuse history
    doesn't prove THIS message is malicious — could be a compromised legitimate
    site that's since been cleaned up), so this is surfaced separately from the
    exact-URL flag rather than merged into one boolean."""
    if not host or not ABUSECH_AUTH_KEY:
        return {"flagged": False, "url_count": 0, "blacklists": {}}
    try:
        resp = await client.post(
            URLHAUS_HOST_ENDPOINT,
            data={"host": host},
            headers={"Auth-Key": ABUSECH_AUTH_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        if data.get("query_status") == "ok":
            url_count = int(data.get("url_count") or 0)
            return {
                "flagged": url_count > 0,
                "url_count": url_count,
                "blacklists": data.get("blacklists") or {},
            }
        return {"flagged": False, "url_count": 0, "blacklists": {}}
    except Exception:
        return {"flagged": False, "url_count": 0, "blacklists": {}}


async def check_hash_malwarebazaar(sha256: str, client: httpx.AsyncClient) -> dict:
    if not sha256 or not ABUSECH_AUTH_KEY:
        return {"flagged": False, "signature": None}
    try:
        resp = await client.post(
            MALWAREBAZAAR_ENDPOINT,
            data={"query": "get_info", "hash": sha256},
            headers={"Auth-Key": ABUSECH_AUTH_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        if data.get("query_status") == "ok" and data.get("data"):
            info = data["data"][0]
            return {"flagged": True, "signature": info.get("signature")}
        return {"flagged": False, "signature": None}
    except Exception:
        return {"flagged": False, "signature": None}


async def check_file_virustotal(sha256: str, client: httpx.AsyncClient) -> dict:
    if not sha256 or not VIRUSTOTAL_API_KEY:
        return {"flagged": False, "malicious_count": None, "total_engines": None}
    try:
        resp = await client.get(
            VT_FILE_ENDPOINT.format(sha256),
            headers={"x-apikey": VIRUSTOTAL_API_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return {"flagged": False, "malicious_count": None, "total_engines": None}
        stats = resp.json()["data"]["attributes"]["last_analysis_stats"]
        malicious = stats.get("malicious", 0)
        return {"flagged": malicious > 0, "malicious_count": malicious, "total_engines": sum(stats.values())}
    except Exception:
        return {"flagged": False, "malicious_count": None, "total_engines": None}


async def check_ip_abuseipdb(ip: str, client: httpx.AsyncClient) -> dict:
    if not ip or not ABUSEIPDB_API_KEY:
        return {"flagged": False, "score": None}
    try:
        resp = await client.get(
            ABUSEIPDB_ENDPOINT,
            params={"ipAddress": ip, "maxAgeInDays": 90},
            headers={"Key": ABUSEIPDB_API_KEY, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        score = resp.json()["data"].get("abuseConfidenceScore", 0)
        return {"flagged": score >= ABUSEIPDB_FLAG_THRESHOLD, "score": score}
    except Exception:
        return {"flagged": False, "score": None}


async def get_ip_info(ip: str, client: httpx.AsyncClient) -> dict:
    if not ip:
        return {"asn": None, "geolocation": None}
    try:
        params = {"token": IPINFO_TOKEN} if IPINFO_TOKEN else {}
        resp = await client.get(IPINFO_ENDPOINT.format(ip), params=params, timeout=REQUEST_TIMEOUT)
        data = resp.json()
        org = data.get("org")  # e.g. "AS15169 Google LLC"
        asn = org.split(" ")[0] if org else None
        city, country = data.get("city"), data.get("country")
        geolocation = f"{city}, {country}" if city and country else country
        return {"asn": asn, "geolocation": geolocation}
    except Exception:
        return {"asn": None, "geolocation": None}


async def enrich(parsed: dict, domain_of, domain_of_url) -> dict:
    """
    Takes the dict returned by parser.parse_eml()/parse_msg(), runs every
    external lookup concurrently, and returns the same dict with the
    threat-intel fields populated. `domain_of` and `domain_of_url` are
    passed in from parser.py rather than imported, to avoid a circular import.
    """
    sender_domain = domain_of(parsed.get("sender_from", ""))
    sending_ip = parsed.get("sending_ip")
    urls = parsed.get("urls", [])
    attachments = parsed.get("attachments", [])

    async with httpx.AsyncClient() as client:
        sender_age_task = get_domain_age_days(sender_domain)
        ip_reputation_task = check_ip_abuseipdb(sending_ip, client)
        ip_info_task = get_ip_info(sending_ip, client)
        url_age_tasks = [get_domain_age_days(domain_of_url(u["actual_href"])) for u in urls]
        urlhaus_tasks = [check_url_urlhaus(u["actual_href"], client) for u in urls]
        urlhaus_host_tasks = [check_host_urlhaus(domain_of_url(u["actual_href"]), client) for u in urls]
        mb_tasks = [check_hash_malwarebazaar(a.get("sha256"), client) for a in attachments]
        vt_file_tasks = [check_file_virustotal(a.get("sha256"), client) for a in attachments]

        (sender_age, ip_rep, ip_info, url_ages, urlhaus_results, urlhaus_host_results,
         mb_results, vt_file_results) = await asyncio.gather(
            sender_age_task,
            ip_reputation_task,
            ip_info_task,
            asyncio.gather(*url_age_tasks) if url_age_tasks else _empty_list(),
            asyncio.gather(*urlhaus_tasks) if urlhaus_tasks else _empty_list(),
            asyncio.gather(*urlhaus_host_tasks) if urlhaus_host_tasks else _empty_list(),
            asyncio.gather(*mb_tasks) if mb_tasks else _empty_list(),
            asyncio.gather(*vt_file_tasks) if vt_file_tasks else _empty_list(),
        )

    parsed["sender_domain_age_days"] = sender_age
    parsed["ip_reputation_flagged"] = ip_rep["flagged"]
    parsed["ip_reputation_score"] = ip_rep["score"]
    parsed["asn"] = ip_info["asn"]
    parsed["geolocation"] = ip_info["geolocation"]

    for u, age, uh, uhh in zip(urls, url_ages, urlhaus_results, urlhaus_host_results):
        u["domain_age_days"] = age
        u["urlhaus_flagged"] = uh["flagged"]  # exact URL match — strong signal
        u["urlhaus_tags"] = ",".join(uh["tags"]) if uh["tags"] else None
        u["urlhaus_host_flagged"] = uhh["flagged"]  # domain has known-malicious history — contextual signal
        u["urlhaus_host_url_count"] = uhh["url_count"]

    for a, mb, vt in zip(attachments, mb_results, vt_file_results):
        a["malwarebazaar_flagged"] = mb["flagged"]
        a["malware_signature"] = mb["signature"]
        a["virustotal_flagged"] = vt["flagged"]
        a["virustotal_malicious_count"] = vt["malicious_count"]

    return parsed


async def _empty_list():
    return []