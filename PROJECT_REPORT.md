# Mail Triage + PhishGuard Project Report

## 1. Executive Summary

Mail Triage is an email analysis product designed to help security teams triage suspicious messages by examining headers, authentication results, sender routing, extracted links, attachments, and risk indicators. The system produces a structured analysis record for each uploaded `.eml` or `.msg` file and provides a user-facing report that summarizes the evidence collected.

The product is intentionally built as a two-service architecture. Mail Triage handles email parsing and submission logic, while PhishGuard performs deeper URL and domain analysis with anomaly scoring, threat intelligence lookups, redirect-chain inspection, TLS checks, and optional LLM-based content review. The two systems are connected through a bridge layer that submits extracted links to PhishGuard, polls for completion, and returns a generated PDF report to the email application.

This project is operationally sound in structure, but its real-world reliability depends on correct environment configuration, service wiring, and deployment hygiene. The main risk areas are external API connectivity, missing environment variables, stale model names, and service-to-service URL configuration.

## 2. Product Purpose and Value

The main value proposition is to reduce analyst effort when investigating suspicious email messages. Instead of manually reading raw headers and checking every link, the system automatically:

- Parses inbound email metadata and headers
- Evaluates SPF, DKIM, and DMARC results
- Checks sender-domain age and route information
- Extracts URLs and attachments
- Detects common phishing indicators such as mismatched sender details or risky links
- Sends suspicious URLs to a dedicated threat-scanning service
- Produces a report that combines both email-level and URL-level risk signals

This makes the tool useful for both automated triage and human review, especially in phishing response workflows.

## 3. Scope of the Current Solution

### Email analysis scope

The email intake pipeline currently covers:

- `.eml` and `.msg` ingestion
- Sender and reply-to validation
- Authentication verification via SPF/DKIM/DMARC
- IP reputation and routing metadata
- URL extraction and anchor-to-destination mismatch checks
- Attachment extraction and mismatch detection
- WHOIS and domain-age checks for sender and URL risk contexts
- Threat intelligence enrichment for suspicious indicators
- Persistence of each analysis and its child records in a database

### URL scanning scope

PhishGuard adds security analysis on URLs extracted from the email:

- URL feature extraction and anomaly scoring
- K-means and SOM-based behavior scoring
- VirusTotal and Safe Browsing lookups
- Redirect-chain analysis
- WHOIS and SSL/TLS evaluation
- Brand impersonation / lookalike detection
- Optional LLM-based content analysis when enabled

The bridge layer between the two systems is critical: it converts extracted email URLs into scan jobs and downloads the final report for the analyst.

## 4. Architecture

### 4.1 Mail Triage architecture

The Mail Triage repo is organized around a FastAPI application with a frontend and API layer:

- `landing/`: static landing page for marketing or product intro content
- `frontend/`: React/Vite user interface for uploading and reviewing emails
- `app/`: API logic, models, parsing, threat-intel enrichment, and integration bridge

The API is expected to run as a Railway service. In local development, SQLite is used as the fallback database, while PostgreSQL is the intended production database.

### 4.2 PhishGuard architecture

The PhishGuard codebase is a separate scanner service with its own API and worker patterns. It exposes endpoints for scan submission, status polling, and report retrieval. Its report pipeline generates PDF and multi-format outputs depending on the job type.

### 4.3 Integration model

The integration is intentionally asynchronous but still user-facing in the sense that the email API waits for the PhishGuard response before finalizing the stored analysis. This ensures the PDF report is available when the result is returned, but it also makes the triage service vulnerable to slow or unavailable external scanning services.

The bridge has clear behavior for failure modes:

- no URLs: no scan is submitted
- connectivity failure: marked as unreachable
- unexpected exceptions: marked as error
- successful job: PDF is downloaded and stored

This is a useful design choice because it prevents a PhishGuard outage from breaking the email triage system entirely.

## 5. Current Implementation Status

### Working areas

The codebase demonstrates a complete end-to-end path for the core product:

- Email upload and parsing are in place
- Threat enrichment runs before storing the result
- The PhishGuard bridge submits URLs and polls for completion
- Report availability is persisted in the database
- A UI exists for listing past analyses and viewing details
- PDF report delivery is wired through API response flow

### Operational dependencies

The system is not self-contained. It depends on correct setup in multiple environments:

- Mail Triage backend environment variables
- PhishGuard service URL configuration
- Postgres database linkage in Railway
- LLM credentials and model names for optional AI features
- Vercel frontend public API URL configuration

This means product health depends on deployment configuration as much as code correctness.

## 6. Key Findings and Risks

### 6.1 Correct service URL is critical

A common issue in this architecture is using the wrong URL target. The Mail Triage backend must point to the public PhishGuard Railway URL, not `localhost`, and not a partial endpoint such as `/scan` appended incorrectly.

The integration is sensitive to:

- base URL format
- trailing slash handling
- whether the endpoint is the service root or a concrete route
- whether the service is reachable from the deployed environment

### 6.2 LLM configuration is split across two functions

This project has two different AI-related flows that must not be conflated:

1. PhishGuard URL-content analysis uses `LLM_PROVIDER` and `GEMINI_API_KEY` on the scanner service.
2. PhishGuard report summary generation uses `REPORT_LLM_PROVIDER`, `LLM_PROVIDER`, and `GEMINI_MODEL` in the report generator.

If the wrong key or model is configured, AI enrichment may silently fail while the underlying scan still succeeds.

### 6.3 Old records are not trustworthy for current status

The project brief explicitly notes that previous analysis records may retain stale `phishguard_status` values. This means any current debugging or verification must be based on a fresh email submission rather than older data.

### 6.4 Frontend API configuration matters

The frontend uses `VITE_API_URL` at build time. If this variable is missing or malformed, the browser may request the wrong host or a relative URL path, causing 404s, 502s, or failed API calls. This is a deployment configuration issue, not just a frontend bug.

## 7. Project Health Assessment

### Overall assessment

The project demonstrates a strong prototype-to-production architecture and has a coherent modular structure. The core pipeline is in place, and the integration points are clear. The product does not appear to be in a random or incomplete state; instead, it is a deployment-heavy application whose main challenge is environment correctness.

### Main strengths

- Clear separation of responsibilities between email parsing and threat analysis
- Use of dedicated staging services rather than one monolith
- Strong database persistence for analyses and related evidence
- Flexible report generation across file formats
- Good handling of partial failures without crashing the whole system

### Main weaknesses

- Strong dependency on deployment environment variables
- The service boundary between Mail Triage and PhishGuard is operationally brittle if misconfigured
- LLM behavior depends on a changing external provider and model availability
- Frontend deployment issues can appear as product failures even when the backend is healthy

## 8. Recommended Verification Order

To continue work effectively, the next validation steps should be:

1. Confirm the deployed frontend requests the correct Railway API host
2. Confirm the backend is connected to the correct Postgres database
3. Confirm `PHISHGUARD_BASE_URL` points to the live PhishGuard service root URL
4. Submit a fresh email and verify both status polling and PDF download
5. Check PGuard logs for scan status and API failures
6. Verify all LLM env vars are valid and model IDs are current
7. Review only fresh results, not older stale records

This order avoids chasing the wrong failure source and keeps debugging rooted in current evidence.

## 9. Suggested Next Development Priorities

### Near-term priorities

- Harden environment validation at startup for required service URLs and secrets
- Add clearer logging and explicit status messages for service failures
- Improve error responses in the UI when PhishGuard analysis is unavailable
- Include diagnostics for malformed `VITE_API_URL` values
- Ensure LLM fallback and provider selection are visible in logs

### Medium-term priorities

- Add health-check and readiness validation across Mail Triage and PhishGuard
- Improve caching and retry logic for external API calls
- Add better user-facing explanation when a report is unavailable or delayed
- Provide a single dashboard view showing current service health and deployment config state

### Long-term priorities

- Expand triage features for larger email volumes and case management
- Add analyst workflow support for review, triaging, escalation, and evidence export
- Improve automated detection quality across phishing campaigns and malicious senders

## 10. Conclusion

Mail Triage + PhishGuard is a well-structured project with a clear product niche: it takes suspicious emails, enriches them with technical context, and sends extracted links to a dedicated threat analysis engine for deeper review. The codebase is coherent, modular, and aligned with a practical phishing-response workflow.

The project’s main challenge is not a missing core feature; it is correct deployment configuration and operational reliability across multiple external services. Once the URL wiring, Railway environment values, and LLM configuration are verified, the system should be able to function as intended in production.

This project is in a good state for continued development, provided the team keeps verifying live configuration and treats service connectivity as a first-class engineering concern.
