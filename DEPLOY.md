# Deploy checklist — LinkForge-style security upgrade

Code is ready and tested locally (20/20 offline tests). This file is
the exact order to get it live. Do not skip step 2 — without
`SECRET_KEY` the new code refuses to create/verify tokens.

## 1. Commit + push

From a machine where git is already signed in to the `xarveth` account:

```bash
cd bot-verification
git add -A
git commit -m "Add LinkForge-style security: Turnstile, Chrome-only gate, MongoDB session tracking

- Cloudflare Turnstile, verified server-side
- Chrome-only gate (server UA + Sec-CH-UA, plus navigator.brave check)
- MongoDB sessions, rate limits 10/min + 70/hour, one-time tokens
- Math challenge verified server-side; hardcoded SECRET_KEY removed
- Admin sessions endpoint GET /api/sessions"
git push origin main
```

Vercel redeploys automatically on push (if the project is connected
to this repo).

## 2. Vercel env vars (Dashboard → Project → Settings → Environment Variables)

Set these for **Production**, then redeploy:

| Variable | Value |
|---|---|
| `SECRET_KEY` | NEW long random string — generate with `openssl rand -hex 32`. **Must be new.** The old default was public in the code; old tokens will stop working, which is intended. |
| `DB_URI` | Your MongoDB Atlas connection string (same cluster as before is fine) |
| `ADMIN_KEY` | NEW long random string — `openssl rand -hex 32` |
| `BOT_API_KEY` | Optional. If set, the bot must send it as `X-Api-Key` to `POST /api/create-token`. |
| `CHROME_ONLY` | `true` (default) |
| `RATE_LIMIT_PER_MINUTE` | `10` (optional) |
| `RATE_LIMIT_PER_HOUR` | `70` (optional) |

## 3. Cloudflare Turnstile (free)

1. https://dash.cloudflare.com → Turnstile → Add site.
2. Widget type: **Managed**. Domain: your Vercel domain.
3. Copy Site Key → `TURNSTILE_SITE_KEY` and Secret Key →
   `TURNSTILE_SECRET_KEY` in Vercel, redeploy.
4. Until BOTH keys are set, Turnstile is skipped and the session is
   flagged `turnstile_skipped: true` — the site keeps working, the
   human check just isn't enforced yet.

## 4. Test after deploy

1. Create a token via the bot (or curl `POST /api/create-token`).
2. Open the verification link in **Chrome** — should show the
   countdown + math + Turnstile, then redirect to the shortener.
3. Open the same link again — should say "already been used".
4. Open it in **Brave** — should get the "open in Google Chrome" page.
5. Check sessions: `curl -H "X-Admin-Key: <ADMIN_KEY>" "https://<your-domain>/api/sessions?limit=5"`

## 5. Rollback

If anything breaks live, revert the push in GitHub (or
`git revert <commit> && git push`) — Vercel redeploys the old code.
The old tokens use the same HMAC format, so reverting also restores
the old `SECRET_KEY` behaviour only if you also restore the old
secret in Vercel; with a new `SECRET_KEY` set, old tokens will not
verify until the secret is restored.
