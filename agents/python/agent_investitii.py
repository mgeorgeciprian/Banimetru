#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
FinRo.ro — Agent 4: Investitii Content Agent (Python)
═══════════════════════════════════════════════════════════════
Scrapes international finance news, ETF/BVB data, Romanian real estate
projects, and corporate investments for the Investitii section.

Sources: Reuters, Bloomberg RSS, BVB, Romania-Insider, Imobiliare.ro,
         Business Review, EY Romania
Schedule: Daily via cron at 09:00 EET
Usage:    python3 agent_investitii.py [--dry-run] [--max-articles 8]
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
OUTPUT_DIR = BASE_DIR / "website" / "articles" / "investitii"
DATA_DIR = BASE_DIR / "website" / "data"
LOG_DIR = Path(__file__).resolve().parent / "logs"

for d in [OUTPUT_DIR, DATA_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "agent_investitii.log"), logging.StreamHandler()],
)
log = logging.getLogger("InvestitiiAgent")

CONFIG = {"user_agent": "FinRo-Bot/1.0 (+https://finro.ro/bot)", "timeout": 15}

# ─── RSS & Scraping Sources ───
SOURCES = [
    # International Finance
    {"id": "reuters_biz", "name": "Reuters Business", "rss": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best", "type": "rss"},
    {"id": "ft_markets", "name": "Financial Times Markets", "rss": "https://www.ft.com/rss/markets", "type": "rss"},
    {"id": "investing_ro", "name": "Investing.com Romania", "rss": "https://ro.investing.com/rss/news.rss", "type": "rss"},
    
    # BVB / ETF Romania
    {"id": "bvb_news", "name": "BVB News", "url": "https://bvb.ro/FinancialInstruments/SelectedData/NewsItem", "type": "scrape", "selector": ".news-list .news-item, .dataTable tr"},
    {"id": "romania_insider_biz", "name": "Romania Insider Business", "rss": "https://www.romania-insider.com/feed", "type": "rss", "filter_keywords": ["ETF", "BVB", "investit", "actiuni", "fond", "bursa", "stock", "bond", "obligatiuni"]},
    {"id": "zf_burse", "name": "Ziarul Financiar - Burse", "rss": "https://www.zf.ro/rss", "type": "rss", "filter_keywords": ["BVB", "ETF", "bursa", "actiuni", "investit", "fond", "BET"]},
    
    # Real Estate / Imobiliare
    {"id": "ri_realestate", "name": "Romania Insider Real Estate", "rss": "https://www.romania-insider.com/feed", "type": "rss", "filter_keywords": ["real estate", "imobiliar", "apartament", "rezidential", "dezvoltator", "proiect", "constructi", "Coresi", "AFI", "One United", "IULIUS", "Speedwell"]},
    {"id": "business_review", "name": "Business Review Property", "rss": "https://business-review.eu/feed", "type": "rss", "filter_keywords": ["property", "real estate", "residential", "office", "logistics", "developer", "imobiliar", "Cluj", "Brasov", "Timisoara", "Bucuresti"]},
    
    # Corporate Investments / FDI
    {"id": "ri_corporate", "name": "Romania Insider Corporate", "rss": "https://www.romania-insider.com/feed", "type": "rss", "filter_keywords": ["investit", "fabrica", "factory", "milioane euro", "million", "FDI", "corporat", "Knauf", "Continental", "Stada", "Bosch", "Mercedes", "Ford"]},
    {"id": "profit_invest", "name": "Profit.ro Investitii", "rss": "https://www.profit.ro/rss", "type": "rss", "filter_keywords": ["investit", "fabrica", "proiect", "milioane", "corporat", "strain"]},
]

# ─── Subcategories ───
SUBCATEGORIES = {
    "finante_internationale": [
        "global", "international", "Fed", "BCE", "ECB", "inflatie", "inflation",
        "dollar", "euro", "tariff", "trade war", "recession", "GDP", "PIB",
        "S&P 500", "Dow Jones", "NASDAQ", "emerging markets", "crypto", "bitcoin",
        "oil", "petrol", "commodities", "gold", "aur"
    ],
    "etf_bvb": [
        "ETF", "BVB", "BET", "bursa", "stock exchange", "actiuni", "shares",
        "fond investitii", "TVBETETF", "BKBETETF", "InterCapital", "Patria",
        "obligatiuni", "bonds", "titluri de stat", "Hidroelectrica", "OMV Petrom",
        "Banca Transilvania", "Romgaz", "Nuclearelectrica", "dividend",
        "portofoliu", "randament", "yield"
    ],
    "imobiliare": [
        "imobiliar", "real estate", "apartament", "rezidential", "dezvoltator",
        "developer", "constructi", "proiect", "Coresi", "AFI", "One United",
        "IULIUS", "Speedwell", "NEPI", "Globalworth", "WDP", "logistic",
        "birouri", "office", "retail", "mall", "hotel", "mixed-use",
        "Brasov", "Cluj", "Timisoara", "Bucuresti", "Bucharest", "Oradea",
        "Sibiu", "Iasi", "pret", "price", "chirii", "rent"
    ],
    "investitii_corporative": [
        "investit", "fabrica", "factory", "plant", "FDI", "corporat",
        "multinational", "strain", "foreign", "milioane euro", "million",
        "Continental", "Bosch", "Mercedes", "Ford", "Knauf", "Stada",
        "Renault", "Dacia", "Nokia", "Oracle", "Amazon", "Google",
        "Microsoft", "Kaufland", "Lidl", "Dedeman", "locuri de munca", "jobs"
    ],
}

# ─── Romanian Cities of Interest ───
CITIES = {
    "brasov": ["Brasov", "Brașov", "Coresi", "AFI Park Brasov", "Ghimbav", "Tractorul"],
    "bucuresti": ["Bucuresti", "București", "Bucharest", "Ilfov", "One United", "Floreasca", "Pipera", "Baneasa"],
    "timisoara": ["Timisoara", "Timișoara", "Iulius Town", "Paltim", "Continental Timisoara"],
    "cluj": ["Cluj", "Cluj-Napoca", "RIVUS", "Iulius Mall Cluj", "Borhanci", "Sophia"],
    "emergente": ["Oradea", "Sibiu", "Iasi", "Iași", "Constanta", "Constanța", "Craiova", "Arad", "Alba Iulia"],
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
    city_tags: List[str] = field(default_factory=list)
    meta_title: str = ""
    meta_description: str = ""
    meta_keywords: List[str] = field(default_factory=list)
    reading_time: int = 5
    author: str = "Echipa FinRo"
    hash_id: str = ""


def detect_subcategory(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for cat, keywords in SUBCATEGORIES.items():
        scores[cat] = sum(1 for kw in keywords if kw.lower() in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def detect_cities(text: str) -> List[str]:
    """Tag article with relevant Romanian cities."""
    text_lower = text.lower()
    found = []
    for city_key, keywords in CITIES.items():
        if any(kw.lower() in text_lower for kw in keywords):
            found.append(city_key)
    return found


def generate_meta(article: Article) -> Article:
    article.meta_title = (article.title[:57] + "..." if len(article.title) > 60 else article.title) + " | FinRo.ro"
    desc = article.summary or article.title
    article.meta_description = desc[:152] + "..." if len(desc) > 155 else desc
    
    base_kw = ["investitii", "Romania", "2026"]
    cat_kw = SUBCATEGORIES.get(article.subcategory, [])[:5]
    city_kw = article.city_tags[:3]
    article.meta_keywords = list(set(base_kw + cat_kw + city_kw))
    
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

        for entry in feed.entries[:20]:
            title = entry.get("title", "").strip()
            summary = ""
            if hasattr(entry, "summary"):
                soup = BeautifulSoup(entry.summary, "html.parser")
                summary = soup.get_text(strip=True)[:500]

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

        log.info(f"  -> {len(entries)} entries from {source['name']}")
        return entries
    except Exception as e:
        log.error(f"  X Failed: {source['name']}: {e}")
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
            summary_el = item.find("p") or item.find(".summary")
            summary = summary_el.get_text(strip=True)[:500] if summary_el else ""
            entries.append({
                "title": title, "url": href,
                "published": datetime.now(timezone.utc).isoformat(),
                "summary": summary,
            })
        log.info(f"  -> {len(entries)} entries from {source['name']}")
        return entries
    except Exception as e:
        log.error(f"  X Failed: {source['name']}: {e}")
        return []


def scrape_content(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": CONFIG["user_agent"]}, timeout=CONFIG["timeout"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for sel in [".entry-content", ".article-content", ".article-body", ".post-content", "article"]:
            el = soup.select_one(sel)
            if el:
                paras = el.find_all("p")
                text = "\n\n".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                if len(text) > 100:
                    return text[:3000]
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if main:
            paras = main.find_all("p")
            return "\n\n".join(p.get_text(strip=True) for p in paras[:12] if len(p.get_text(strip=True)) > 30)[:3000]
        return ""
    except Exception:
        return ""


def load_seen() -> set:
    f = DATA_DIR / "seen_investitii.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")).get("hashes", []))
        except Exception:
            return set()
    return set()


def save_seen(hashes: set):
    f = DATA_DIR / "seen_investitii.json"
    f.write_text(json.dumps({"hashes": list(hashes), "updated": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")


def get_subcategory_icon(subcat: str) -> str:
    icons = {
        "finante_internationale": "\U0001F30D",
        "etf_bvb": "\U0001F4C8",
        "imobiliare": "\U0001F3D7",
        "investitii_corporative": "\U0001F3ED",
    }
    return icons.get(subcat, "\U0001F4B0")


def get_subcategory_label(subcat: str) -> str:
    labels = {
        "finante_internationale": "Finante Internationale",
        "etf_bvb": "ETF & BVB",
        "imobiliare": "Imobiliare",
        "investitii_corporative": "Investitii Corporative",
    }
    return labels.get(subcat, "Investitii")


def save_article(article: Article):
    filepath = OUTPUT_DIR / f"{article.slug}.html"
    icon = get_subcategory_icon(article.subcategory)
    label = get_subcategory_label(article.subcategory)
    city_badges = "".join(f'<span class="card__badge card__badge--city">{c.title()}</span>' for c in article.city_tags)

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
    <link rel="canonical" href="https://finro.ro/investitii/{article.slug}">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "{article.title}",
        "description": "{article.meta_description}",
        "author": {{"@type": "Person", "name": "{article.author}"}},
        "publisher": {{"@type": "Organization", "name": "FinRo.ro"}},
        "datePublished": "{article.published}",
        "articleSection": "Investitii - {label}"
    }}
    </script>
    <link rel="stylesheet" href="../../css/style.css">
</head>
<body>
    <div class="ad-slot ad-slot--top"><div class="ad-placeholder"><span class="ad-label">AD 728x90</span></div></div>
    <main class="main"><div class="main__grid">
        <article class="article-page" itemscope itemtype="https://schema.org/Article">
            <div class="article-page__header">
                <span class="card__category">{icon} {label.upper()}</span>
                {city_badges}
                <h1 itemprop="headline">{article.title}</h1>
                <div class="card__meta">
                    <span>{article.author}</span>
                    <time datetime="{article.published}">{article.published[:10]}</time>
                    <span>{article.reading_time} min citire</span>
                </div>
            </div>
            <div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD 336x280</span></div></div>
            <div class="article-page__content" itemprop="articleBody">
                <p><strong>{article.summary}</strong></p>
                {''.join(f"<p>{para}</p>" for para in article.content_html.split(chr(10)+chr(10)) if para.strip())}
            </div>
            <p class="article-page__source">Sursa: <a href="{article.url}" target="_blank" rel="nofollow">{article.source_name}</a></p>
            <div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD 728x90</span></div></div>
        </article>
        <aside class="sidebar">
            <div class="ad-slot ad-slot--sidebar"><div class="ad-placeholder"><span class="ad-label">AD 300x250</span></div></div>
            <div class="widget widget--etf">
                <h3>ETF-uri BVB Populare</h3>
                <ul>
                    <li><strong>TVBETETF</strong> - ETF BET Patria-TradeVille (RON 809M)</li>
                    <li><strong>PTENGETF</strong> - ETF Energie Patria</li>
                    <li><strong>BKBETETF</strong> - ETF BET BRK</li>
                    <li><strong>ICBETNETF</strong> - InterCapital BET-TRN</li>
                </ul>
            </div>
            <div class="widget widget--cities">
                <h3>Orase Monitorizate</h3>
                <ul>
                    <li>Bucuresti - 2,284 EUR/mp</li>
                    <li>Cluj-Napoca - 3,139 EUR/mp</li>
                    <li>Brasov - 2,538 EUR/mp</li>
                    <li>Timisoara - 2,127 EUR/mp</li>
                    <li>Oradea, Sibiu, Iasi - emergente</li>
                </ul>
            </div>
            <div class="ad-slot ad-slot--sidebar ad-slot--sticky"><div class="ad-placeholder"><span class="ad-label">AD 300x600</span></div></div>
        </aside>
    </div></main>
</body>
</html>"""
    filepath.write_text(html, encoding="utf-8")
    log.info(f"  OK Saved: {article.slug}.html [{article.subcategory}] cities={article.city_tags}")

    # Save JSON metadata
    meta = {
        "title": article.title, "slug": article.slug,
        "category": "investitii", "subcategory": article.subcategory,
        "city_tags": article.city_tags,
        "meta_title": article.meta_title, "meta_description": article.meta_description,
        "meta_keywords": article.meta_keywords, "author": article.author,
        "published": article.published, "reading_time": article.reading_time,
        "source": article.source_name, "hash_id": article.hash_id,
        "url": f"/investitii/{article.slug}",
    }
    (DATA_DIR / f"article_{article.hash_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_index():
    articles = []
    for f in sorted(DATA_DIR.glob("article_*.json"), reverse=True):
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
            if a.get("category") == "investitii":
                articles.append(a)
        except Exception:
            continue

    # Build sub-indexes by subcategory
    for subcat in SUBCATEGORIES:
        sub_articles = [a for a in articles if a.get("subcategory") == subcat]
        sub_index = {
            "category": "investitii", "subcategory": subcat,
            "total": len(sub_articles), "updated": datetime.now(timezone.utc).isoformat(),
            "articles": sub_articles[:30],
        }
        (DATA_DIR / f"index_investitii_{subcat}.json").write_text(
            json.dumps(sub_index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Build city indexes
    for city_key in CITIES:
        city_articles = [a for a in articles if city_key in a.get("city_tags", [])]
        city_index = {
            "category": "investitii", "city": city_key,
            "total": len(city_articles), "updated": datetime.now(timezone.utc).isoformat(),
            "articles": city_articles[:20],
        }
        (DATA_DIR / f"index_city_{city_key}.json").write_text(
            json.dumps(city_index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Main index
    main_index = {
        "category": "investitii", "total": len(articles),
        "updated": datetime.now(timezone.utc).isoformat(),
        "articles": articles[:50],
    }
    (DATA_DIR / "index_investitii.json").write_text(
        json.dumps(main_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"  Index updated: {len(articles)} investitii articles")


def run(max_articles=8, dry_run=False):
    log.info("=" * 60)
    log.info("FinRo Investitii Agent - Starting")
    log.info(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    log.info(f"  Max articles: {max_articles}, Dry run: {dry_run}")
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

    log.info(f"\nTotal entries fetched: {len(all_entries)}")

    for entry in all_entries:
        if not entry.get("title") or not entry.get("url"):
            continue
        url_hash = hashlib.md5(entry["url"].encode()).hexdigest()[:12]
        if url_hash in seen:
            continue

        text = f"{entry['title']} {entry.get('summary', '')}"
        subcategory = detect_subcategory(text)
        city_tags = detect_cities(text)

        article = Article(
            title=entry["title"],
            slug=slugify(entry["title"], max_length=80),
            url=entry["url"],
            source_id=entry["source_id"],
            source_name=entry["source_name"],
            published=entry.get("published", datetime.now(timezone.utc).isoformat()),
            summary=entry.get("summary", ""),
            subcategory=subcategory,
            city_tags=city_tags,
            hash_id=url_hash,
        )

        if not dry_run:
            article.content_html = scrape_content(entry["url"])

        article = generate_meta(article)
        new_articles.append(article)
        seen.add(url_hash)

        if len(new_articles) >= max_articles:
            break

    log.info(f"\nNew articles to process: {len(new_articles)}")

    # Log distribution
    dist = {}
    for a in new_articles:
        dist[a.subcategory] = dist.get(a.subcategory, 0) + 1
    log.info(f"  Distribution: {dist}")

    if not dry_run:
        for article in new_articles:
            save_article(article)
        save_seen(seen)
        update_index()
    else:
        for a in new_articles:
            cities = ",".join(a.city_tags) if a.city_tags else "-"
            log.info(f"  [DRY] {a.subcategory:25s} | {cities:15s} | {a.title[:50]}")

    log.info(f"\n{'='*60}")
    log.info(f"Investitii Agent complete. {len(new_articles)} articles processed.")
    log.info(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinRo Investitii Content Agent")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--max-articles", type=int, default=8, help="Max articles per run")
    args = parser.parse_args()
    run(max_articles=args.max_articles, dry_run=args.dry_run)
