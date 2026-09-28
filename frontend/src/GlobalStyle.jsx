import { createGlobalStyle } from 'styled-components';

// Same structural language as the reference component (thick ink borders, hard
// offset shadows, dotted dividers, monospace HUD labels) — recolored for
// Mail Triage's indigo brand instead of the fantasy bone/ink/gold palette.
const GlobalStyle = createGlobalStyle`
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap');

  :root {
    --color-ink: #14161A;
    --color-ink-soft: #4B4E5B;
    --color-bone: #FAFAF7;
    --color-surface: #FFFFFF;
    --color-border-dotted: #D6D5CE;
    --color-accent: #4F46E5;
    --color-accent-dark: #3D34C4;
    --color-danger: #D64545;
    --color-warning: #C98A2C;
    --color-success: #2E9E6B;
    --font-body: 'Inter', ui-sans-serif, sans-serif;
    --font-hud: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  }

  [data-theme="dark"] {
    --color-ink: #EDECE6;
    --color-ink-soft: #B8B6AC;
    --color-bone: #17181C;
    --color-surface: #1E2025;
    --color-border-dotted: #34363C;
    --color-accent: #7C86FF;
    --color-accent-dark: #94A0FF;
    --color-danger: #E8827D;
    --color-warning: #E0B067;
    --color-success: #6BC79B;
  }

  * { box-sizing: border-box; }
  html, body, #root { margin: 0; padding: 0; width: 100%; height: 100%; }
  body {
    font-family: var(--font-body);
    background: var(--color-bone);
    color: var(--color-ink);
    transition: background 0.2s ease, color 0.2s ease;
  }
`;

export default GlobalStyle;
