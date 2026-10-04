# Mail Triage + PhishGuard: AI Project Handoff

**Purpose:** Give another AI enough context to explain, debug, document, or continue work on the deployed email-analysis product without relying on prior chat history. This brief contains variable names only; never add secret values here.

## Product Summary

Mail Triage analyzes suspicious `.eml` and `.msg` email files. It extracts header/authentication information, sender and routing details, links, attachments, and threat-intelligence results, then saves an analysis record and displays a structured report. It sends extracted URLs to PhishGuard for URL scanning and a downloadable PDF report.

PhishGuard is a separate URL threat scanner. It combines URL features, K-means and SOM anomaly models, threat-intelligence lookups, domain/redirect/TLS signals, and optional Gemini/Ollama analysis. It has a CLI, a web admin page, and an HTTP API.

## Repositories

- Mail Triage: https://github.com/nirvana58/Email-Triage
- PhishGuard: https://github.com/nirvana58/phishgaurd

The projects are separate Git repositories and separate Railway services. Do not merge them into one service unless explicitly requested.

## Architecture and Deployment

### Mail Triage

- Landing page: static HTML/Tailwind in `landing/`; intended as its own Vercel project, root directory `landing`.
- Main UI: React/Vite in `frontend/`; Vercel project root directory `frontend`, build `npm run build`, output `dist`.
- API: FastAPI/SQLAlchemy in `app/`; Railway project root is the repository root.
- Railway config: root `railway.toml` selects Railpack and starts `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- PostgreSQL is selected through `DATABASE_URL`; SQLite (`./analyzer.db`) is the local-development fallback. Railway must provide a valid Postgres `DATABASE_URL`. `Base.metadata.create_all(engine)` creates the schema at API startup.
- API endpoints: `POST /analyze`, `GET /analyses`, `GET /analyses/{id}`, and `GET /analyses/{id}/phishguard-report`.

### PhishGuard

- FastAPI entry point: `server.main:app`; API routes are in `server/api.py`.
- Root `railpack.json` sets `uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}`.
- Main routes include `POST /scan`, `GET /scan/{id}`, `GET /scan/{id}/report`, `POST /batch`, `GET /batch/{id}`, and `GET /health`.
- The scanner worker generates a PDF for single scans and multi-format reports for batches.
- Storage is SQLite in `data.db`; this database is local-only in the repository and ignored by Git. If using Railway without a persistent volume, database history may not persist across replacement/redeploy.

## Frontend-to-API Wiring

`frontend/src/EmailAnalyzerApp.jsx` constructs API calls from `import.meta.env.VITE_API_URL`. It is a Vite build-time environment variable, not a runtime browser lookup. Local development leaves it empty and uses the Vite proxy in `frontend/vite.config.js` to `localhost:8000`.

Expected Vercel Production variable:

```text
VITE_API_URL=https://email-triage-production-46fb.up.railway.app
```

Include `https://`; do not include quotes or a trailing slash. Redeploy the Vercel frontend after changing it. The email API CORS allowlist currently contains localhost and the known Vercel production domains; if a Vercel domain changes, update the list without trailing slashes and redeploy the API.

**Previously observed issue:** The built frontend requested `/analyses` from the Vercel origin, then later requested `/email-triage-production-46fb.up.railway.app/analyses` as a relative path. Both observations indicate a missing or malformed `VITE_API_URL`. Recheck browser Network requests after deployment; the request must target the Railway HTTPS host.

## Mail Triage ↔ PhishGuard Integration

`app/phishguard_bridge.py` submits one extracted link to `/scan`, multiple links to `/batch`, polls for completion, and downloads the PDF. It sends `use_llm` based on `PHISHGUARD_USE_LLM`, which currently defaults to `true`; explicitly setting it to `false` opts out. It logs the request mode and stage-specific failures without logging scan URLs or API secrets.

Set these on the **Mail Triage API Railway service**:

```text
PHISHGUARD_BASE_URL=https://<PGuard-public-Railway-domain>
PHISHGUARD_USE_LLM=true
```

`PHISHGUARD_BASE_URL` must be the PGuard service root URL, not `localhost`, and should not end with `/scan`. The PGuard public domain was not confirmed in this brief; obtain it from its Railway service settings. Alternatively, use Railway private networking only if both services share a project/environment and the correct internal hostname/port is known.

## LLM Configuration: Two Different Features

Do not conflate scanner page-content analysis with report summaries:

1. **PGuard URL-content analysis:** `server/scanner.py` calls Gemini only when each scan request has `use_llm: true`. `core/llm_content_check.py` reads `LLM_PROVIDER` (default `gemini`), `GEMINI_API_KEY`, and `GEMINI_MODEL`.
2. **Gemini-written report summary:** `report/generator.py` only generates a summary when the scan result has `use_llm: true`. It selects `REPORT_LLM_PROVIDER`, falling back to `LLM_PROVIDER`, then `ollama`; it also needs `GEMINI_API_KEY` and a valid `GEMINI_MODEL`.

Set these on the **PGuard Railway service** (not only in local `.env`):

```text
LLM_PROVIDER=gemini
REPORT_LLM_PROVIDER=gemini
GEMINI_API_KEY=<store privately in Railway>
GEMINI_MODEL=<currently supported Gemini model ID>
```

Verify the selected model ID is currently available to the Google API key/account. Do not assume a model name from an old local `.env` or CLI menu still exists. `GEMINI_API_KEY` is read by both features. A missing/invalid key or model can make LLM output unavailable, but scanner LLM failure is designed to degrade without taking down the URL scan. A missing LLM summary does not necessarily mean PDF generation itself failed.

## Current State and Known Checks

- Both repositories were clean and synced with `origin/main` during the latest workspace check.
- Mail Triage latest observed commit: `2b83dbe` (`Enhance responsive design in EmailAnalyzerApp with media queries and grid layouts`).
- PhishGuard latest observed commit: `186147b` (`Add railpack configuration for deployment`).
- The email API Railway URL above responded to `GET /analyses` with saved rows during a browser check on 2026-10-02.
- A saved Mail Triage analysis (ID 11, checked earlier on 2026-10-02) had `phishguard_status: error` and `phishguard_report_available: false`. Later bridge logging and LLM-flag changes were pushed; check fresh Railway logs and create a new analysis before treating that old record as current.
- Latest checked UI mobile work is in the Mail Triage frontend. At 320/375/768/1440px, layout width checks passed with no horizontal overflow. Main responsive changes: compact top/history navigation on mobile, full-width workspace/dropzone, stacked report finding panels, and status-row action reflow.
- Latest checked landing page responsive work is in `landing/index.html` and `landing/input.css`; `npm run build` passed and browser checks showed no horizontal overflow at 320/375/768/1440px.
- A local frontend preview may show 502s for `/analyses` if the local Mail Triage API is not running; this is separate from the deployed API.

## Security and Data Handling

- Never commit `.env`, API keys, Discord tokens/webhooks, database files, or credentials. Both repositories have `.gitignore` rules for local env files and data.
- Credentials from local `.env` files were pasted into chat during setup and must be considered exposed. Revoke/rotate them with their providers; do not copy old values into Railway.
- Configure replacements as Railway service variables. Do not put secret keys in Vercel `VITE_*` variables: Vite embeds those values in browser-delivered JavaScript.
- `VITE_API_URL` is a public service URL, not a credential.

## Suggested Debugging Order

1. Check the Vercel browser Network request for `/analyses`; confirm it targets the Railway HTTPS URL and returns JSON.
2. Check the Mail Triage Railway API logs for `Database schema ready (postgresql).` and confirm Postgres authentication succeeds.
3. Check the Mail Triage service’s `PHISHGUARD_BASE_URL` points to the deployed PGuard service, not localhost.
4. Check Mail Triage API logs for `Submitting N PhishGuard scan(s); use_llm=True` followed by a specific submit, polling, timeout, or PDF-download warning.
5. Check PGuard Railway logs for scan status and Gemini/API errors. Confirm the scan result has `use_llm: true` and inspect `content_analysis.available` / `content_analysis.reason` if available.
6. For missing report summaries, verify `REPORT_LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, and a supported `GEMINI_MODEL` on the PGuard Railway service.
7. Use a newly uploaded email/scan for verification; old records retain their original PhishGuard status and PDF.

## Prompt for the Next AI

```text
You are helping continue the Mail Triage + PhishGuard project. Read this brief first. Inspect the current repository state before editing, preserve local changes, never expose or request secret values, and distinguish the email frontend, email API, PGuard scan-content LLM, and PGuard report-summary LLM. Diagnose from current browser/network evidence and Railway logs rather than assuming old failures persist. Make the smallest targeted code/config change, run a focused build/test, and state clearly whether a step requires Railway/Vercel dashboard configuration or redeployment.
```
