"""Bridge email analysis to PhishGuard's asynchronous scan APIs."""
import asyncio
import os

import httpx

PHISHGUARD_BASE_URL = os.environ.get("PHISHGUARD_BASE_URL", "http://localhost:8001").rstrip("/")
PHISHGUARD_SCAN_PATH = "/scan"
PHISHGUARD_BATCH_PATH = "/batch"
PHISHGUARD_TIMEOUT = float(os.environ.get("PHISHGUARD_TIMEOUT", "300"))
PHISHGUARD_POLL_INTERVAL = float(os.environ.get("PHISHGUARD_POLL_INTERVAL", "1"))
PHISHGUARD_REQUEST_TIMEOUT = 15.0


async def get_phishguard_pdf_report(urls: list[str]) -> dict:
    """
    Uses the single-scan API for one URL and the batch API for multiple URLs,
    then polls for completion and downloads the generated PDF report.

    Returns {"status": "success", "pdf_bytes": <bytes>} on success,
    or {"status": "no_urls" | "unreachable" | "error", "pdf_bytes": None}
    on anything else — never raises, so a PhishGuard outage doesn't break
    email triage itself.
    """
    if not urls:
        return {"status": "no_urls", "pdf_bytes": None}

    urls = list(dict.fromkeys(url.strip() for url in urls if url and url.strip()))
    if not urls:
        return {"status": "no_urls", "pdf_bytes": None}

    deadline = asyncio.get_running_loop().time() + PHISHGUARD_TIMEOUT
    is_single_scan = len(urls) == 1
    submit_path = PHISHGUARD_SCAN_PATH if is_single_scan else PHISHGUARD_BATCH_PATH
    submit_payload = {"url": urls[0]} if is_single_scan else {"urls": urls}
    id_key = "scan_id" if is_single_scan else "batch_id"

    try:
        async with httpx.AsyncClient(timeout=PHISHGUARD_REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{PHISHGUARD_BASE_URL}{submit_path}",
                json=submit_payload,
            )
            if response.status_code != 200:
                return {"status": "error", "pdf_bytes": None}

            job_id = response.json().get(id_key)
            if not job_id:
                return {"status": "error", "pdf_bytes": None}

            status_url = f"{PHISHGUARD_BASE_URL}{submit_path}/{job_id}"
            while asyncio.get_running_loop().time() < deadline:
                status_response = await client.get(status_url)
                if status_response.status_code != 200:
                    return {"status": "error", "pdf_bytes": None}

                batch_status = status_response.json().get("status")
                if batch_status in {"failed", "cancelled"}:
                    return {"status": "error", "pdf_bytes": None}
                if batch_status == "completed":
                    break

                await asyncio.sleep(min(
                    PHISHGUARD_POLL_INTERVAL,
                    max(0, deadline - asyncio.get_running_loop().time()),
                ))
            else:
                return {"status": "error", "pdf_bytes": None}

            report_url = f"{status_url}/report"
            while asyncio.get_running_loop().time() < deadline:
                report_response = await client.get(report_url, params={"fmt": "pdf"})
                if report_response.status_code == 200:
                    pdf_bytes = report_response.content
                    if pdf_bytes.startswith(b"%PDF-"):
                        return {"status": "success", "pdf_bytes": pdf_bytes}
                    return {"status": "error", "pdf_bytes": None}
                if report_response.status_code != 404:
                    return {"status": "error", "pdf_bytes": None}

                await asyncio.sleep(min(
                    PHISHGUARD_POLL_INTERVAL,
                    max(0, deadline - asyncio.get_running_loop().time()),
                ))

        return {"status": "error", "pdf_bytes": None}
    except httpx.ConnectError:
        return {"status": "unreachable", "pdf_bytes": None}
    except Exception:
        return {"status": "error", "pdf_bytes": None}
