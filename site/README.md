# Script2Subs website

A static landing page — no build step. It links the Download button straight
to the newest release DMG (resolved client-side from the GitHub API, with the
releases page as a fallback).

## Deploy to Cloudflare Pages

**Option A — Git integration (recommended, no secrets):**
1. Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git.
2. Pick `tiggertian/script2subs`.
3. Framework preset: **None**. Build command: *(leave empty)*.
   Build output directory: **`site`**.
4. Save. Every push to `main` redeploys.

**Option B — Direct upload:**
```bash
npx wrangler pages deploy site --project-name script2subs
```

## Local preview
```bash
python3 -m http.server -d site 8000   # http://127.0.0.1:8000
```

The download button needs the GitHub API; offline it just falls back to the
releases page.
