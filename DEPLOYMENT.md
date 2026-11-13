# Deploy PixelEcho on Render

The code supports a hosted domain while keeping localhost development working.
Render supplies RENDER_EXTERNAL_URL automatically. PUBLIC_ORIGIN overrides it
for a custom domain, for example https://pixelecho.example (no path).
The allowed-host list stays explicit; arbitrary hosts and cross-origin browser
submissions are rejected. HTTPS validation uses the configured public origin,
not untrusted forwarding headers. No CORS wildcard is enabled.

## Service settings

- Connect the GitHub repository as a Python Web Service.
- Branch: main (or the branch containing your current code).
- Root Directory: leave blank if server.py is at repository root. Otherwise,
  use image-search.
- Build Command: pip install -r requirements.lock.txt
- Start Command: python deploy.py
- Health Check Path: /api/status
- Instances: one. deploy.py also fixes workers=1 because cases live in memory.
- Python: .python-version requests the latest Python 3.11 patch on Render.
  Remove any conflicting PYTHON_VERSION override in your Render settings.

## Secrets

Set GOOGLE_VISION_API_KEY and SERPER_API_KEY in the Render dashboard.
Do not upload config.local.json, the .venv directory, or a secrets-filled .env.
For an onrender.com address, no PUBLIC_ORIGIN setting is required.
For a custom domain, set PUBLIC_ORIGIN to its exact HTTPS origin and redeploy.
Only that configured public origin will be accepted for browser submissions.
Environment changes require restart/redeploy.

The Windows start.ps1 remains for local development. deploy.py binds to
0.0.0.0 and Render's PORT, defaulting to 10000 outside Render. It is intended
for hosted use; do not expose an unauthenticated development server by accident.

## Check the deployed service

1. Confirm /api/status returns JSON (it does not disclose API keys).
2. Open the home page and /architecture.
3. Upload an image and test source collection and comparison.
4. Export a report from the same browser session.
5. Check logs for import errors if native dependencies fail to load on Linux.

The complete dependency installation and native C2PA/OpenCV runtime have not
been verified on Render/Linux in this session. Local regression tests and
host/origin tests do not prove successful cloud deployment. If installation
fails, preserve the build error and diagnose that dependency rather than
removing signature or image verification silently.

Cases are ephemeral and clear on service restart. Do not scale to multiple
instances without moving state to shared storage. There is currently no login,
per-user quota, or monthly application spending cap. Same-origin checks are
not authentication: direct API callers can consume provider credits. Limit demo
access/provider quotas before sharing publicly.
