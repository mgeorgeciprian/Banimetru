/**
 * ═══════════════════════════════════════════════════════════════
 * FinRo.ro — Shared Utilities for Node.js Agents
 * ═══════════════════════════════════════════════════════════════
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const winston = require("winston");

const BASE_DIR = path.resolve(__dirname, "..", "..");
const DATA_DIR = path.join(BASE_DIR, "website", "data");

/** Ensure directories exist */
function ensureDirs(...dirs) {
  for (const d of dirs) {
    fs.mkdirSync(d, { recursive: true });
  }
}

/** Create a winston logger */
function createLogger(name, logDir) {
  ensureDirs(logDir);
  return winston.createLogger({
    level: "info",
    format: winston.format.combine(
      winston.format.timestamp(),
      winston.format.printf(
        ({ timestamp, level, message }) =>
          `${timestamp} [${level.toUpperCase()}] ${message}`
      )
    ),
    transports: [
      new winston.transports.Console(),
      new winston.transports.File({
        filename: path.join(logDir, `${name}.log`),
        maxsize: 5 * 1024 * 1024,
        maxFiles: 3,
      }),
    ],
  });
}

/** MD5 hash (first 12 chars) */
function hashUrl(url) {
  return crypto.createHash("md5").update(url).digest("hex").slice(0, 12);
}

/** Load seen hashes from JSON */
function loadSeen(filename) {
  const filepath = path.join(DATA_DIR, filename);
  if (fs.existsSync(filepath)) {
    try {
      const data = JSON.parse(fs.readFileSync(filepath, "utf-8"));
      return new Set(data.hashes || []);
    } catch {
      return new Set();
    }
  }
  return new Set();
}

/** Save seen hashes */
function saveSeen(filename, hashes) {
  ensureDirs(DATA_DIR);
  const filepath = path.join(DATA_DIR, filename);
  fs.writeFileSync(
    filepath,
    JSON.stringify(
      { hashes: [...hashes], updated: new Date().toISOString() },
      null,
      2
    ),
    "utf-8"
  );
}

/** Detect subcategory from text using keyword mapping */
function detectSubcategory(text, subcategories) {
  const lower = text.toLowerCase();
  const scores = {};
  for (const [cat, keywords] of Object.entries(subcategories)) {
    scores[cat] = keywords.filter((kw) => lower.includes(kw.toLowerCase())).length;
  }
  const best = Object.entries(scores).sort((a, b) => b[1] - a[1])[0];
  return best && best[1] > 0 ? best[0] : "general";
}

/** Generate SEO metadata */
function generateMeta(article, baseKeywords = []) {
  // Meta title
  article.metaTitle =
    (article.title.length > 60
      ? article.title.slice(0, 57) + "..."
      : article.title) + " | FinRo.ro";

  // Meta description
  const desc = article.summary || article.title;
  article.metaDescription =
    desc.length > 155 ? desc.slice(0, 152) + "..." : desc;

  // Keywords
  const catKw = (article.subcategoryKeywords || []).slice(0, 4);
  article.metaKeywords = [
    ...new Set([...baseKeywords, ...catKw]),
  ];

  // Reading time
  const words = `${article.summary} ${article.contentHtml}`.split(/\s+/).length;
  article.readingTime = Math.max(2, Math.floor(words / 200));

  return article;
}

/** Save article JSON metadata */
function saveArticleMeta(article, hashId) {
  ensureDirs(DATA_DIR);
  const meta = {
    title: article.title,
    slug: article.slug,
    category: article.category,
    subcategory: article.subcategory,
    meta_title: article.metaTitle,
    meta_description: article.metaDescription,
    meta_keywords: article.metaKeywords,
    author: article.author || "Echipa FinRo",
    published: article.published,
    reading_time: article.readingTime,
    source: article.sourceName,
    hash_id: hashId,
    url: `/${article.category}/${article.slug}`,
  };
  if (article.rating) meta.rating = article.rating;
  fs.writeFileSync(
    path.join(DATA_DIR, `article_${hashId}.json`),
    JSON.stringify(meta, null, 2),
    "utf-8"
  );
}

/** Update category index */
function updateIndex(category) {
  ensureDirs(DATA_DIR);
  const articles = [];
  const files = fs.readdirSync(DATA_DIR).filter((f) => f.startsWith("article_"));
  for (const f of files) {
    try {
      const a = JSON.parse(
        fs.readFileSync(path.join(DATA_DIR, f), "utf-8")
      );
      if (a.category === category) articles.push(a);
    } catch {
      continue;
    }
  }
  articles.sort((a, b) => (b.published || "").localeCompare(a.published || ""));

  const index = {
    category,
    total: articles.length,
    updated: new Date().toISOString(),
    articles: articles.slice(0, 50),
  };
  fs.writeFileSync(
    path.join(DATA_DIR, `index_${category}.json`),
    JSON.stringify(index, null, 2),
    "utf-8"
  );
  return articles.length;
}

/** Generate article HTML page with AdSense slots */
function generateArticleHtml(article, categoryIcon = "📰") {
  const ratingBadge = article.rating
    ? `<span class="card__badge card__badge--review">⭐ ${article.rating}</span>`
    : "";

  const contentParagraphs = (article.contentHtml || "")
    .split("\n\n")
    .filter((p) => p.trim())
    .map((p) => `<p>${p}</p>`)
    .join("\n");

  return `<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${article.metaTitle}</title>
    <meta name="description" content="${article.metaDescription}">
    <meta name="keywords" content="${(article.metaKeywords || []).join(", ")}">
    <meta property="og:title" content="${article.metaTitle}">
    <meta property="og:description" content="${article.metaDescription}">
    <meta property="og:type" content="article">
    <link rel="canonical" href="https://finro.ro/${article.category}/${article.slug}">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "${article.title.replace(/"/g, '\\"')}",
        "description": "${article.metaDescription.replace(/"/g, '\\"')}",
        "author": {"@type": "Person", "name": "${article.author || "Echipa FinRo"}"},
        "publisher": {"@type": "Organization", "name": "FinRo.ro"},
        "datePublished": "${article.published}",
        "articleSection": "${article.subcategory}"
    }
    </script>
    <link rel="stylesheet" href="../../css/style.css">
</head>
<body>
    <div class="ad-slot ad-slot--top"><div class="ad-placeholder"><span class="ad-label">AD · 728×90</span></div></div>
    <main class="main"><div class="main__grid">
        <article class="article-page" itemscope itemtype="https://schema.org/Article">
            <div class="article-page__header">
                <span class="card__category">${categoryIcon} ${(article.subcategory || "").toUpperCase()}</span>
                ${ratingBadge}
                <h1 itemprop="headline">${article.title}</h1>
                <div class="card__meta">
                    <span>${article.author || "Echipa FinRo"}</span>
                    <time datetime="${article.published}">${(article.published || "").slice(0, 10)}</time>
                    <span>${article.readingTime || 4} min citire</span>
                </div>
            </div>
            <div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD · 336×280</span></div></div>
            <div class="article-page__content" itemprop="articleBody">
                <p><strong>${article.summary}</strong></p>
                ${contentParagraphs}
            </div>
            <p class="article-page__source">Sursă: <a href="${article.url}" target="_blank" rel="nofollow">${article.sourceName}</a></p>
            <div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD · 728×90</span></div></div>
        </article>
        <aside class="sidebar">
            <div class="ad-slot ad-slot--sidebar"><div class="ad-placeholder"><span class="ad-label">AD · 300×250</span></div></div>
            <div class="ad-slot ad-slot--sidebar ad-slot--sticky"><div class="ad-placeholder"><span class="ad-label">AD · 300×600</span></div></div>
        </aside>
    </div></main>
</body>
</html>`;
}

/** Parse CLI args for --dry-run and --max-articles */
function parseArgs() {
  const args = process.argv.slice(2);
  return {
    dryRun: args.includes("--dry-run"),
    maxArticles: (() => {
      const idx = args.indexOf("--max-articles");
      return idx >= 0 && args[idx + 1] ? parseInt(args[idx + 1]) : 5;
    })(),
  };
}

module.exports = {
  BASE_DIR,
  DATA_DIR,
  ensureDirs,
  createLogger,
  hashUrl,
  loadSeen,
  saveSeen,
  detectSubcategory,
  generateMeta,
  saveArticleMeta,
  updateIndex,
  generateArticleHtml,
  parseArgs,
};
