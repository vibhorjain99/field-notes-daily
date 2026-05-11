"""
Field Notes — daily builder
Fetches RSS/Atom feeds + arXiv + Hacker News, renders docs/index.html.

Runs on GitHub Actions every morning. Designed to be boring and reliable:
- Each feed has its own try/except so one failure doesn't kill the build.
- Items are tagged with topic labels for the front-end filter pills.
- The generated HTML embeds the data as JSON so the page loads instantly
  (no client-side fetching, no CORS proxies, no flicker).
"""

import feedparser
import requests
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from html import escape

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
TEMPLATE = HERE / "template.html"
OUTPUT = HERE / "docs" / "index.html"
MAX_PER_FEED = 15

# Topic-tag rules — same heuristic as the original dashboard.
# Lowercased keyword → list of tag IDs the front-end filter pills use.
TAG_RULES = {
    "llm": r"\b(llm|gpt|claude|gemini|llama|mistral|qwen|deepseek|language model|"
           r"transformer|fine-tun|rlhf|dpo|moe|mixture-of-experts|reasoning)\b",
    "multimodal": r"\b(vision|image|video|multimodal|clip|vlm|vqa|diffusion|"
                  r"stable diffusion|sora|midjourney|3d|world model)\b",
    "agents": r"\b(agent|tool use|reinforcement|\brl\b|reward|policy|browser|"
              r"autonomous|mcp|computer-use|orchestrat)\b",
    "applied": r"\b(deploy|production|inference|serving|latency|quantiz|"
               r"throughput|enterprise|industry|benchmark|eval|cost|gpu)\b",
}

# Blog/research feeds — easy to add more, just append a (name, url) tuple.
BLOG_FEEDS = [
    ("Google Research", "https://research.google/blog/rss/"),
    ("The Decoder", "https://the-decoder.com/feed/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
]

ARXIV_URL = (
    "https://export.arxiv.org/api/query?"
    "search_query=cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.AI"
    "&sortBy=submittedDate&sortOrder=descending&max_results=20"
)

HN_QUERIES = ["AI", "LLM", "GPT", "Claude", "agent"]
HN_URL = "https://hn.algolia.com/api/v1/search?query={q}&tags=story&hitsPerPage=8"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def tag_text(text: str) -> list[str]:
    """Return the topic tags that match in the given text."""
    t = (text or "").lower()
    return [tag for tag, pattern in TAG_RULES.items() if re.search(pattern, t)]


def safe_date(s: str) -> str:
    """Best-effort date parsing → YYYY-MM-DD, blank if it can't parse."""
    if not s:
        return ""
    try:
        # feedparser already normalizes most date strings into struct_time
        return datetime(*s[:6]).strftime("%Y-%m-%d")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# FETCHERS — each returns a list of dicts: {id, title, url, date, source, tags, meta?}
# Each is wrapped in try/except so a single broken feed doesn't kill the build.
# ---------------------------------------------------------------------------
def fetch_arxiv() -> list[dict]:
    """Pull the most recent cs.LG / cs.CL / cs.AI preprints from arXiv."""
    items = []
    try:
        feed = feedparser.parse(ARXIV_URL)
        for entry in feed.entries[:MAX_PER_FEED]:
            title = entry.title.replace("\n", " ").strip()
            summary = (entry.summary if hasattr(entry, "summary") else "").replace("\n", " ")
            items.append({
                "id": "arxiv:" + entry.id.split("/")[-1],
                "title": title,
                "url": entry.link,
                "date": safe_date(entry.published_parsed) if hasattr(entry, "published_parsed") else "",
                "source": "arXiv",
                "tags": tag_text(title + " " + summary),
            })
        print(f"  arXiv: {len(items)} entries")
    except Exception as e:
        print(f"  arXiv FAILED: {e}")
    return items


def fetch_hn() -> list[dict]:
    """Pull top AI-related Hacker News stories via Algolia's public API."""
    seen, items = set(), []
    try:
        for q in HN_QUERIES:
            r = requests.get(HN_URL.format(q=q), timeout=15)
            for hit in r.json().get("hits", []):
                oid = hit.get("objectID")
                if oid in seen:
                    continue
                seen.add(oid)
                title = hit.get("title") or ""
                items.append({
                    "id": "hn:" + oid,
                    "title": title,
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                    "date": (hit.get("created_at") or "")[:10],
                    "source": "Hacker News",
                    "tags": tag_text(title),
                    "meta": f"{hit.get('points', 0)} pts · {hit.get('num_comments', 0)} comments",
                    "_score": hit.get("points", 0),
                })
        items.sort(key=lambda x: x.get("_score", 0), reverse=True)
        items = items[:MAX_PER_FEED]
        for it in items:
            it.pop("_score", None)
        print(f"  HN: {len(items)} stories")
    except Exception as e:
        print(f"  HN FAILED: {e}")
    return items


def fetch_blogs() -> list[dict]:
    """Pull recent posts from research/industry blogs."""
    items = []
    for name, url in BLOG_FEEDS:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:4]:
                title = entry.title.strip() if hasattr(entry, "title") else ""
                link = entry.link if hasattr(entry, "link") else "#"
                date = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    date = safe_date(entry.published_parsed)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    date = safe_date(entry.updated_parsed)
                items.append({
                    "id": f"blog:{name}:{link[-40:]}",
                    "title": title,
                    "url": link,
                    "date": date,
                    "source": name,
                    "tags": tag_text(title),
                })
                count += 1
            print(f"  {name}: {count} posts")
        except Exception as e:
            print(f"  {name} FAILED: {e}")
    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    return items[:MAX_PER_FEED]


# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------
def render(arxiv: list, hn: list, blogs: list) -> str:
    """Read template.html and replace placeholders with JSON + timestamp."""
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "arxiv": arxiv,
        "hn": hn,
        "blogs": blogs,
    }
    # Embed as a JSON string assigned to window.__FEED_DATA__
    # — safer than templating individual fields and lets the page render instantly.
    json_blob = json.dumps(payload, ensure_ascii=False)
    # Escape </script> so a malicious title can't break out of the script tag
    json_blob = json_blob.replace("</", "<\\/")
    template = template.replace("__FEED_DATA__", json_blob)
    template = template.replace(
        "__GENERATED_AT__",
        escape(datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC"))
    )
    return template


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print(f"Build started at {datetime.now(timezone.utc).isoformat()}")
    print("Fetching feeds:")
    arxiv = fetch_arxiv()
    hn = fetch_hn()
    blogs = fetch_blogs()
    print(f"Total items: {len(arxiv) + len(hn) + len(blogs)}")

    html = render(arxiv, hn, blogs)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
