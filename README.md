# Mail Triage + PhishGuard

https://github.com/user-attachments/assets/f0513bc1-9dd5-424f-97a8-49348df4d8f6

Mail Triage is an email analysis tool that helps security teams triage suspicious messages quickly. Upload a `.eml` or `.msg` file and it parses headers, checks authentication results, enriches sender and routing data with threat intelligence, extracts links and attachments, and, through a bridge to the companion **PhishGuard** service, runs deeper URL and domain analysis and returns a combined PDF report.

Instead of reading raw headers and checking every link by hand, you get the signals analysts actually check. The email body is never stored or shown.

**Live:** [Landing page](https://email-triage-xpk6.vercel.app/) · [Try the app](https://email-triage-19oh-chi.vercel.app/)

## Features

- Parses inbound email metadata and headers from `.eml` and `.msg` files
- SPF, DKIM, and DMARC verification, shown as a clear pass, fail, or none
- Sender-domain age (WHOIS) and routing/IP reputation checks
- Link extraction with anchor-text vs. destination mismatch detection
- Attachment extraction with extension-spoofing detection (for example `invoice.pdf.exe`)
- Threat-intel enrichment from WHOIS, URLhaus, MalwareBazaar, VirusTotal, AbuseIPDB, and ipinfo.io
- Extracted URLs sent to PhishGuard for deeper scanning, with the PDF report returned to the analyst
- Account sign-up and login with bearer-token authentication

## Privacy by design

Only structural metadata is extracted and saved. The message body is never read into the report or the database.

## How it works

1. Upload a `.eml` or `.msg` file.
2. Mail Triage extracts headers, auth results, links, and attachments.
3. Findings are enriched with live threat intelligence.
4. Extracted URLs go to PhishGuard for deeper analysis.
5. You get a structured report, plus a combined PDF.

## Architecture

- **Mail Triage** handles email parsing, header analysis, and threat-intel enrichment.
- **PhishGuard** is a separate scanner service for URL and domain anomaly scoring, redirect-chain analysis, WHOIS/TLS evaluation, brand-impersonation detection, and optional LLM-based content review.
- **Bridge** submits extracted URLs to PhishGuard, waits for the scan, and stores the resulting PDF with the email's analysis. If PhishGuard is unavailable, email triage still completes and the report shows a status flag.

## Tech stack

FastAPI, React + Vite, SQLite (local) / PostgreSQL (production).

## Project structure

```
├── landing/      Static marketing/landing page
├── frontend/     React + Vite UI for uploading and reviewing emails
└── app/          FastAPI backend: API, models, parsing, threat-intel, PhishGuard bridge
```

## Getting started

```bash
# Backend
cd app
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```
