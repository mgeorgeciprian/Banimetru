#!/usr/bin/env python3
"""
FinRo.ro — Sitemap Generator
Scans article directories and builds sitemap.xml
Runs daily via cron after agents finish.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

DOMAIN = "https://finro.ro"
PROJECT_DIR = Path("/var/www/finro/website")
DATA_DIR = PROJECT_DIR / "data"
OUTPUT = PROJECT_DIR / "sitemap.xml"

# Static pages
STATIC_PAGES = [
    {"url": "/", "priority": "1.0", "changefreq": "daily"},
    {"url": "/finante", "priority": "0.9", "changefreq": "daily"},
    {"url": "/asigurari", "priority": "0.9", "changefreq": "daily"},
    {"url": "/tech", "priority": "0.9", "changefreq": "daily"},
]

def build_sitemap():
    urls = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Static pages
    for page in STATIC_PAGES:
        urls.append(f"""  <url>
    <loc>{DOMAIN}{page['url']}</loc>
    <lastmod>{now}</lastmod>
    <changefreq>{page['changefreq']}</changefreq>
    <priority>{page['priority']}</priority>
  </url>""")

    # Dynamic articles from JSON indexes
    for index_file in DATA_DIR.glob("index_*.json"):
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
            for article in data.get("articles", []):
                article_url = article.get("url", "")
                published = article.get("published", now)[:10]
                urls.append(f"""  <url>
    <loc>{DOMAIN}{article_url}</loc>
    <lastmod>{published}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>""")
        except Exception as e:
            print(f"Warning: Could not parse {index_file}: {e}")

    # Build XML
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

    OUTPUT.write_text(sitemap, encoding="utf-8")
    print(f"Sitemap generated: {len(urls)} URLs → {OUTPUT}")

if __name__ == "__main__":
    build_sitemap()
