#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
FinRo.ro — Agent 1: Finance Content Agent (Python)
═══════════════════════════════════════════════════════════════
Scrapes Romanian finance news and generates SEO-optimized articles
for the Finanțe Personale section.

Sources: BNR, Ziarul Financiar, Profit.ro, Wall-Street.ro
Schedule: Daily via cron at 06:00 EET
Usage:    python3 agent_finance.py [--dry-run] [--max-articles 5]
Requirements: pip install requests beautifulsoup4 feedparser python-slugify
"""

import os
import sys
import json
import hashlib
import logging
import argparse
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from urllib.parse import urlparse

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

# ─── Paths ───
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "website" / "articles" / "finante"
DATA_DIR = BASE_DIR / "website" / "data"
LOG_DIR = Path(__file__).resolve().parent / "logs"

for d in [OUTPUT_DIR, DATA_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "agent_finance.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("FinanceAgent")

# ─── Config ───
CONFIG = {
    "user_agent": "FinRo-Bot/1.0 (+https://finro.ro/bot)",
    "timeout": 15,
    "max_articles": 5,
}

# ─── RSS Sources ───
SOURCES = [
    {
        "id": "bnr",
        "name": "Banca Națională a României",
        "rss": "https://www.bnr.ro/RSS_200.aspx",
        "type": "rss",
    },
    {
        "id": "zf",
        "name": "Ziarul Financiar",
        "rss": "https://www.zf.ro/rss",
        "type": "rss",
    },
    {
        "id": "profit",
        "name": "Profit.ro",
        "rss": "https://www.profit.ro/rss",
        "type": "rss",
    },
    {
        "id": "wall_street",
        "name": "Wall-Street.ro",
        "rss": "https://www.wall-street.ro/rss/economie.xml",
        "type": "rss",
    },
]

# ─── Subcategory keyword mapping ───
SUBCATEGORIES = {
    "credite": ["credit", "credite", "ipotecar", "imobiliar", "dobândă", "IRCC", "ROBOR", "împrumut", "bancă", "refinanțare", "prima casă", "noua casă"],
    "economisire": ["economii", "economisire", "depozit", "cont economii", "buget", "cheltuieli"],
    "investitii": ["investiți", "acțiuni", "obligațiuni", "ETF", "bursă", "BVB", "portofoliu", "dividend", "titluri de stat", "fond de investiții"],
    "taxe": ["taxe", "impozit", "ANAF", "declarația unică", "CAS", "CASS", "TVA", "fiscal", "PFA", "SRL"],
    "pensii": ["pensie", "pilonul", "fond de pensii", "CNPP", "punct de pensie", "vârstă de pensionare"],
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
    reading_time: int = 4
    author: str = "Echipa FinRo"
    image_url: str = ""
    hash_id: str = ""


def detect_subcategory(text: str) -> str:
    """Classify article into finance subcategory based on keyword matching."""
    text_lower = text.lower()
    scores = {}
    for cat, keywords in SUBCATEGORIES.items():
        scores[cat] = sum(1 for kw in keywords if kw.lower() in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def generate_meta(article: Article) -> Article:
    """Generate SEO metadata for the article."""
    # Meta title: max 60 chars
    article.meta_title = article.title[:57] + "..." if len(article.title) > 60 else article.title
    article.meta_title += " | FinRo.ro"

    # Meta description: max 155 chars
    desc = article.summary or article.title
    article.meta_description = desc[:152] + "..." if len(desc) > 155 else desc

    # Keywords from subcategory + extracted
    base_keywords = ["finanțe personale", "România", "2025"]
    cat_keywords = SUBCATEGORIES.get(article.subcategory, [])[:5]
    # Extract capitalized words as potential keywords
    title_words = [w for w in article.title.split() if len(w) > 3][:5]
    article.meta_keywords = list(set(base_keywords + cat_keywords + title_words))

    # Reading time estimate
    word_count = len((article.summary + " " + article.content_html).split())
    article.reading_time = max(2, word_count // 200)

    # Hash for dedup
    article.hash_id = hashlib.md5(article.url.encode()).hexdigest()[:12]

    return article


def fetch_rss_feed(source: dict) -> List[dict]:
    """Fetch and parse an RSS feed."""
    log.info(f"  Fetching RSS: {source['name']} — {source['rss']}")
    try:
        headers = {"User-Agent": CONFIG["user_agent"]}
        resp = requests.get(source["rss"], headers=headers, timeout=CONFIG["timeout"])
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = []
        for entry in feed.entries[:10]:
            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            summary = ""
            if hasattr(entry, "summary"):
                soup = BeautifulSoup(entry.summary, "html.parser")
                summary = soup.get_text(strip=True)[:500]

            entries.append({
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "published": published,
                "summary": summary,
            })
        log.info(f"  → Found {len(entries)} entries from {source['name']}")
        return entries
    except Exception as e:
        log.error(f"  ✗ Failed to fetch {source['name']}: {e}")
        return []


def scrape_article_content(url: str) -> str:
    """Attempt to scrape full article text from URL."""
    try:
        headers = {"User-Agent": CONFIG["user_agent"]}
        resp = requests.get(url, headers=headers, timeout=CONFIG["timeout"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try common article selectors
        selectors = [
            "article .entry-content",
            "article .post-content",
            ".article-body",
            ".article-content",
            ".entry-content",
            "article p",
            ".post-body",
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                paragraphs = el.find_all("p")
                text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                if len(text) > 100:
                    return text[:2000]

        # Fallback: grab all <p> in main/article
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if main:
            paragraphs = main.find_all("p")
            text = "\n\n".join(p.get_text(strip=True) for p in paragraphs[:10] if len(p.get_text(strip=True)) > 30)
            return text[:2000]

        return ""
    except Exception as e:
        log.warning(f"  Could not scrape content from {url}: {e}")
        return ""


def load_seen_hashes() -> set:
    """Load previously processed article hashes to avoid duplicates."""
    seen_file = DATA_DIR / "seen_finance.json"
    if seen_file.exists():
        try:
            data = json.loads(seen_file.read_text(encoding="utf-8"))
            return set(data.get("hashes", []))
        except Exception:
            return set()
    return set()


def save_seen_hashes(hashes: set):
    """Persist seen article hashes."""
    seen_file = DATA_DIR / "seen_finance.json"
    data = {"hashes": list(hashes), "updated": datetime.now(timezone.utc).isoformat()}
    seen_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_article_html(article: Article):
    """Save article as an HTML file with embedded metadata."""
    filename = f"{article.slug}.html"
    filepath = OUTPUT_DIR / filename

    html = f"""<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article.meta_title}</title>
    <meta name="description" content="{article.meta_description}">
    <meta name="keywords" content="{', '.join(article.meta_keywords)}">
    <meta name="author" content="{article.author}">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="{article.meta_title}">
    <meta property="og:description" content="{article.meta_description}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="https://finro.ro/finante/{article.slug}">
    <link rel="canonical" href="https://finro.ro/finante/{article.slug}">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "{article.title}",
        "description": "{article.meta_description}",
        "author": {{"@type": "Person", "name": "{article.author}"}},
        "publisher": {{"@type": "Organization", "name": "FinRo.ro"}},
        "datePublished": "{article.published}",
        "dateModified": "{datetime.now(timezone.utc).isoformat()}",
        "mainEntityOfPage": "https://finro.ro/finante/{article.slug}",
        "articleSection": "{article.subcategory}"
    }}
    </script>
    <link rel="stylesheet" href="../../css/style.css">
</head>
<body>
    <!-- Top Ad Slot -->
    <div class="ad-slot ad-slot--top" aria-label="Reclamă">
        <div class="ad-placeholder"><span class="ad-label">AD · 728×90 Leaderboard</span></div>
    </div>

    <main class="main">
        <div class="main__grid">
            <article class="article-page" itemscope itemtype="https://schema.org/Article">
                <div class="article-page__header">
                    <span class="card__category">{article.subcategory.title()}</span>
                    <h1 itemprop="headline">{article.title}</h1>
                    <div class="card__meta">
                        <span itemprop="author">{article.author}</span>
                        <time datetime="{article.published}" itemprop="datePublished">{article.published[:10]}</time>
                        <span>{article.reading_time} min citire</span>
                    </div>
                </div>

                <!-- In-article Ad -->
                <div class="ad-slot ad-slot--in-content" aria-label="Reclamă">
                    <div class="ad-placeholder"><span class="ad-label">AD · 336×280 In-Article</span></div>
                </div>

                <div class="article-page__content" itemprop="articleBody">
                    <p class="article-page__lead">{article.summary}</p>
                    {''.join(f"<p>{p}</p>" for p in article.content_html.split(chr(10)+chr(10)) if p.strip())}
                </div>

                <div class="article-page__source">
                    <p>Sursă: <a href="{article.url}" target="_blank" rel="nofollow noopener">{article.source_name}</a></p>
                </div>

                <!-- Post-article Ad -->
                <div class="ad-slot ad-slot--in-content" aria-label="Reclamă">
                    <div class="ad-placeholder"><span class="ad-label">AD · 728×90 Post-Article</span></div>
                </div>
            </article>

            <aside class="sidebar">
                <div class="ad-slot ad-slot--sidebar" aria-label="Reclamă">
                    <div class="ad-placeholder"><span class="ad-label">AD · 300×250</span></div>
                </div>
            </aside>
        </div>
    </main>

    <script src="../../js/main.js"></script>
</body>
</html>"""

    filepath.write_text(html, encoding="utf-8")
    log.info(f"  ✓ Saved: {filename}")
    return filepath


def save_article_json(article: Article):
    """Save article metadata as JSON for the frontend index."""
    meta = {
        "title": article.title,
        "slug": article.slug,
        "category": "finante",
        "subcategory": article.subcategory,
        "meta_title": article.meta_title,
        "meta_description": article.meta_description,
        "meta_keywords": article.meta_keywords,
        "author": article.author,
        "published": article.published,
        "reading_time": article.reading_time,
        "source": article.source_name,
        "source_url": article.url,
        "hash_id": article.hash_id,
        "url": f"/finante/{article.slug}",
    }
    json_path = DATA_DIR / f"article_{article.hash_id}.json"
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def update_index():
    """Rebuild the master articles index from individual JSON files."""
    articles = []
    for f in sorted(DATA_DIR.glob("article_*.json"), reverse=True):
        try:
            articles.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue

    index_path = DATA_DIR / "index_finante.json"
    index_data = {
        "category": "finante",
        "total": len(articles),
        "updated": datetime.now(timezone.utc).isoformat(),
        "articles": articles[:50],  # Keep latest 50
    }
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"  Index updated: {len(articles)} articles")


def run(max_articles: int = 5, dry_run: bool = False):
    """Main execution: fetch → process → generate → save."""
    log.info("=" * 60)
    log.info("FinRo.ro Finance Agent — Starting run")
    log.info(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    log.info(f"  Max articles: {max_articles}, Dry run: {dry_run}")
    log.info("=" * 60)

    seen = load_seen_hashes()
    new_articles = []

    # Phase 1: Fetch from all sources
    all_entries = []
    for source in SOURCES:
        entries = fetch_rss_feed(source)
        for entry in entries:
            entry["source_id"] = source["id"]
            entry["source_name"] = source["name"]
        all_entries.extend(entries)

    log.info(f"\nTotal entries fetched: {len(all_entries)}")

    # Phase 2: Process and deduplicate
    for entry in all_entries:
        if not entry.get("title") or not entry.get("url"):
            continue

        url_hash = hashlib.md5(entry["url"].encode()).hexdigest()[:12]
        if url_hash in seen:
            continue

        # Detect subcategory
        text = f"{entry['title']} {entry.get('summary', '')}"
        subcategory = detect_subcategory(text)

        # Create article
        article = Article(
            title=entry["title"],
            slug=slugify(entry["title"], max_length=80),
            url=entry["url"],
            source_id=entry["source_id"],
            source_name=entry["source_name"],
            published=entry.get("published", datetime.now(timezone.utc).isoformat()),
            summary=entry.get("summary", ""),
            subcategory=subcategory,
            hash_id=url_hash,
        )

        # Try to scrape full content
        if not dry_run:
            article.content_html = scrape_article_content(entry["url"])

        # Generate metadata
        article = generate_meta(article)

        new_articles.append(article)
        seen.add(url_hash)

        if len(new_articles) >= max_articles:
            break

    log.info(f"\nNew articles to process: {len(new_articles)}")

    # Phase 3: Save
    if not dry_run:
        for article in new_articles:
            save_article_html(article)
            save_article_json(article)
        save_seen_hashes(seen)
        update_index()
    else:
        for a in new_articles:
            log.info(f"  [DRY] {a.subcategory:12s} | {a.title[:60]}")

    log.info(f"\n{'='*60}")
    log.info(f"Finance Agent complete. Processed {len(new_articles)} articles.")
    log.info(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinRo Finance Content Agent")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--max-articles", type=int, default=5, help="Max articles per run")
    args = parser.parse_args()
    run(max_articles=args.max_articles, dry_run=args.dry_run)
