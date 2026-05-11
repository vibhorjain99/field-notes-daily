"""
Field Notes — daily builder (v2)
Fetches RSS/Atom feeds + arXiv + Hacker News, renders docs/index.html.

Changes vs v1:
- Many more feeds: researchers, conferences, Substacks
- Per-source cap (no single blogger floods the page)
- Generates a build-summary text file for the email notification
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
SUMMARY_FILE = HERE / "build_summary.txt"  # consumed by the email step

MAX_PER_FEED = 20         # total items per feed column shown on the page
PER_SOURCE_CAP = 3        # blog column: max items per individual source

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

# Research labs & company blogs
LAB_FEEDS = [
    ("Google Research", "https://research.google/blog/rss/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    ("The Decoder", "https://the-decoder.com/feed/"),
]

# Individual researchers / writers — the dense, opinionated ones
RESEARCHER_FEEDS = [
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("Sebastian Raschka", "https://magazine.sebastianraschka.com/feed"),
    ("Nathan Lambert (Interconnects)", "https://www.interconnects.ai/feed"),
    ("Lil'Log (Lilian Weng)", "https://lilianweng.github.io/index.xml"),
    ("Andrej Karpathy", "https://karpathy.github.io/feed.xml"),
    # Daniel Han / Unsloth doesn't have a tracked blog feed; we use the
    # Unsloth blog as a proxy since Daniel writes a lot of it.
    ("Unsloth (Daniel Han)", "https://unsloth.ai/blog/rss.xml"),
]

# Substacks — long-form analysis
SUBSTACK_FEEDS = [
    ("Import AI (Jack Clark)", "https://importai.substack.com/feed"),
    ("AI Snake Oil", "https://www.aisnakeoil.com/feed"),
]

# Conferences — pulls arXiv listings tagged with the conference
# (We use arXiv for these since NeurIPS/ICML/ICLR don't expose RSS for accepted papers.)
CONF_QUERIES = [
    ("NeurIPS / ICML / ICLR (arXiv)",
     "https://export.arxiv.org/api/query?"
     "search_query=cat:cs.LG+AND+(abs:NeurIPS+OR+abs:ICML+OR+abs:ICLR)"
     "&sortBy=submittedDate&sortOrder=descending&max_results=10"),
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
    t = (text or "").lower()
    return [tag for tag, pattern in TAG_RULES.items() if re.search(pattern, t)]


def safe_date(struct_time) -> str:
    if not struct_time:
        return ""
    try:
        return datetime(*struct_time[:6]).strftime("%Y-%m-%d")
    except Exception:
        return ""


def parse_feed(name: str, url: str, cap: int = PER_SOURCE_CAP) -> list[dict]:
    """Generic Atom/RSS parser with per-source cap and tag inference."""
    items = []
    try:
        feed = feedparser.parse(url)
        count = 0
        for entry in feed.entries[:cap]:
            title = entry.title.strip() if hasattr(entry, "title") else ""
            link = entry.link if hasattr(entry, "link") else "#"
            date = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                date = safe_date(entry.published_parsed)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                date = safe_date(entry.updated_parsed)
            items.append({
                "id": f"src:{name}:{link[-50:]}",
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
    return items


# ---------------------------------------------------------------------------
# FETCHERS
# ---------------------------------------------------------------------------
def fetch_arxiv() -> list[dict]:
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


def fetch_conferences() -> list[dict]:
    items = []
    for name, url in CONF_QUERIES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.title.replace("\n", " ").strip()
                summary = (entry.summary if hasattr(entry, "summary") else "").replace("\n", " ")
                items.append({
                    "id": "conf:" + entry.id.split("/")[-1],
                    "title": title,
                    "url": entry.link,
                    "date": safe_date(entry.published_parsed) if hasattr(entry, "published_parsed") else "",
                    "source": name,
                    "tags": tag_text(title + " " + summary),
                })
            print(f"  {name}: {len([i for i in items if i['source']==name])} papers")
        except Exception as e:
            print(f"  {name} FAILED: {e}")
    return items


def fetch_hn() -> list[dict]:
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


def fetch_blogs_combined() -> dict:
    """Returns a dict with three blog buckets so the UI can show them separately."""
    labs, researchers, substacks = [], [], []
    for name, url in LAB_FEEDS:
        labs.extend(parse_feed(name, url))
    for name, url in RESEARCHER_FEEDS:
        researchers.extend(parse_feed(name, url))
    for name, url in SUBSTACK_FEEDS:
        substacks.extend(parse_feed(name, url))
    # Sort each bucket by date desc, then cap
    for bucket in (labs, researchers, substacks):
        bucket.sort(key=lambda x: x.get("date") or "", reverse=True)
    return {
        "labs": labs[:MAX_PER_FEED],
        "researchers": researchers[:MAX_PER_FEED],
        "substacks": substacks[:MAX_PER_FEED],
    }


# ---------------------------------------------------------------------------
# RENDER + SUMMARY
# ---------------------------------------------------------------------------
def render(data: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    json_blob = json.dumps(data, ensure_ascii=False)
    json_blob = json_blob.replace("</", "<\\/")
    template = template.replace("__FEED_DATA__", json_blob)
    template = template.replace(
        "__GENERATED_AT__",
        escape(datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC"))
    )
    return template


def write_summary(data: dict) -> None:
    """Plain-text digest used by the email notification step."""
    lines = []
    lines.append(f"Field Notes — daily build")
    lines.append(f"Built: {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}")
    lines.append("")

    def section(title, items, max_show=5):
        if not items:
            return
        lines.append(f"━━ {title} ({len(items)} total, showing {min(max_show, len(items))}) ━━")
        for it in items[:max_show]:
            lines.append(f"• {it['title']}")
            lines.append(f"  {it.get('source','')} · {it.get('date','')}")
            lines.append(f"  {it['url']}")
            lines.append("")

    section("ARXIV — TODAY'S TOP PREPRINTS", data.get("arxiv", []), 5)
    section("HACKER NEWS — TOP AI STORIES", data.get("hn", []), 5)
    section("RESEARCHERS", data.get("researchers", []), 4)
    section("LABS", data.get("labs", []), 3)
    section("SUBSTACKS", data.get("substacks", []), 3)
    section("CONFERENCES (NeurIPS/ICML/ICLR)", data.get("conferences", []), 3)

    lines.append("")
    lines.append("Open the dashboard for interactive features:")
    lines.append("(replace with your GitHub Pages URL after first deploy)")

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote summary: {SUMMARY_FILE}")


def main():
    print(f"Build started at {datetime.now(timezone.utc).isoformat()}")
    print("Fetching feeds:")
    arxiv = fetch_arxiv()
    hn = fetch_hn()
    blogs = fetch_blogs_combined()
    conferences = fetch_conferences()

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "arxiv": arxiv,
        "hn": hn,
        "labs": blogs["labs"],
        "researchers": blogs["researchers"],
        "substacks": blogs["substacks"],
        "conferences": conferences,
    }

    total = sum(len(data[k]) for k in ["arxiv", "hn", "labs", "researchers", "substacks", "conferences"])
    print(f"Total items: {total}")

    html = render(data)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(html):,} bytes)")

    write_summary(data)


if __name__ == "__main__":
    main()
