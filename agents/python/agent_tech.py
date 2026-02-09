#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
FinRo.ro — Agent 3: Tech Reviews Content Agent (Python)
═══════════════════════════════════════════════════════════════
Scrapes tech news, phone/laptop reviews, AI tools, software reviews
for the Tehnologie section.

Sources: ArenaIT.ro, Go4IT.ro, Playtech.ro, TechRadar RSS
Schedule: Daily via cron at 08:00 EET
Usage:    python3 agent_tech.py [--dry-run] [--max-articles 5]
"""

import os
import json
import hashlib
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

try:
    import requests
    from bs4 import BeautifulSoup
    import feedparser
    from slugify import slugify
except ImportError:
    os.system("pip install requests beautifulsoup4 feedparser python-slugify --break-system-packages -q")
    import requests
    from bs4 import BeautifulSoup
    import feedparser
    from slugify import slugify

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "website" / "articles" / "tech"
DATA_DIR = BASE_DIR / "website" / "data"
LOG_DIR = Path(__file__).resolve().parent / "logs"

for d in [OUTPUT_DIR, DATA_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "agent_tech.log"), logging.StreamHandler()],
)
log = logging.getLogger("TechAgent")

CONFIG = {"user_agent": "FinRo-Bot/1.0 (+https://finro.ro/bot)", "timeout": 15}

SOURCES = [
    {"id": "arenait", "name": "ArenaIT.ro", "rss": "https://arenait.ro/feed/", "type": "rss"},
    {"id": "go4it", "name": "Go4IT.ro", "rss": "https://www.go4it.ro/feed/", "type": "rss"},
    {"id": "playtech", "name": "Playtech.ro", "rss": "https://playtech.ro/feed/", "type": "rss"},
    {"id": "techradar", "name": "TechRadar", "rss": "https://www.techradar.com/rss", "type": "rss", "filter_keywords": ["review", "best", "vs", "comparison"]},
    {"id": "theverge", "name": "The Verge", "rss": "https://www.theverge.com/rss/reviews/index.xml", "type": "rss"},
]

SUBCATEGORIES = {
    "telefoane": ["telefon", "smartphone", "Samsung", "iPhone", "Pixel", "OnePlus", "Xiaomi", "Galaxy", "Motorola", "Nothing Phone", "POCO"],
    "laptopuri": ["laptop", "notebook", "MacBook", "ThinkPad", "Dell XPS", "ASUS", "Lenovo", "HP Pavilion", "ultrabook", "Chromebook"],
    "software": ["aplicație", "app", "software", "VPN", "antivirus", "Windows", "macOS", "Linux", "browser", "Chrome", "Firefox"],
    "ai": ["AI", "inteligență artificială", "ChatGPT", "Claude", "Gemini", "Copilot", "machine learning", "neural", "LLM", "GPT"],
    "accesorii": ["căști", "headphones", "earbuds", "smartwatch", "ceas inteligent", "tabletă", "monitor", "tastatură", "mouse"],
}


@dataclass
class Article:
    title: str
    slug: str
    url: str
    source_id: str
    source_name: str
    published: str
    summary: str
    content_html: str = ""
    subcategory: str = "general"
    meta_title: str = ""
    meta_description: str = ""
    meta_keywords: List[str] = field(default_factory=list)
    reading_time: int = 5
    author: str = "Echipa FinRo"
    hash_id: str = ""
    rating: str = ""  # For reviews: "8.5/10"


def detect_subcategory(text: str) -> str:
    text_lower = text.lower()
    scores = {cat: sum(1 for kw in kws if kw.lower() in text_lower) for cat, kws in SUBCATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def extract_rating(text: str) -> str:
    """Try to extract a review rating from text."""
    import re
    patterns = [
        r'(\d+\.?\d?)\s*/\s*10',
        r'rating[:\s]+(\d+\.?\d?)',
        r'scor[:\s]+(\d+\.?\d?)',
        r'(\d+\.?\d?)%',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if val <= 10:
                return f"{val}/10"
            elif val <= 100:
                return f"{val / 10:.1f}/10"
    return ""


def generate_meta(article: Article) -> Article:
    article.meta_title = (article.title[:57] + "..." if len(article.title) > 60 else article.title) + " | FinRo.ro"
    desc = article.summary or article.title
    article.meta_description = desc[:152] + "..." if len(desc) > 155 else desc

    base_kw = ["tehnologie", "recenzie", "2025"]
    cat_kw = SUBCATEGORIES.get(article.subcategory, [])[:4]
    article.meta_keywords = list(set(base_kw + cat_kw))
    word_count = len((article.summary + " " + article.content_html).split())
    article.reading_time = max(3, word_count // 200)
    article.hash_id = hashlib.md5(article.url.encode()).hexdigest()[:12]
    return article


def fetch_rss(source: dict) -> List[dict]:
    log.info(f"  Fetching: {source['name']}")
    try:
        resp = requests.get(source["rss"], headers={"User-Agent": CONFIG["user_agent"]}, timeout=CONFIG["timeout"])
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = []
        filter_kw = source.get("filter_keywords", [])

        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            summary = ""
            if hasattr(entry, "summary"):
                soup = BeautifulSoup(entry.summary, "html.parser")
                summary = soup.get_text(strip=True)[:500]

            if filter_kw:
                combined = f"{title} {summary}".lower()
                if not any(kw.lower() in combined for kw in filter_kw):
                    continue

            # Extract image if available
            image_url = ""
            if hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url", "")
            elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get("url", "")

            published = getattr(entry, "published", getattr(entry, "updated", ""))
            entries.append({
                "title": title, "url": entry.get("link", ""),
                "published": published, "summary": summary, "image_url": image_url,
            })

        log.info(f"  → {len(entries)} entries")
        return entries
    except Exception as e:
        log.error(f"  ✗ {source['name']}: {e}")
        return []


def scrape_content(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": CONFIG["user_agent"]}, timeout=CONFIG["timeout"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for sel in [".entry-content", ".article-content", ".post-content", "article"]:
            el = soup.select_one(sel)
            if el:
                paras = el.find_all("p")
                text = "\n\n".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                if len(text) > 100:
                    return text[:2500]
        return ""
    except Exception:
        return ""


def load_seen() -> set:
    f = DATA_DIR / "seen_tech.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")).get("hashes", []))
        except Exception:
            return set()
    return set()


def save_seen(hashes: set):
    f = DATA_DIR / "seen_tech.json"
    f.write_text(json.dumps({"hashes": list(hashes), "updated": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")


def save_article(article: Article):
    filepath = OUTPUT_DIR / f"{article.slug}.html"

    rating_badge = ""
    if article.rating:
        rating_badge = f'<span class="card__badge card__badge--review">⭐ {article.rating}</span>'

    html = f"""<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article.meta_title}</title>
    <meta name="description" content="{article.meta_description}">
    <meta name="keywords" content="{', '.join(article.meta_keywords)}">
    <meta property="og:title" content="{article.meta_title}">
    <meta property="og:description" content="{article.meta_description}">
    <meta property="og:type" content="article">
    <link rel="canonical" href="https://finro.ro/tech/{article.slug}">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": "{article.title}",
        "description": "{article.meta_description}",
        "author": {{"@type": "Person", "name": "{article.author}"}},
        "publisher": {{"@type": "Organization", "name": "FinRo.ro"}},
        "datePublished": "{article.published}",
        "articleSection": "Tehnologie - {article.subcategory.title()}"
    }}
    </script>
    <link rel="stylesheet" href="../../css/style.css">
</head>
<body>
    <div class="ad-slot ad-slot--top"><div class="ad-placeholder"><span class="ad-label">AD · 728×90</span></div></div>
    <main class="main"><div class="main__grid">
        <article class="article-page" itemscope itemtype="https://schema.org/TechArticle">
            <div class="article-page__header">
                <span class="card__category">⚡ {article.subcategory.upper()}</span>
                {rating_badge}
                <h1 itemprop="headline">{article.title}</h1>
                <div class="card__meta">
                    <span>{article.author}</span>
                    <time datetime="{article.published}">{article.published[:10]}</time>
                    <span>{article.reading_time} min citire</span>
                </div>
            </div>
            <div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD · 336×280</span></div></div>
            <div class="article-page__content" itemprop="articleBody">
                <p><strong>{article.summary}</strong></p>
                {''.join(f"<p>{p}</p>" for p in article.content_html.split(chr(10)+chr(10)) if p.strip())}
            </div>
            <p class="article-page__source">Sursă: <a href="{article.url}" target="_blank" rel="nofollow">{article.source_name}</a></p>
            <div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD · 728×90</span></div></div>
        </article>
        <aside class="sidebar">
            <div class="ad-slot ad-slot--sidebar"><div class="ad-placeholder"><span class="ad-label">AD · 300×250</span></div></div>
            <div class="ad-slot ad-slot--sidebar ad-slot--sticky"><div class="ad-placeholder"><span class="ad-label">AD · 300×600</span></div></div>
        </aside>
    </div></main>
</body>
</html>"""
    filepath.write_text(html, encoding="utf-8")
    log.info(f"  ✓ Saved: {article.slug}.html")

    meta = {
        "title": article.title, "slug": article.slug, "category": "tech",
        "subcategory": article.subcategory, "meta_title": article.meta_title,
        "meta_description": article.meta_description, "meta_keywords": article.meta_keywords,
        "author": article.author, "published": article.published,
        "reading_time": article.reading_time, "source": article.source_name,
        "rating": article.rating, "hash_id": article.hash_id, "url": f"/tech/{article.slug}",
    }
    (DATA_DIR / f"article_{article.hash_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def update_index():
    articles = []
    for f in sorted(DATA_DIR.glob("article_*.json"), reverse=True):
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
            if a.get("category") == "tech":
                articles.append(a)
        except Exception:
            continue
    idx = {"category": "tech", "total": len(articles), "updated": datetime.now(timezone.utc).isoformat(), "articles": articles[:50]}
    (DATA_DIR / "index_tech.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"  Index: {len(articles)} tech articles")


def run(max_articles=5, dry_run=False):
    log.info("=" * 60)
    log.info("FinRo Tech Agent — Starting")
    log.info("=" * 60)

    seen = load_seen()
    new_articles = []

    all_entries = []
    for source in SOURCES:
        entries = fetch_rss(source)
        for e in entries:
            e["source_id"] = source["id"]
            e["source_name"] = source["name"]
        all_entries.extend(entries)

    log.info(f"Total entries: {len(all_entries)}")

    for entry in all_entries:
        if not entry.get("title") or not entry.get("url"):
            continue
        url_hash = hashlib.md5(entry["url"].encode()).hexdigest()[:12]
        if url_hash in seen:
            continue

        text = f"{entry['title']} {entry.get('summary', '')}"
        article = Article(
            title=entry["title"], slug=slugify(entry["title"], max_length=80),
            url=entry["url"], source_id=entry["source_id"],
            source_name=entry["source_name"],
            published=entry.get("published", datetime.now(timezone.utc).isoformat()),
            summary=entry.get("summary", ""), subcategory=detect_subcategory(text), hash_id=url_hash,
        )

        if not dry_run:
            article.content_html = scrape_content(entry["url"])
            article.rating = extract_rating(f"{article.summary} {article.content_html}")

        article = generate_meta(article)
        new_articles.append(article)
        seen.add(url_hash)
        if len(new_articles) >= max_articles:
            break

    if not dry_run:
        for a in new_articles:
            save_article(a)
        save_seen(seen)
        update_index()
    else:
        for a in new_articles:
            log.info(f"  [DRY] {a.subcategory:12s} | {a.title[:60]}")

    log.info(f"Tech Agent complete. {len(new_articles)} articles.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinRo Tech Content Agent")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-articles", type=int, default=5)
    args = parser.parse_args()
    run(max_articles=args.max_articles, dry_run=args.dry_run)
