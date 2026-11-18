# nginx (frontend container)

`default.conf` serves `frontend/dist` and proxies `/api`, `/health` and the API docs to the backend.

## Content-Security-Policy hash

`index.html` has one inline script (it applies the saved light/dark theme before first paint).
The CSP allows it by its SHA-256 hash. If you edit that script, recompute the hash and paste it
into `security.conf`:

```bash
python3 - <<'PY'
import re, hashlib, base64
s = re.search(r"<script>(.*?)</script>", open("frontend/index.html").read(), re.S).group(1)
print("sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode())
PY
```

A wrong hash doesn't break the app: the browser blocks the script and logs a CSP error, and
the theme falls back to dark.
