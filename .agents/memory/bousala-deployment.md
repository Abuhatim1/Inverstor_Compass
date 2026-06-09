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

`st.markdown('<link rel="apple-touch-icon" ...>')` injects into `<body>`, but Safari only reads from `<head>`.

**Do NOT embed base64 in `st.markdown()`** — a 180×180 PNG base64-encoded is ~100KB of inline HTML. This bloats Streamlit's initial response and causes the proxy-level health check at `/` to time out during startup → deployment crashes with SIGTERM.

**Do NOT use `streamlit.components.v1.html()`** — this also causes deployment instability (SIGTERM after ~5s).

**Correct fix:** Enable static file serving (`enableStaticServing = true` in `.streamlit/config.toml`). This serves `edgar_app/static/icon.png` at `/app/static/icon.png`. Then use a lightweight URL reference:
```python
st.markdown('<link rel="apple-touch-icon" href="/app/static/icon.png">', unsafe_allow_html=True)
```
This injects into `<body>` (Safari may not always use it for Add to Home Screen), but the deployment stays stable.

## Streamlit config.toml location

`edgar_app/.streamlit/config.toml` IS picked up when running `edgar_app/app.py` even from the workspace root — Streamlit searches the script directory. The production run command does NOT need to `cd edgar_app` first.

## Production URL

`https://investor-compass.replit.app` — visibility: private (invited only as of initial deploy).

## Icon file

`edgar_app/static/icon.png` — 747KB, 512×512 compass rose generated image. Resized to 180×180 in memory for the apple-touch-icon injection.
