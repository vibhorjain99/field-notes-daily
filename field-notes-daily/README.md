# Field Notes Daily

A self-updating AI research dashboard. A GitHub Action runs every morning, fetches the latest arXiv preprints, top AI stories from Hacker News, and posts from a handful of research blogs, then commits a regenerated `docs/index.html`. GitHub Pages serves it for free.

You wake up. You open one URL. Yesterday's research is already there.

## What's in this repo

| File | Purpose |
|---|---|
| `fetch.py` | The builder. Fetches feeds, renders the page. |
| `template.html` | The HTML shell with `__FEED_DATA__` and `__GENERATED_AT__` placeholders. |
| `.github/workflows/daily.yml` | The cron job. Runs at 01:30 UTC = 07:00 IST. |
| `docs/index.html` | The generated page (this is what GitHub Pages serves). |

## Setup — 15 minutes, once

### 1. Create the repo

1. New repo on GitHub: `field-notes-daily` (or whatever name you want). Make it **public** — GitHub Pages and Actions are free for public repos.
2. Clone it locally, drop all these files in, commit, push.

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/field-notes-daily.git
git push -u origin main
```

### 2. Enable GitHub Pages

1. In your repo on GitHub: **Settings → Pages**.
2. Source: **Deploy from a branch**.
3. Branch: **main**, folder: **/docs**.
4. Save.

Within a minute, GitHub gives you a URL: `https://YOUR-USERNAME.github.io/field-notes-daily/`. Bookmark it. This is the URL you'll open every morning.

### 3. Let the Action run

The workflow has `workflow_dispatch` enabled, which means you can trigger it by hand the first time:

1. Go to **Actions → Daily Field Notes Build → Run workflow**.
2. Click the green "Run workflow" button.
3. Wait ~60 seconds. You'll see it fetch the feeds, then commit the generated page back to the repo.

After that, it runs automatically every morning at 01:30 UTC (07:00 IST). Adjust the cron line in `.github/workflows/daily.yml` if you want a different time — [crontab.guru](https://crontab.guru) explains the syntax.

### 4. (Optional) Get a notification when the build finishes

If you'd like an email or Slack ping when fresh content lands:

- **Email**: in your GitHub notification settings, enable "Actions" notifications. You'll get an email if a build fails, but not when it succeeds. For success-pings, add a `mail` step to the workflow.
- **Slack/Discord**: add a webhook step at the end of `daily.yml` that posts to your channel. Plenty of GitHub Action examples online.
- **Just a calendar event**: easiest of all — set a 7:05 AM recurring reminder on your phone titled "Field Notes" with the bookmark URL.

## Customizing

**Add more feeds.** Edit the `BLOG_FEEDS` list at the top of `fetch.py`. Any valid RSS or Atom URL works. Run the script locally (`python fetch.py`) to test before pushing.

**Change the cron time.** Edit `.github/workflows/daily.yml` — the line `cron: '30 1 * * *'` is UTC. Use [crontab.guru](https://crontab.guru) to convert your desired local time to UTC.

**Change the topic-tag heuristics.** The `TAG_RULES` dict in `fetch.py` is a regex per tag. Add keywords, add a fifth tag, whatever.

**Change the design.** Edit `template.html`. The `__FEED_DATA__` placeholder becomes the embedded JSON; the `__GENERATED_AT__` placeholder becomes a timestamp string. Everything else is yours.

## Running it locally

```bash
pip install feedparser requests
python fetch.py
# open docs/index.html in your browser
```

Useful for testing changes before pushing.

## Troubleshooting

**The Action ran but the page didn't update.** Check the Actions log. If it says "No changes to commit," all the feeds returned the same items as last build — that's fine, the page is unchanged. If a specific feed failed, the others still went through (the script catches per-feed errors so one bad RSS URL won't kill the build).

**GitHub Pages shows 404.** Pages can take a few minutes to publish on first setup. Double-check Settings → Pages shows your URL and "Your site is live."

**The Action isn't running on schedule.** GitHub disables scheduled workflows on repos with no activity for 60 days. Just push any commit and it re-enables.

**A feed is consistently empty.** Some RSS endpoints return JSON or block bot user agents. Open `fetch.py`, set `requests.get(url, headers={"User-Agent": "Mozilla/5.0"})` for that feed, or switch to `feedparser` which handles most of this automatically.

## Free-tier limits

- **GitHub Actions** on public repos: unlimited minutes. (Private repos: 2000 free min/month, this job uses ~30 sec.)
- **GitHub Pages**: 100 GB bandwidth/month, 1 GB storage. You'll never come close.

## What this teaches you

If you've never set up a CI/CD pipeline, this is the smallest useful one. The same pattern — *cron-triggered Action → script → commit → static hosting* — runs a huge slice of the internet's static dashboards, status pages, and personal sites. You can reuse it for: weather pages, finance trackers, sports scoreboards, anything that's a periodic fetch + render.

The script is intentionally boring Python — no fancy frameworks, no async, no Docker. Read it; it's 150 lines.
