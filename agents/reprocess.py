#!/usr/bin/env python3
"""Reprocess existing articles with sumy summaries"""
import os, glob, re
from summarizer import summarize

ARTICLES_DIR = "/var/www/banimetru/articles"

def extract_text(html):
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def reprocess():
    count = 0
    for cat in ["finante", "asigurari", "tech", "investitii"]:
        d = os.path.join(ARTICLES_DIR, cat)
        for fp in glob.glob(os.path.join(d, "*.html")):
            html = open(fp, encoding="utf-8").read()
            m = re.search(r'<div class="article-page__content"[^>]*>(.*?)</div>', html, re.DOTALL)
            if not m:
                continue
            content = extract_text(m.group(1))
            if len(content) < 100:
                continue
            summary = summarize(content, 3)
            old = re.search(r'<strong>([^<]+)</strong>', html)
            if old:
                html = html.replace(old.group(0), f'<strong>{summary}</strong>')
                open(fp, "w", encoding="utf-8").write(html)
                count += 1
                print(f"  OK {os.path.basename(fp)[:60]}")
    print(f"Reprocessed {count} articles")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    reprocess()