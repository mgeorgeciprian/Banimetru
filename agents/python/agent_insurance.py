#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
FinRo.ro — Agent 2: Insurance Content Agent (Python)
═══════════════════════════════════════════════════════════════
Scrapes Romanian insurance news and generates SEO-optimized articles
for the Asigurări section. Covers RCA, CASCO, health, travel, home.

Sources: ASF.ro, 1asig.ro, Xprimm.ro, Ziarul Financiar (asigurări)
Schedule: Daily via cron at 07:00 EET
Usage:    python3 agent_insurance.py [--dry-run] [--max-articles 5]
"""

import os
import sys
import json
import hashlib
import logging
import argparse
import re
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

# ─── Paths ───
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "website" / "articles" / "asigurari"
DATA_DIR = BASE_DIR / "website" / "data"
LOG_DIR = Path(__file__).resolve().parent / "logs"

for d in [OUTPUT_DIR, DATA_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "agent_insurance.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("InsuranceAgent")

CONFIG = {
    "user_agent": "FinRo-Bot/1.0 (+https://finro.ro/bot)",
    "timeout": 15,
    "max_articles": 5,
}

SOURCES = [
    {
        "id": "asf",
        "name": "ASF - Autoritatea de Supraveghere Financiară",
        "url": "https://asfromania.ro/ro/a/1/informatii-publice/comunicate",
        "type": "scrape",
        "selector": ".view-content .views-row",
    },
    {
        "id": "1asig",
        "name": "1asig.ro",
        "rss": "https://www.1asig.ro/rss/",
        "type": "rss",
    },
    {
        "id": "xprimm",
        "name": "XPRIMM",
        "url": "https://www.xprimm.com/Romania/",
        "type": "scrape",
        "selector": ".news-list .news-item",
    },
    {
        "id": "zf_asig",
        "name": "Ziarul Financiar - Asigurări",
        "rss": "https://www.zf.ro/rss",
        "type": "rss",
        "filter_keywords": ["asigur", "RCA", "CASCO", "poliț"],
    },
]

SUBCATEGORIES = {
    "rca": ["RCA", "asigurare auto", "obligatorie auto", "daune auto", "poliță auto", "asigurător auto", "despăgubire auto", "BAAR"],
    "casco": ["CASCO", "miniCASCO", "asigurare facultativă", "avarie", "furt auto", "decontare directă"],
    "sanatate": ["asigurare sănătate", "medical", "asigurare privată sănătate", "spitalizare", "diagnostic"],
    "calatorie": ["asigurare călătorie", "travel", "asistență rutieră", "carte verde", "asigurare vacanță"],
    "locuinta": ["asigurare locuință", "PAD", "PAID", "inundații", "cutremur", "asigurare casă"],
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
    hash_id: str = ""


def detect_subcategory(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for cat, keywords in SUBCATEGORIES.items():
        scores[cat] = sum(1 for kw in keywords if kw.lower() in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def generate_meta(article: Article) -> Article:
    article.meta_title = (article.title[:57] + "..." if len(article.title) > 60 else article.title) + " | FinRo.ro"
    desc = article.summary or article.title
    article.meta_description = desc[:152] + "..." if len(desc) > 155 else desc
    base_kw = ["asigurări", "România", "2025"]
    cat_kw = SUBCATEGORIES.get(article.subcategory, [])[:4]
    article.meta_keywords = list(set(base_kw + cat_kw))
    word_count = len((article.summary + " " + article.content_html).split())
    article.reading_time = max(2, word_count // 200)
    article.hash_id = hashlib.md5(article.url.encode()).hexdigest()[:12]
    return article


def fetch_rss(source: dict) -> List[dict]:
    log.info(f"  Fetching RSS: {source['name']}")
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

            # Apply keyword filter if present
            if filter_kw:
                combined = f"{title} {summary}".lower()
                if not any(kw.lower() in combined for kw in filter_kw):
                    continue

            published = getattr(entry, "published", getattr(entry, "updated", ""))
            entries.append({
                "title": title,
                "url": entry.get("link", ""),
                "published": published,
                "summary": summary,
            })

        log.info(f"  → {len(entries)} entries from {source['name']}")
        return entries
    except Exception as e:
        log.error(f"  ✗ Failed: {source['name']}: {e}")
        return []


def scrape_page(source: dict) -> List[dict]:
    log.info(f"  Scraping: {source['name']}")
    try:
        resp = requests.get(source["url"], headers={"User-Agent": CONFIG["user_agent"]}, timeout=CONFIG["timeout"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        entries = []
        items = soup.select(source["selector"])[:10]

        for item in items:
            link = item.find("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(source["url"], href)

            summary_el = item.find("p") or item.find(".summary") or item.find(".description")
            summary = summary_el.get_text(strip=True)[:500] if summary_el else ""

            entries.append({
                "title": title,
                "url": href,
                "published": datetime.now(timezone.utc).isoformat(),
                "summary": summary,
            })

        log.info(f"  → {len(entries)} entries from {source['name']}")
        return entries
    except Exception as e:
        log.error(f"  ✗ Failed: {source['name']}: {e}")
        return []


def scrape_content(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": CONFIG["user_agent"]}, timeout=CONFIG["timeout"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for sel in ["article .entry-content", ".article-body", ".article-content", "article p"]:
            el = soup.select_one(sel)
            if el:
                paras = el.find_all("p")
                text = "\n\n".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                if len(text) > 100:
                    return text[:2000]
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if main:
            paras = main.find_all("p")
            return "\n\n".join(p.get_text(strip=True) for p in paras[:10] if len(p.get_text(strip=True)) > 30)[:2000]
        return ""
    except Exception:
        return ""


def load_seen() -> set:
    f = DATA_DIR / "seen_insurance.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")).get("hashes", []))
        except Exception:
            return set()
    return set()


def save_seen(hashes: set):
    f = DATA_DIR / "seen_insurance.json"
    f.write_text(json.dumps({"hashes": list(hashes), "updated": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")


def save_article(article: Article):
    """Save article HTML with AdSense slots and structured data."""
    filepath = OUTPUT_DIR / f"{article.slug}.html"
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
    <link rel="canonical" href="https://finro.ro/asigurari/{article.slug}">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "{article.title}",
        "description": "{article.meta_description}",
        "author": {{"@type": "Person", "name": "{article.author}"}},
        "publisher": {{"@type": "Organization", "name": "FinRo.ro"}},
        "datePublished": "{article.published}",
        "articleSection": "Asigurări - {article.subcategory.title()}"
    }}
    </script>
    <link rel="stylesheet" href="../../css/style.css">
</head>
<body>
    <div class="ad-slot ad-slot--top"><div class="ad-placeholder"><span class="ad-label">AD · 728×90</span></div></div>
    <main class="main"><div class="main__grid">
        <article class="article-page" itemscope itemtype="https://schema.org/Article">
            <div class="article-page__header">
                <span class="card__category">🛡️ {article.subcategory.upper()}</span>
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

    # Save JSON metadata
    meta = {
        "title": article.title, "slug": article.slug, "category": "asigurari",
        "subcategory": article.subcategory, "meta_title": article.meta_title,
        "meta_description": article.meta_description, "meta_keywords": article.meta_keywords,
        "author": article.author, "published": article.published,
        "reading_time": article.reading_time, "source": article.source_name,
        "hash_id": article.hash_id, "url": f"/asigurari/{article.slug}",
    }
    (DATA_DIR / f"article_{article.hash_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def update_index():
    articles = []
    for f in sorted(DATA_DIR.glob("article_*.json"), reverse=True):
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
            if a.get("category") == "asigurari":
                articles.append(a)
        except Exception:
            continue
    index = {"category": "asigurari", "total": len(articles), "updated": datetime.now(timezone.utc).isoformat(), "articles": articles[:50]}
    (DATA_DIR / "index_asigurari.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"  Index updated: {len(articles)} insurance articles")


def run(max_articles=5, dry_run=False):
    log.info("=" * 60)
    log.info("FinRo Insurance Agent — Starting")
    log.info("=" * 60)

    seen = load_seen()
    new_articles = []
    all_entries = []

    for source in SOURCES:
        if source["type"] == "rss":
            entries = fetch_rss(source)
        else:
            entries = scrape_page(source)
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
            source_name=entry["source_name"], published=entry.get("published", datetime.now(timezone.utc).isoformat()),
            summary=entry.get("summary", ""), subcategory=detect_subcategory(text), hash_id=url_hash,
        )
        if not dry_run:
            article.content_html = scrape_content(entry["url"])
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

    log.info(f"Insurance Agent complete. {len(new_articles)} articles processed.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinRo Insurance Content Agent")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-articles", type=int, default=5)
    args = parser.parse_args()
    run(max_articles=args.max_articles, dry_run=args.dry_run)
