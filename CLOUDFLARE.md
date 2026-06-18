# Cloudflare Deployment

This repo is Cloudflare Pages ready for the static frontend in `frontend/`.

## What deploys on Cloudflare Pages

- `frontend/index.html`
- `frontend/style.css`
- `frontend/app.js`
- `frontend/assets/`
- `frontend/js/`
- `frontend/css/`
- `frontend/i18n/`

## API setup

Cloudflare Pages cannot run the FastAPI app in `main.py` directly.

Use a separate backend service and set one of these environment variables in Pages:

- `API_ORIGIN`
- `BACKEND_ORIGIN`

The Pages Function at `functions/api/[[path]].js` will proxy `/api/*` requests to that backend.

## Pages settings

- Build command: none
- Build output directory: `frontend`

## Notes

- `frontend/_routes.json` keeps only `/api/*` on the function path.
- If you later migrate the API into Workers, the proxy function can be removed.
