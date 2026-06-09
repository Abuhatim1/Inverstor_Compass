---
name: Bousala deployment config
description: How the Streamlit app is wired into the pnpm monorepo deployment, and the lessons learned getting it live.
---

## How the Streamlit app is deployed

The Bousala app (Python/Streamlit) is NOT a pnpm artifact type — it runs as a second service inside `artifacts/api-server/.replit-artifact/artifact.toml`.

Two services are defined in that one artifact.toml:
1. **API Server** — port 8080, paths `["/api"]`, health check `/api/healthz`
2. **Bousala App** — port 5000, paths `["/"]`, health check `/_stcore/health`

**Why:** Streamlit must return 200 at `/_stcore/health` (its built-in endpoint). Using `/` as the health check causes the deployment to terminate because Streamlit returns 500 at `/` during the proxy-routed health check phase.

**How:** Edit `artifact.edit.toml`, add `[services.production.health.startup] path = "/_stcore/health"` for the Streamlit service, then call `verifyAndReplaceArtifactToml`.

## Apple touch icon (iPhone "Add to Home Screen")

`st.markdown('<link rel="apple-touch-icon" ...>')` does NOT work — it injects into `<body>`, but Safari only reads from `<head>`.

**Fix:** Use `streamlit.components.v1.html()` (same-origin iframe) to run JS that appends the link to `window.parent.document.head`. Resize the icon to 180×180 before base64-encoding to reduce payload.

## Production URL

`https://investor-compass.replit.app` — visibility: private (invited only as of initial deploy).

## Icon file

`edgar_app/static/icon.png` — 747KB, 512×512 compass rose generated image. Resized to 180×180 in memory for the apple-touch-icon injection.
