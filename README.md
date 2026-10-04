# Mail Triage + PhishGuard

Mail Triage is an email analysis tool that helps security teams triage suspicious messages quickly. Upload a `.eml` or `.msg` file and it parses headers, checks authentication results, enriches sender/routing data with threat intelligence, extracts links and attachments, and — via a bridge to the companion **PhishGuard** service — runs deeper URL and domain analysis, returning a combined PDF report.

Instead of manually reading raw headers and checking every link by hand, the system automates:

- Parsing inbound email metadata and headers (`.eml` / `.msg`)
- SPF, DKIM, and DMARC verification
- Sender-domain age (WHOIS) and routing/IP reputation checks
- URL extraction with anchor-text-vs-destination mismatch detection
- Attachment extraction with extension-spoofing detection
- Threat-intel enrichment (WHOIS, URLhaus, MalwareBazaar, VirusTotal, AbuseIPDB, ipinfo.io)
- Submission of extracted URLs to PhishGuard for deeper scanning, with the resulting PDF report returned to the analyst

## Architecture

Two-service design, connected by a bridge layer:

- **Mail Triage** — handles email parsing, header analysis, and threat-intel enrichment. This repo.
- **PhishGuard** — a separate scanner service providing URL/domain anomaly scoring, VirusTotal/Safe Browsing lookups, redirect-chain analysis, WHOIS/TLS evaluation, brand-impersonation detection, and optional LLM-based content review.
- **Bridge** — submits extracted URLs from an email to PhishGuard, waits for the scan to complete, and stores the resulting PDF alongside the email's analysis record. A PhishGuard outage degrades to a status flag rather than breaking email triage.

### Repo structure

```
├── landing/      Static marketing/landing page
├── frontend/     React + Vite UI for uploading and reviewing emails
└── app/          FastAPI backend — API, models, parsing, threat-intel, PhishGuard bridge
```

### Deployment model

- **Backend**: FastAPI, deployed as a Railway service. SQLite locally; PostgreSQL in production.
- **Frontend**: React/Vite, deployed on Vercel.
- **PhishGuard**: separate service with its own API (scan submission, status polling, report retrieval).

## Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `PHISHGUARD_BASE_URL` | Backend | Must point to PhishGuard's live service root — not `localhost`, and not a partial path like `/scan` appended incorrectly. Integration is sensitive to base URL format and trailing slashes. |
| `SANDBOX_SERVICE_URL` | Backend | Root URL of the Render-hosted sandbox service. When set with `SANDBOX_API_TOKEN`, extracted HTTP(S) links are detonated and findings are stored with the analysis. |
| `SANDBOX_API_TOKEN` | Backend | Bearer token configured on the sandbox service. Keep it in Railway's backend environment settings, never in the Vercel frontend. |
| `SANDBOX_MAX_URLS` | Backend | Maximum unique HTTP(S) links submitted per email (default: `3`). |
| `SANDBOX_REQUEST_TIMEOUT` | Backend | Per-request timeout in seconds (default: `180`). |
| `LLM_PROVIDER`, `GEMINI_API_KEY` | PhishGuard (URL-content analysis) | Optional AI-based content review during scanning |
| `REPORT_LLM_PROVIDER`, `LLM_PROVIDER`, `GEMINI_MODEL` | PhishGuard (report generation) | Separate LLM config for report summarization — distinct from the scanning flow above; don't conflate the two |
| `VITE_API_URL` | Frontend (build-time) | Public API host the deployed frontend calls. If missing/malformed, requests silently go to the wrong host or a broken relative path. |
| Postgres connection vars | Backend | Production database linkage on Railway |

> **Note:** AI enrichment can fail silently if the wrong key/model is configured while the underlying scan still succeeds — check logs, not just scan success, when verifying LLM features.

## Local development

```bash
# Backend
cd app
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Landing page
cd landing
npm install
npm run build
```

## Verifying a deployment

When debugging connectivity issues, check in this order (chasing symptoms out of order tends to point at the wrong cause):

1. Frontend is requesting the correct Railway API host (`VITE_API_URL`)
2. Backend is connected to the correct Postgres database
3. `PHISHGUARD_BASE_URL` points to the live PhishGuard service root
4. Submit a **fresh** email and confirm both status polling and PDF download succeed
5. Check PhishGuard logs for scan status/API failures
6. Confirm LLM env vars and model IDs are current
7. Base conclusions only on fresh results — older records may carry stale `phishguard_status` values from before a config fix

## Known operational notes

This project's core pipeline is complete and modular; most of its risk surface is deployment configuration rather than missing functionality:

- The Mail Triage ↔ PhishGuard integration is synchronous from the analyst's point of view — the backend waits for PhishGuard before finalizing a stored analysis, so a slow/unreachable PhishGuard instance delays (not corrupts) the result.
- Service-to-service URL misconfiguration (wrong host, wrong path, trailing slash handling) is the most common source of integration failures.
- Two independent LLM configuration surfaces exist (scan-time content analysis vs. report summarization) — verify both separately if AI features seem inconsistent.

## Roadmap

**Near-term:** startup-time validation for required service URLs/secrets, clearer service-failure logging, better UI messaging when PhishGuard is unavailable.

**Medium-term:** health-check/readiness endpoints across both services, retry logic for external API calls, a unified service-health dashboard.

**Long-term:** higher-volume triage support, analyst workflow features (review, escalation, evidence export), improved detection quality across phishing campaigns.
