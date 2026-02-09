
#!/usr/bin/env python3
"""Auto-rebuild index.html with real articles from all categories"""
import os, glob, re

ARTICLES_DIR = "/var/www/banimetru/articles"
INDEX_FILE = "/var/www/banimetru/index.html"

CATEGORIES = {
    "finante": {"icon": "💰", "label": "Finanțe"},
    "asigurari": {"icon": "🛡️", "label": "Asigurări"},
    "tech": {"icon": "💻", "label": "Tech"},
    "investitii": {"icon": "📈", "label": "Investiții"},
}

def build_cards(cat, max_items=6):
    d = os.path.join(ARTICLES_DIR, cat)
    if not os.path.exists(d):
        return ""
    files = sorted(glob.glob(os.path.join(d, "*.html")), key=os.path.getmtime, reverse=True)[:max_items]
    cards = ""
    for fp in files:
        slug = os.path.basename(fp).replace(".html", "")
        try:
            html = open(fp, encoding="utf-8").read()
        except:
            continue
        m = re.search(r"<h1[^>]*>([^<]+)", html)
        title = m.group(1).strip() if m else slug.replace("-", " ")[:80]
        m2 = re.search(r"<strong>([^<]+)", html)
        summary = m2.group(1).strip()[:150] if m2 else "Citește articolul complet pe BaniMetru.ro"
        m3 = re.search(r'nofollow[^>]*>([^<]+)', html)
        source = m3.group(1).strip() if m3 else "BaniMetru.ro"
        cards += f'''                    <article class="card">
                        <a href="/{cat}/{slug}" class="card__link">
                            <h3 class="card__title">{title}</h3>
                            <p class="card__excerpt">{summary}</p>
                            <div class="card__meta"><span>Conform {source}</span></div>
                        </a>
                    </article>
'''
    return cards

def build_index():
    sections = ""
    total = 0
    for cat, info in CATEGORIES.items():
        cards = build_cards(cat)
        count = cards.count("card__title")
        total += count
        sections += f'''
        <section id="{cat}" class="section">
            <div class="section__header">
                <h2>{info["icon"]} {info["label"]}</h2>
            </div>
            <div class="section__grid">
{cards}            </div>
        </section>
'''

    html = f'''<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="BaniMetru.ro — Compară finanțe, asigurări, investiții și tehnologie în România. Rezumate zilnice din surse de încredere.">
    <meta name="author" content="BaniMetru.ro">
    <meta property="og:title" content="BaniMetru.ro — Finanțe, Asigurări, Investiții & Tehnologie">
    <meta property="og:description" content="Compară și decide mai bine. Rezumate zilnice din surse financiare de încredere.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://banimetru.ro">
    <meta property="og:locale" content="ro_RO">
    <link rel="canonical" href="https://banimetru.ro">
    <title>BaniMetru.ro — Finanțe, Asigurări, Investiții & Tehnologie | România</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/css/style.css">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "BaniMetru.ro",
        "url": "https://banimetru.ro",
        "description": "Compară finanțe, asigurări, investiții și tehnologie în România",
        "publisher": {{
            "@type": "Organization",
            "name": "BaniMetru.ro"
        }}
    }}
    </script>
</head>
<body>
    <header class="header">
        <div class="header__inner">
            <a href="/" class="header__logo">
                <span class="logo__icon">📊</span>
                <span class="logo__text">Bani<strong>Metru</strong><span class="logo__ro">.ro</span></span>
            </a>
            <nav class="header__nav">
                <a href="#finante" class="nav__link">Finanțe</a>
                <a href="#asigurari" class="nav__link">Asigurări</a>
                <a href="#tech" class="nav__link">Tech</a>
                <a href="#investitii" class="nav__link">Investiții</a>
            </nav>
        </div>
    </header>

    <main class="main">
        <section class="hero">
            <div class="hero__content">
                <h1>Măsoară-ți banii mai bine</h1>
                <p>Rezumate zilnice din finanțe, asigurări, investiții și tech — din surse de încredere.</p>
            </div>
        </section>
{sections}
    </main>

    <footer class="footer">
        <div class="footer__inner">
            <div class="footer__grid">
                <div class="footer__col">
                    <p class="footer__about">BaniMetru.ro — Compară și decide mai bine. Rezumate zilnice din surse financiare de încredere din România.</p>
                </div>
                <div class="footer__col">
                    <h4>Categorii</h4>
                    <a href="#finante">Finanțe</a>
                    <a href="#asigurari">Asigurări</a>
                    <a href="#tech">Tech</a>
                    <a href="#investitii">Investiții</a>
                </div>
            </div>
            <p class="footer__copy">© 2025 BaniMetru.ro — Toate drepturile rezervate.</p>
        </div>
    </footer>
    <script src="/js/main.js"></script>
</body>
</html>'''

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Index rebuilt: {total} articles across {len(CATEGORIES)} categories")

if __name__ == "__main__":
    build_index()
