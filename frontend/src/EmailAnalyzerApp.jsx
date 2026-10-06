import React, { useState, useCallback } from "react";
import styled from "styled-components";
import GlobalStyle from "./GlobalStyle";
import TypewriterLoader from "./TypewriterLoader";

const API_BASE_URL = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
const apiUrl = (path) => `${API_BASE_URL}${path}`;
const TOKEN_STORAGE_KEY = "mail-triage-access-token";
const USERNAME_STORAGE_KEY = "mail-triage-username";

const AuthPage = styled.main`
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
`;

const AuthPanel = styled.form`
  width: min(100%, 420px);
  background: var(--color-surface);
  border: 2px solid var(--color-ink);
  box-shadow: 5px 5px 0 var(--color-ink);
  padding: 24px;
`;

const AuthInput = styled.input`
  box-sizing: border-box;
  width: 100%;
  margin: 6px 0 14px;
  padding: 10px;
  border: 2px solid var(--color-ink);
  background: var(--color-bone);
  color: var(--color-ink);
  font: inherit;
`;

const AccountBar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: auto 0 12px;
  min-width: 0;
  font-size: 12px;
  font-weight: 700;
  overflow-wrap: anywhere;
  @media (max-width: 700px) {
    grid-area: account;
    margin: 0;
  }
`;

const toneColor = (tone) =>
  tone === "danger" ? "var(--color-danger)" : tone === "warning" ? "var(--color-warning)" : "var(--color-success)";

// Backend sends full ISO timestamps (e.g. "2026-09-19T08:03:02.103939") — too
// long for the compact sidebar/header. Renders as "Sep 19, 08:03".
const formatTimestamp = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso; // already-friendly demo strings pass through untouched
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + ", " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
};

// Received-chain hostnames can be long unbroken strings (IPv6 literals,
// multi-label FQDNs) with no natural break point — truncate with an ellipsis
// and the full value in a tooltip, rather than letting them wrap character
// by character across dozens of lines.
const truncateHost = (host, max = 28) => {
  if (!host) return "unknown";
  return host.length > max ? host.slice(0, max - 1) + "\u2026" : host;
};

/* ---------- Shared structural pieces (same pattern as the reference component) ---------- */

const Shell = styled.div`
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;
  @media (max-width: 700px) {
    flex-direction: column;
    height: auto;
    min-height: 100vh;
    min-height: 100dvh;
    overflow: visible;
  }
`;

const Sidebar = styled.aside`
  width: 240px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-right: 2px solid var(--color-ink);
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
  @media (max-width: 700px) {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      "brand create"
      "account theme"
      "history history"
      "list list";
    gap: 8px 12px;
    width: 100%;
    flex: 0 0 auto;
    padding: 12px 14px 10px;
    border-right: 0;
    border-bottom: 2px solid var(--color-ink);

    > a {
      grid-area: brand;
      min-width: 0;
      margin-bottom: 0;
    }

    > button:first-of-type {
      grid-area: create;
      width: auto !important;
      margin: 0 !important;
      white-space: nowrap;
    }

    > p {
      grid-area: history;
      align-self: center;
      margin: 0;
    }

    > div[data-history-list] {
      grid-area: list;
      display: flex;
      gap: 10px;
      width: 100%;
      flex: 0 0 auto;
      overflow-x: auto;
      overflow-y: hidden;
    }

    > div[data-history-list] > div {
      flex: 0 0 205px;
      min-width: 0;
      padding: 7px 2px;
    }

    > button:last-of-type {
      grid-area: theme;
      justify-self: end;
      margin: 0 !important;
      white-space: nowrap;
    }
  }
`;

const Logo = styled.a`
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  text-decoration: none;
  color: var(--color-ink);
`;

const LogoMark = styled.div`
  width: 26px;
  height: 26px;
  background: var(--color-accent);
  border: 2px solid var(--color-ink);
  box-shadow: 2px 2px 0 0 var(--color-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-family: var(--font-hud);
  font-weight: 700;
  font-size: 13px;
`;

const HardButton = styled.button`
  font-family: var(--font-hud);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  background: ${(p) => (p.$variant === "ghost" ? "var(--color-surface)" : "var(--color-accent)")};
  color: ${(p) => (p.$variant === "ghost" ? "var(--color-ink)" : "#fff")};
  border: 2px solid var(--color-ink);
  box-shadow: 3px 3px 0 0 var(--color-ink);
  padding: 9px 12px;
  cursor: pointer;
  transition: transform 0.08s ease, box-shadow 0.08s ease;
  &:active {
    transform: translate(3px, 3px);
    box-shadow: 0 0 0 0 var(--color-ink);
  }
`;

// Direct equivalent of `.ow-quest-check` — a bordered, hard-shadowed fieldset
// with an inset legend chip. Every panel in the app reuses this.
const Panel = styled.fieldset`
  display: block;
  min-width: 0;
  background: var(--color-surface);
  border: 2px solid var(--color-ink);
  box-shadow: 4px 4px 0 0 var(--color-ink);
  padding: 16px;
  margin: 0 0 16px;
`;

const Legend = styled.legend`
  font-family: var(--font-hud);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-bone);
  background: var(--color-ink);
  padding: 3px 9px;
  border: 2px solid var(--color-ink);
  line-height: 1;
  margin-bottom: 8px;
`;

// Direct equivalent of `.ow-quest-check__row` — grid row with a dotted divider.
const Row = styled.div`
  display: grid;
  grid-template-columns: 100px 1fr auto;
  align-items: baseline;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 2px dotted var(--color-border-dotted);
  font-size: 13px;
  &:last-of-type { border-bottom: none; padding-bottom: 2px; }
  @media (max-width: 480px) {
    grid-template-columns: 76px minmax(0, 1fr);
    gap: 6px;
    font-size: 12px;

    > :nth-child(3) {
      grid-column: 2;
      justify-self: start;
    }

    > :nth-child(3):empty {
      display: none;
    }
  }
`;

const RowLabel = styled.span`
  font-family: var(--font-hud);
  font-size: 11px;
  color: var(--color-ink-soft);
  text-transform: uppercase;
`;

const RowValue = styled.span`
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
`;

// Direct equivalent of `.ow-quest-check__xp` — the small colored HUD readout on the right of a row.
const Readout = styled.span`
  font-family: var(--font-hud);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  color: ${(p) => toneColor(p.$tone)};
  white-space: nowrap;
`;

// A chunky bordered badge, colored per tone, with a small hard shadow.
const Badge = styled.span`
  display: inline-flex;
  align-items: center;
  font-family: var(--font-hud);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: ${(p) => toneColor(p.$tone)};
  background: var(--color-surface);
  border: 2px solid ${(p) => toneColor(p.$tone)};
  box-shadow: 2px 2px 0 0 ${(p) => toneColor(p.$tone)};
  padding: 2px 7px;
  margin-left: 6px;
`;

const StatCard = styled.div`
  min-width: 0;
  background: var(--color-surface);
  border: 2px solid var(--color-ink);
  box-shadow: 3px 3px 0 0 var(--color-ink);
  padding: 10px 12px;
`;

const StatLabel = styled.p`
  font-family: var(--font-hud);
  font-size: 10px;
  color: var(--color-ink-soft);
  text-transform: uppercase;
  margin: 0 0 4px;
`;

const StatValue = styled.p`
  font-family: var(--font-hud);
  font-size: 15px;
  font-weight: 700;
  margin: 0;
  color: ${(p) => toneColor(p.$tone)};
`;

const Main = styled.main`
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
  @media (max-width: 700px) {
    width: 100%;
    min-width: 0;
    overflow: visible;
    padding: 18px 14px 24px;
  }
`;

const Dropzone = styled.div`
  border: 3px dashed ${(p) => (p.$active ? "var(--color-accent)" : "var(--color-ink)")};
  background: ${(p) => (p.$active ? "var(--color-surface)" : "transparent")};
  height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
  @media (max-width: 700px) {
    box-sizing: border-box;
    width: 100%;
    height: min(58vh, 420px);
    min-height: 260px;
    padding: 18px;
  }
`;

// Unlike Row (fixed 100px label), a URL's anchor text is unbounded in length,
// so this stacks anchor text and destination vertically instead of forcing
// them into a narrow fixed column — that mismatch was overflowing and
// visually overlapping the two lines of text.
const UrlRow = styled.div`
  padding: 8px 0;
  border-bottom: 2px dotted var(--color-border-dotted);
  font-size: 13px;
  &:last-of-type { border-bottom: none; padding-bottom: 2px; }
`;

const UrlAnchorText = styled.div`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 3px;
`;

const SandboxScreenshot = styled.img`
  display: block;
  width: min(100%, 360px);
  max-height: 220px;
  object-fit: contain;
  object-position: left top;
  border: 1px solid var(--color-border-dotted);
  background: var(--color-surface);
`;

const UrlDestinationLine = styled.div`
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
`;

const HistoryRow = styled.div`
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px 4px;
  border-bottom: 2px dotted var(--color-border-dotted);
  cursor: pointer;
  background: ${(p) => (p.$active ? "var(--color-bone)" : "transparent")};
  &:last-of-type { border-bottom: none; }
`;

const HistoryList = styled.div`
  flex: 1;
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  &::-webkit-scrollbar { display: none; }
`;

const AuthGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 200px));
  gap: 10px;
  margin-bottom: 16px;
  @media (max-width: 480px) {
    gap: 6px;
  }
`;

const FindingsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
  @media (max-width: 700px) {
    grid-template-columns: minmax(0, 1fr);
  }
`;

/* ---------- App ---------- */

export default function EmailAnalyzerApp() {
  const [theme, setTheme] = useState("light");
  const [report, setReport] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_STORAGE_KEY) || "");
  const [username, setUsername] = useState(() => sessionStorage.getItem(USERNAME_STORAGE_KEY) || "");
  const [authMode, setAuthMode] = useState("login");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [requestError, setRequestError] = useState("");
  const [screenshotPreviews, setScreenshotPreviews] = useState({ reportId: null, urls: {} });

  const requestApi = useCallback(async (path, options = {}) => {
    const activeToken = sessionStorage.getItem(TOKEN_STORAGE_KEY);
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: {
        ...options.headers,
        ...(activeToken ? { Authorization: `Bearer ${activeToken}` } : {}),
      },
    });
    if (response.status === 401) {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY);
      sessionStorage.removeItem(USERNAME_STORAGE_KEY);
      setToken("");
      setUsername("");
    }
    return response;
  }, []);

  // data-theme must live on <html>, not a div below <body> — GlobalStyle sets
  // `color` on body itself, and CSS inheritance resolves that against
  // whatever --color-ink is at body's own position in the tree. Setting the
  // attribute deeper doesn't retroactively re-color the already-inherited value.
  React.useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const refreshHistory = useCallback(async () => {
    try {
      const res = await requestApi("/analyses");
      if (!res.ok) throw new Error("backend unavailable");
      const data = await res.json();
      setHistory(data);
      setRequestError("");
    } catch (error) {
      setHistory([]);
      setRequestError(error.message || "Could not load your analysis history.");
    }
  }, [requestApi]);

  const refreshHistoryFromEffect = React.useEffectEvent(() => {
    refreshHistory();
  });

  React.useEffect(() => {
    if (token) queueMicrotask(refreshHistoryFromEffect);
  }, [token]);

  const openHistoryItem = useCallback(async (item) => {
    try {
      const res = await requestApi(`/analyses/${item.id}`);
      if (!res.ok) throw new Error("not found");
      const data = await res.json();
      setReport(data);
      setRequestError("");
    } catch (error) {
      setRequestError(error.message || "Could not load this analysis.");
    }
  }, [requestApi]);

  const handleFile = useCallback(async (file) => {
    if (!file) return;
    setLoading(true);
    setRequestError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await requestApi("/analyze", { method: "POST", body: form });
      if (!res.ok) throw new Error("backend unavailable");
      const data = await res.json();
      setReport(data);
      refreshHistory(); // pick up the newly saved analysis in the sidebar
    } catch (error) {
      setRequestError(error.message || "Could not analyze this email.");
    } finally {
      setLoading(false);
    }
  }, [refreshHistory, requestApi]);

  const submitAuth = useCallback(async (event) => {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    const form = new FormData(event.currentTarget);
    const credentials = {
      username: form.get("username"),
      password: form.get("password"),
    };
    try {
      const response = await fetch(apiUrl(`/auth/${authMode === "register" ? "register" : "login"}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Authentication failed.");
      sessionStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
      sessionStorage.setItem(USERNAME_STORAGE_KEY, result.username);
      setToken(result.access_token);
      setUsername(result.username);
      setHistory([]);
      setReport(null);
      setAuthError("");
    } catch (error) {
      setAuthError(error.message || "Authentication failed.");
    } finally {
      setAuthBusy(false);
    }
  }, [authMode]);

  const signOut = useCallback(() => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    sessionStorage.removeItem(USERNAME_STORAGE_KEY);
    setToken("");
    setUsername("");
    setHistory([]);
    setReport(null);
  }, []);

  const downloadProtectedFile = useCallback(async (path, filename) => {
    try {
      const response = await requestApi(path);
      if (!response.ok) throw new Error("Could not download this file.");
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setRequestError(error.message || "Could not download this file.");
    }
  }, [requestApi]);

  React.useEffect(() => {
    if (!token || !report?.id) {
      return undefined;
    }

    let cancelled = false;
    const objectUrls = [];
    const screenshotUrls = (report.urls || [])
      .filter((item) => item.actual_href && item.sandbox?.screenshot_available)
      .map((item) => item.actual_href);

    Promise.all(screenshotUrls.map(async (url) => {
      const path = `/analyses/${report.id}/sandbox-screenshot?url=${encodeURIComponent(url)}`;
      try {
        const response = await requestApi(path);
        if (!response.ok) return null;
        const objectUrl = URL.createObjectURL(await response.blob());
        objectUrls.push(objectUrl);
        return [url, objectUrl];
      } catch {
        return null;
      }
    })).then((entries) => {
      if (!cancelled) {
        setScreenshotPreviews({
          reportId: report.id,
          urls: Object.fromEntries(entries.filter(Boolean)),
        });
      }
    });

    return () => {
      cancelled = true;
      objectUrls.forEach((objectUrl) => URL.revokeObjectURL(objectUrl));
    };
  }, [report, requestApi, token]);

  const currentScreenshotPreviews = screenshotPreviews.reportId === report?.id
    ? screenshotPreviews.urls
    : {};

  if (!token) {
    return (
      <>
        <GlobalStyle />
        <AuthPage>
          <AuthPanel onSubmit={submitAuth}>
            <Logo href="/" style={{ marginBottom: 24 }}>
              <LogoMark>M</LogoMark>
              <span style={{ fontFamily: "var(--font-hud)", fontWeight: 700, fontSize: 14 }}>MAIL TRIAGE</span>
            </Logo>
            <h1 style={{ fontFamily: "var(--font-hud)", fontSize: 21, margin: "0 0 8px",color: "var(--color-accent)"  }}>
              {authMode === "login" ? "Sign in" : "Create account"}
            </h1>
            <p style={{ color: "var(--color-ink-soft)", fontSize: 13, margin: "0 0 20px" }}>
              Your email analyses and history are private to your account.
            </p>
            <label htmlFor="auth-username">Username</label>
            <AuthInput id="auth-username" name="username" autoComplete="username" minLength={3} maxLength={32} required />
            <label htmlFor="auth-password">Password</label>
            <AuthInput id="auth-password" name="password" type="password" autoComplete={authMode === "login" ? "current-password" : "new-password"} minLength={12} maxLength={128} required />
            {authError && <p role="alert" style={{ color: "var(--color-danger)", fontSize: 13 }}>{authError}</p>}
            <HardButton type="submit" disabled={authBusy} style={{ width: "100%", marginTop: 8 }}>
              {authBusy ? "Please wait..." : authMode === "login" ? "Sign in" : "Create account"}
            </HardButton>
            <button
              type="button"
              onClick={() => { setAuthError(""); setAuthMode(authMode === "login" ? "register" : "login"); }}
              style={{ display: "block", margin: "18px auto 0", background: "none", border: 0, color: "var(--color-accent)", font: "inherit", fontWeight: 700, cursor: "pointer" }}
            >
              {authMode === "login" ? "Create an account" : "Already registered? Sign in"}
            </button>
          </AuthPanel>
        </AuthPage>
      </>
    );
  }

  return (
    <>
      <GlobalStyle />
      <Shell>
        <Sidebar>
          <Logo href="/">
            <LogoMark>M</LogoMark>
            <span style={{ fontFamily: "var(--font-hud)", fontWeight: 700, fontSize: 14 }}>MAIL TRIAGE</span>
          </Logo>

          <HardButton onClick={() => setReport(null)} style={{ marginBottom: 18, width: "100%" }}>
            + New analysis
          </HardButton>

          <Legend as="p" style={{ display: "inline-block" }}>History</Legend>
          <HistoryList data-history-list>
            {history.map((item) => (
              <HistoryRow key={item.id} $active={report?.id === item.id} onClick={() => openHistoryItem(item)}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.filename}</div>
                  <div style={{ fontFamily: "var(--font-hud)", fontSize: 10, color: "var(--color-ink-soft)" }}>{formatTimestamp(item.timestamp)}</div>
                </div>
                <Badge $tone={item.flag_count > 2 ? "danger" : item.flag_count > 0 ? "warning" : "success"}>{item.flag_count}</Badge>
              </HistoryRow>
            ))}
          </HistoryList>

          <AccountBar>
            <span title={username}>{username}</span>
            <HardButton $variant="ghost" onClick={signOut} style={{ padding: "6px 8px", fontSize: 11 }}>
              Sign out
            </HardButton>
          </AccountBar>

          <HardButton $variant="ghost" onClick={() => setTheme(theme === "light" ? "dark" : "light")} style={{ marginTop: 12 }}>
            {theme === "light" ? "Dark mode" : "Light mode"}
          </HardButton>

        </Sidebar>

        <Main>
          {requestError && (
            <p role="alert" style={{ color: "var(--color-danger)", margin: "0 0 14px", overflowWrap: "anywhere" }}>
              {requestError}
            </p>
          )}
          {!report && (
            <Dropzone
              $active={dragOver}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
              onClick={() => document.getElementById("file-input").click()}
            >
              <input id="file-input" type="file" accept=".eml,.msg" style={{ display: "none" }}
                     onChange={(e) => handleFile(e.target.files[0])} />
              <p style={{ margin: "0 0 6px" }}>
                {loading ? <TypewriterLoader /> : "DROP A .EML OR .MSG FILE"}
              </p>
              {!loading && <p style={{ color: "var(--color-ink-soft)", margin: 0, fontSize: 13 }}>or click to browse</p>}
            </Dropzone>
          )}

          {report && (
            <div style={{ maxWidth: 1000 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
                <div>
                  <p style={{ fontWeight: 700, fontSize: 17, margin: 0 }}>{report.filename}</p>
                  <p style={{ fontFamily: "var(--font-hud)", color: "var(--color-ink-soft)", fontSize: 11, margin: "3px 0 0" }}>{formatTimestamp(report.timestamp)}</p>
              {report.phishguard_status && report.phishguard_status !== "no_urls" && (
                <Panel style={{ marginBottom: 16 }}>
                  <Legend>PhishGuard link report</Legend>
                  {report.phishguard_report_available ? (
                    <Row>
                      <RowLabel>Status</RowLabel>
                      <RowValue>Report generated for every link found in this email</RowValue>
                      <HardButton
                        type="button"
                        onClick={() => downloadProtectedFile(
                          `/analyses/${report.id}/phishguard-report`,
                          `phishguard-report-${report.id}.pdf`,
                        )}
                        style={{ fontSize: 11, padding: "6px 10px" }}
                      >
                        Download PDF
                      </HardButton>
                    </Row>
                  ) : (
                    <Row>
                      <RowLabel>Status</RowLabel>
                      <RowValue style={{ color: "var(--color-warning)" }}>
                        {report.phishguard_status === "unreachable"
                          ? "PhishGuard was unreachable — link report unavailable for this run"
                          : "PhishGuard couldn't generate a report for this run"}
                      </RowValue>
                      <span />
                    </Row>
                  )}
                </Panel>
              )}

                </div>
                <Badge $tone={report.flag_count > 2 ? "danger" : report.flag_count > 0 ? "warning" : "success"}>
                  {report.flag_count} flag{report.flag_count === 1 ? "" : "s"}
                </Badge>
              </div>

              <AuthGrid>
                {["spf", "dkim", "dmarc"].map((k) => {
                  const v = report.auth[k];
                  const tone = v === "pass" ? "success" : v === "fail" ? "danger" : "warning";
                  return (
                    <StatCard key={k}>
                      <StatLabel>{k}</StatLabel>
                      <StatValue $tone={tone}>{v ? v.toUpperCase() : "\u2014"}</StatValue>
                    </StatCard>
                  );
                })}
              </AuthGrid>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, alignItems: "start" }}>
                <Panel>
                  <Legend>Sender identity</Legend>
                  <Row>
                    <RowLabel>From</RowLabel>
                    <RowValue>{report.sender.from}</RowValue>
                    <span />
                  </Row>
                  <Row>
                    <RowLabel>Reply-To</RowLabel>
                    <RowValue>{report.sender.reply_to}</RowValue>
                    {report.sender.from_reply_to_mismatch && <Badge $tone="danger">Mismatch</Badge>}
                  </Row>
                  <Row>
                    <RowLabel>Return-Path</RowLabel>
                    <RowValue>{report.sender.return_path}</RowValue>
                    {report.sender.from_return_path_mismatch && <Badge $tone="danger">Mismatch</Badge>}
                  </Row>
                  {report.sender_domain_age_days != null && (
                    <Row>
                      <RowLabel>Domain age</RowLabel>
                      <RowValue />
                      <Readout $tone={report.sender_domain_age_days < 30 ? "danger" : "success"}>
                        {report.sender_domain_age_days}d old
                      </Readout>
                    </Row>
                  )}
                </Panel>

                {report.routing?.sending_ip && (
                  <Panel>
                    <Legend>Routing &amp; sending IP</Legend>
                    <Row>
                      <RowLabel>IP</RowLabel>
                      <RowValue>{report.routing.sending_ip}</RowValue>
                      {report.routing.ip_reputation_flagged && <Badge $tone="danger">Flagged</Badge>}
                    </Row>
                    {report.routing.ip_reputation_score != null && (
                      <Row>
                        <RowLabel>Abuse score</RowLabel>
                        <RowValue />
                        <Readout $tone={report.routing.ip_reputation_score >= 25 ? "danger" : "success"}>
                          {report.routing.ip_reputation_score}/100
                        </Readout>
                      </Row>
                    )}
                    {report.routing.asn && (
                      <Row>
                        <RowLabel>ASN</RowLabel>
                        <RowValue>{report.routing.asn}</RowValue>
                        <span />
                      </Row>
                    )}
                    {report.routing.geolocation && (
                      <Row>
                        <RowLabel>Location</RowLabel>
                        <RowValue>{report.routing.geolocation}</RowValue>
                        <span />
                      </Row>
                    )}
                  </Panel>
                )}

                {report.received_chain?.length > 0 && (
                  <Panel>
                    <Legend>Received chain</Legend>
                    {report.received_chain.map((h, i) => (
                      <UrlRow key={i} title={`${h.from_host || "unknown"} \u2192 ${h.by_host || "unknown"}`}>
                        <RowLabel>Hop {i + 1}</RowLabel>
                        <UrlDestinationLine style={{ marginTop: 2 }}>
                          <span style={{ flex: "1 1 auto", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {truncateHost(h.from_host)} &rarr; {truncateHost(h.by_host)}
                          </span>
                          <Readout style={{ flexShrink: 0 }}>{formatTimestamp(h.timestamp)}</Readout>
                        </UrlDestinationLine>
                      </UrlRow>
                    ))}
                  </Panel>
                )}
              </div>

              <FindingsGrid>
                {report.urls?.length > 0 && (
                  <Panel>
                    <Legend>Links found</Legend>
                    {report.urls.map((u, i) => {
                      const hostTitle = u.urlhaus_host_flagged
                        ? `${u.anchor_text} — this domain has ${u.urlhaus_host_url_count} known-malicious URL${u.urlhaus_host_url_count === 1 ? "" : "s"} on record with URLhaus`
                        : u.anchor_text;
                      return (
                      <UrlRow key={i} title={hostTitle}>
                        <UrlAnchorText>{u.anchor_text}</UrlAnchorText>
                        <UrlDestinationLine>
                          <span style={{
                            flex: "1 1 auto", minWidth: 0, overflowWrap: "anywhere", wordBreak: "break-word",
                            color: u.mismatch || u.urlhaus_flagged || u.sandbox?.risk_detected ? "var(--color-danger)" : "var(--color-ink)",
                          }}>
                            &rarr; {u.actual_href}
                          </span>
                          <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, flexShrink: 0 }}>
                            {u.urlhaus_flagged && (
                              <Badge $tone="danger">
                                URLhaus{u.urlhaus_tags ? `: ${u.urlhaus_tags.split(",")[0]}` : ""}
                              </Badge>
                            )}
                            {!u.urlhaus_flagged && u.urlhaus_host_flagged && (
                              <Badge $tone="warning">Host history ({u.urlhaus_host_url_count})</Badge>
                            )}
                            {u.mismatch && <Badge $tone="danger">Mismatch</Badge>}
                            {!u.urlhaus_flagged && !u.urlhaus_host_flagged && !u.mismatch && (
                              <Readout $tone="success">{u.domain_age_days != null ? `${u.domain_age_days}d old` : "\u2014"}</Readout>
                            )}
                          </span>
                        </UrlDestinationLine>
                        {u.sandbox && (
                          <div style={{ marginTop: 5, fontSize: 12 }}>
                            <Badge $tone={u.sandbox.risk_detected ? "danger" : u.sandbox.available ? "success" : "warning"}>
                              {u.sandbox.status === "complete"
                                ? u.sandbox.risk_detected ? "Sandbox flagged" : "Sandbox clean"
                                : u.sandbox.status === "unavailable" ? "Sandbox unavailable" : "Sandbox skipped"}
                            </Badge>
                            {u.sandbox.risk_signals?.length > 0 && (
                              <div style={{ color: "var(--color-danger)", marginTop: 5, overflowWrap: "anywhere" }}>
                                {u.sandbox.risk_signals.join(" · ")}
                              </div>
                            )}
                            {!u.sandbox.available && u.sandbox.reason && (
                              <div style={{ color: "var(--color-ink-soft)", marginTop: 5, overflowWrap: "anywhere" }}>
                                {u.sandbox.reason}
                              </div>
                            )}
                            {u.sandbox.screenshot_available && (
                              <div style={{ marginTop: 8 }}>
                                {screenshotPreviews[u.actual_href] ? (
                                  <a
                                    href={screenshotPreviews[u.actual_href]}
                                    target="_blank"
                                    rel="noreferrer"
                                    aria-label={`Open screenshot preview for ${u.actual_href}`}
                                  >
                                    <SandboxScreenshot
                                      src={screenshotPreviews[u.actual_href]}
                                      alt={`Rendered page screenshot for ${u.actual_href}`}
                                    />
                                  </a>
                                ) : (
                                  <div style={{ color: "var(--color-ink-soft)" }}>Loading screenshot preview...</div>
                                )}
                                <HardButton
                                  type="button"
                                  onClick={() => downloadProtectedFile(
                                    `/analyses/${report.id}/sandbox-screenshot?url=${encodeURIComponent(u.actual_href)}`,
                                    `sandbox-screenshot-${report.id}.png`,
                                  )}
                                  style={{ fontSize: 11, padding: "6px 10px", marginTop: 6 }}
                                >
                                  Download Image
                                </HardButton>
                              </div>
                            )}
                          </div>
                        )}
                      </UrlRow>
                      );
                    })}
                  </Panel>
                )}

                {report.attachments?.length > 0 && (
                  <Panel>
                    <Legend>Attachments</Legend>
                    {report.attachments.map((a, i) => (
                      <Row key={i}>
                        <RowLabel>File</RowLabel>
                        <RowValue>
                          {a.filename}
                          {a.malwarebazaar_flagged && a.malware_signature && (
                            <div style={{ fontFamily: "var(--font-hud)", fontSize: 10, color: "var(--color-danger)", marginTop: 2 }}>
                              {a.malware_signature}
                            </div>
                          )}
                        </RowValue>
                        <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
                          {a.malwarebazaar_flagged && <Badge $tone="danger">Malware</Badge>}
                          {a.virustotal_flagged && <Badge $tone="danger">VT {a.virustotal_malicious_count}</Badge>}
                          {a.extension_mismatch && <Badge $tone="danger">Spoofed</Badge>}
                        </span>
                      </Row>
                    ))}
                  </Panel>
                )}
              </FindingsGrid>
            </div>
          )}
        </Main>
      </Shell>
    </>
  );
}
