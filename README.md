# Field Notes Daily — v2

A self-updating AI research dashboard with progress tracking, optional cloud sync, and daily email digests.

**What's new in v2 (vs v1):**
- **Many more feeds**: Karpathy, Sebastian Raschka, Nathan Lambert, Lilian Weng, Daniel Han, Jack Clark, AI Snake Oil, plus NeurIPS/ICML/ICLR conference papers
- **Full interactive dashboard**: checkboxes on every resource, notes, streak counter, 12-question quiz, command palette, saved-items list
- **Optional cross-device sync** via a tiny Cloudflare Worker (free tier covers ~100k requests/day; you'll use ~10)
- **Optional daily email digest** when a new build completes

The progress, notes, and streak data all live in browser `localStorage` by default — they're untouched when the daily rebuild commits the new feeds, so nothing gets wiped. Cloud sync is only needed if you want the same progress on phone *and* laptop.

## File layout

```
field-notes-daily/
├── .github/workflows/
│   └── daily.yml              # Cron job: build feeds + commit + optional email
├── docs/
│   └── index.html             # Generated page (GitHub Pages serves this)
├── worker/                    # Optional Cloudflare Worker for sync
│   ├── index.js
│   └── wrangler.toml
├── fetch.py                   # Builder
├── template.html              # HTML template with __FEED_DATA__ placeholder
├── build_summary.txt          # Generated text digest, used by email step
└── README.md
```

## Step 1 — Upgrade your existing repo (5 min)

You already have v1 deployed. To upgrade:

1. **Replace these 3 files** in your repo with the new versions:
   - `fetch.py`
   - `template.html`
   - `.github/workflows/daily.yml`

2. **Add 2 new files**:
   - `worker/index.js`
   - `worker/wrangler.toml`

3. Commit and push.

4. Trigger a manual build: **Actions → Daily Field Notes Build → Run workflow**.

5. Visit your site. You should see the new interactive dashboard with today's feeds. Try clicking ☐ on a resource, then refresh — your check survives. That's localStorage doing its job.

The rebuild does NOT wipe your progress because:
- All progress lives in browser `localStorage`, keyed by your domain.
- The rebuild only regenerates `docs/index.html`'s embedded feed data.
- Your localStorage state is loaded *after* the HTML loads.

## Step 2 — (Optional) Cloud sync via Cloudflare Workers (10 min)

Cloudflare Workers + KV give you a free serverless backend that stores ~256 KB of JSON per "sync code." Your progress follows you across devices.

### One-time Cloudflare setup

1. **Sign up at [dash.cloudflare.com](https://dash.cloudflare.com)** — free, no credit card.

2. **Install Wrangler** (Cloudflare's CLI) on your laptop:
   ```bash
   npm install -g wrangler
   ```
   (Need Node.js installed. On Ubuntu: `sudo apt install nodejs npm`. On Mac: `brew install node`.)

3. **Log in**:
   ```bash
   wrangler login
   ```
   It opens your browser; click "Allow."

4. **`cd` into the `worker/` directory** in your repo clone.

5. **Create the KV namespace** that will store your state:
   ```bash
   wrangler kv namespace create STATE_KV
   ```
   It prints something like:
   ```
   ✨ Add the following to your configuration file:
   [[kv_namespaces]]
   binding = "STATE_KV"
   id = "a1b2c3d4e5f6..."
   ```

6. **Open `worker/wrangler.toml`** and replace `REPLACE_ME_WITH_NAMESPACE_ID_FROM_WRANGLER` with the `id` value from the previous step. Save.

7. **Deploy**:
   ```bash
   wrangler deploy
   ```
   It prints your Worker URL: something like `https://field-notes-sync.your-name.workers.dev`. Copy it.

8. **Open your dashboard** → click the **"SYNC: OFF"** button in the top right → paste the worker URL and pick a sync code (8+ characters, something memorable). Click "enable & push now."

9. The button now reads **"SYNC: ✓"**. Open the dashboard on your phone, hit the same sync button, paste the same URL and same code → your progress appears.

**About the "sync code":** it's a shared password between your devices. Pick something you'll remember but not obvious. Anyone with the code can read/write your progress, so don't use `password123`. The Worker enforces 8+ characters and 256 KB max body. You can use the same code across devices, or have different codes for different "profiles."

### Cloudflare free-tier limits

- **Workers**: 100,000 requests/day. You'll use ~20.
- **KV**: 100,000 reads/day, 1,000 writes/day, 1 GB storage. You'll use ~10 writes/day.
- You won't pay anything.

## Step 3 — (Optional) Daily email digest (5 min)

After each build, get a plain-text email listing today's top AI items.

### One-time Gmail setup

1. **Enable 2-Step Verification** on your Google account if you haven't: [myaccount.google.com/security](https://myaccount.google.com/security) → "How you sign in to Google" → 2-Step Verification.

2. **Create an App Password**: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → name it "Field Notes" → click "Create." You'll get a 16-character password like `abcd efgh ijkl mnop`. Copy it (you won't see it again).

### Add the secrets to GitHub

1. **In your repo → Settings → Secrets and variables → Actions → New repository secret.**
2. Add three secrets:
   - **Name:** `MAIL_USERNAME` · **Value:** your full Gmail address (e.g. `you@gmail.com`)
   - **Name:** `MAIL_PASSWORD` · **Value:** the 16-character app password from step 2 (spaces OK)
   - **Name:** `MAIL_TO` · **Value:** where to send the digest (often the same as `MAIL_USERNAME`)

3. **Trigger a manual build**: Actions → Daily Field Notes Build → Run workflow. Wait ~60 seconds.

4. **Check your inbox.** Subject line: "Field Notes — daily AI digest · #N." Body is the same digest you'd see on the dashboard's Live Wire.

If the email secrets aren't set, the email step is skipped automatically — no error, the rest of the workflow runs fine.

### Use a different provider?

Edit the `Send daily digest email` step in `.github/workflows/daily.yml`. The `dawidd6/action-send-mail@v3` action supports any SMTP server:
- **Outlook/Hotmail**: `smtp.office365.com`, port 587, `secure: false`
- **Yahoo**: `smtp.mail.yahoo.com`, port 465, `secure: true`
- **SendGrid**: `smtp.sendgrid.net`, username `apikey`, password is your API key
- **AWS SES**: use the SES SMTP credentials

## Maintenance & customization

**Add more feeds.** Edit the `LAB_FEEDS`, `RESEARCHER_FEEDS`, or `SUBSTACK_FEEDS` lists in `fetch.py`. Each is a `(name, url)` tuple.

**Change the cron time.** Edit `cron: '30 1 * * *'` in `daily.yml`. The line is UTC; use [crontab.guru](https://crontab.guru) to convert from your timezone.

**Test changes locally before pushing.**
```bash
pip install feedparser requests
python fetch.py
# open docs/index.html in your browser
```

**A feed went silent.** Some RSS endpoints rotate URLs or block bots. Open `fetch.py`, find the `parse_feed` function, and either remove the feed or add a `headers={"User-Agent": "Mozilla/5.0"}` argument. Per-feed errors are caught — one bad URL won't kill the build.

## Troubleshooting

**The dashboard shows old feed data even after a build.** Browser cache. Hard-refresh: Ctrl+Shift+R (Linux/Windows), Cmd+Shift+R (Mac).

**Sync button shows "SYNC: ERR".** The Worker URL is wrong or unreachable. Open the URL in a new tab — you should see a JSON response. If you get a 404 or "Worker not found," double-check `wrangler deploy` succeeded.

**Email never arrives.** Most common: wrong app password. Re-create one. Second most common: Gmail's "Less secure app access" was off (you bypass this with the app password). Third: check spam.

**My progress disappeared.** localStorage is per-browser, per-domain. If you switched browsers, used incognito, or cleared site data, it's gone. Cloud sync prevents this — it's the main reason to set it up.

## What this is, philosophically

This is the minimum viable "personal cloud" pattern:
- **Static page** for the UI (zero hosting cost, infinite scale).
- **Tiny serverless function** for the bits that need a backend (basically free).
- **GitHub Actions** as the scheduler.

You can apply the same shape to dozens of personal tools: a habit tracker, a reading list, a workout log, a weather page that texts you when it's about to rain.
