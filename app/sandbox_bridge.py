"""Bridge extracted email links to the remote PhishGuard URL sandbox."""

import asyncio
import logging
import os
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

SANDBOX_SERVICE_URL = os.environ.get("SANDBOX_SERVICE_URL", "").rstrip("/")
SANDBOX_API_TOKEN = os.environ.get("SANDBOX_API_TOKEN", "")
SANDBOX_MAX_URLS = max(1, int(os.environ.get("SANDBOX_MAX_URLS", "3")))
SANDBOX_REQUEST_TIMEOUT = float(os.environ.get("SANDBOX_REQUEST_TIMEOUT", "180"))


def _risk_signals(result: dict) -> list[str]:
    signals = []
    if result.get("has_cross_origin_password_form"):
        signals.append("Password form submits to another domain")
    if result.get("download_attempted"):
        filename = result.get("download_filename") or "unknown file"
        signals.append(f"Page attempted a download ({filename})")
    if result.get("brand_domain_mismatch"):
        brands = ", ".join(result.get("brand_keywords_found", []))
        signals.append(f"Page impersonates a brand ({brands}) on an unrelated domain")
    if result.get("num_iframes", 0) >= 3 or result.get("num_external_scripts", 0) >= 5:
        signals.append("Page has an unusually large iframe or external-script surface")
    return signals


def _summarize_result(result: dict) -> dict:
    available = bool(result.get("available"))
    summary = {
        "status": "complete" if available else "unavailable",
        "available": available,
        "risk_signals": _risk_signals(result) if available else [],
        "risk_detected": bool(available and _risk_signals(result)),
    }
    for key in (
        "final_url",
        "title",
        "load_time_ms",
        "num_forms",
        "num_password_fields",
        "has_cross_origin_password_form",
        "num_iframes",
        "num_external_scripts",
        "download_attempted",
        "download_filename",
        "brand_keywords_found",
        "brand_domain_mismatch",
        "screenshot_available",
    ):
        if key in result:
            summary[key] = result[key]
    reason = result.get("reason") or result.get("error")
    if reason:
        summary["reason"] = str(reason)[:500]
    return summary


async def scan_extracted_urls(urls: list[dict]) -> dict[str, dict]:
    """Scan at most the configured number of unique HTTP(S) links."""
    if not urls:
        return {}

    if not SANDBOX_SERVICE_URL or not SANDBOX_API_TOKEN:
        logger.info("Remote URL sandbox is not configured; skipping sandbox scans")
        return {}

    unique_urls = list(dict.fromkeys(
        item.get("actual_href", "").strip()
        for item in urls
        if isinstance(item.get("actual_href"), str) and item["actual_href"].strip()
    ))
    results = {}
    candidates = []
    for url in unique_urls:
        if urlparse(url).scheme.lower() not in {"http", "https"}:
            results[url] = {
                "status": "skipped",
                "available": False,
                "risk_detected": False,
                "risk_signals": [],
                "reason": "Only HTTP(S) links can be detonated",
            }
        elif len(candidates) < SANDBOX_MAX_URLS:
            candidates.append(url)
        else:
            results[url] = {
                "status": "skipped",
                "available": False,
                "risk_detected": False,
                "risk_signals": [],
                "reason": f"Per-email limit reached ({SANDBOX_MAX_URLS} links)",
            }

    timeout = httpx.Timeout(SANDBOX_REQUEST_TIMEOUT)
    headers = {"Authorization": f"Bearer {SANDBOX_API_TOKEN}"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        async def scan_one(url: str) -> tuple[str, dict]:
            try:
                response = await client.post(
                    f"{SANDBOX_SERVICE_URL}/detonate",
                    json={"url": url},
                )
                response.raise_for_status()
                return url, _summarize_result(response.json())
            except Exception as error:
                logger.warning("Remote sandbox request failed for an extracted URL: %s", error)
                return url, {
                    "status": "unavailable",
                    "available": False,
                    "risk_detected": False,
                    "risk_signals": [],
                    "reason": str(error)[:500],
                }

        scanned = await asyncio.gather(*(scan_one(url) for url in candidates))
    results.update(scanned)
    return results
