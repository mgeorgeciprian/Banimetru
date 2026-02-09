#!/usr/bin/env node
/**
 * ═══════════════════════════════════════════════════════════════
 * FinRo.ro — Agent 1: Finance Content Agent (Node.js)
 * ═══════════════════════════════════════════════════════════════
 * Scrapes Romanian finance news and generates SEO articles.
 * Schedule: Daily at 06:00 EET via cron
 * Usage: node agent_finance.js [--dry-run] [--max-articles 5]
 */

const fs = require("fs");
const path = require("path");
const axios = require("axios");
const cheerio = require("cheerio");
const Parser = require("rss-parser");
const slugify = require("slugify");
const {
  BASE_DIR, ensureDirs, createLogger, hashUrl,
  loadSeen, saveSeen, detectSubcategory, generateMeta,
  saveArticleMeta, updateIndex, generateArticleHtml, parseArgs,
} = require("./utils");

const OUTPUT_DIR = path.join(BASE_DIR, "website", "articles", "finante");
const LOG_DIR = path.join(__dirname, "logs");
ensureDirs(OUTPUT_DIR, LOG_DIR);

const log = createLogger("agent_finance", LOG_DIR);
const parser = new Parser({ timeout: 15000, headers: { "User-Agent": "FinRo-Bot/1.0" } });

const SOURCES = [
  { id: "bnr", name: "BNR", rss: "https://www.bnr.ro/RSS_200.aspx" },
  { id: "zf", name: "Ziarul Financiar", rss: "https://www.zf.ro/rss" },
  { id: "profit", name: "Profit.ro", rss: "https://www.profit.ro/rss" },
  { id: "wall_street", name: "Wall-Street.ro", rss: "https://www.wall-street.ro/rss/economie.xml" },
];

const SUBCATEGORIES = {
  credite: ["credit", "credite", "ipotecar", "imobiliar", "dobândă", "IRCC", "ROBOR", "împrumut", "refinanțare"],
  economisire: ["economii", "economisire", "depozit", "cont economii", "buget"],
  investitii: ["investiți", "acțiuni", "obligațiuni", "ETF", "bursă", "BVB", "portofoliu", "titluri de stat"],
  taxe: ["taxe", "impozit", "ANAF", "declarația unică", "CAS", "CASS", "TVA", "fiscal", "PFA"],
  pensii: ["pensie", "pilonul", "fond de pensii", "CNPP", "punct de pensie"],
};

async function fetchRss(source) {
  log.info(`  Fetching: ${source.name}`);
  try {
    const feed = await parser.parseURL(source.rss);
    const entries = (feed.items || []).slice(0, 10).map((item) => ({
      title: (item.title || "").trim(),
      url: item.link || "",
      published: item.pubDate || item.isoDate || new Date().toISOString(),
      summary: (item.contentSnippet || item.content || "").slice(0, 500),
      sourceId: source.id,
      sourceName: source.name,
    }));
    log.info(`  → ${entries.length} entries from ${source.name}`);
    return entries;
  } catch (err) {
    log.error(`  ✗ ${source.name}: ${err.message}`);
    return [];
  }
}

async function scrapeContent(url) {
  try {
    const { data } = await axios.get(url, {
      timeout: 15000,
      headers: { "User-Agent": "FinRo-Bot/1.0" },
    });
    const $ = cheerio.load(data);
    const selectors = [".entry-content", ".article-content", ".article-body", ".post-content", "article"];
    for (const sel of selectors) {
      const el = $(sel).first();
      if (el.length) {
        const paras = [];
        el.find("p").each((_, p) => {
          const t = $(p).text().trim();
          if (t.length > 30) paras.push(t);
        });
        const text = paras.join("\n\n");
        if (text.length > 100) return text.slice(0, 2000);
      }
    }
    return "";
  } catch {
    return "";
  }
}

async function run() {
  const { dryRun, maxArticles } = parseArgs();
  log.info("=".repeat(60));
  log.info(`FinRo Finance Agent (Node.js) — dry=${dryRun}, max=${maxArticles}`);
  log.info("=".repeat(60));

  const seen = loadSeen("seen_finance.json");
  const allEntries = [];

  for (const source of SOURCES) {
    const entries = await fetchRss(source);
    allEntries.push(...entries);
  }
  log.info(`Total entries: ${allEntries.length}`);

  const newArticles = [];
  for (const entry of allEntries) {
    if (!entry.title || !entry.url) continue;
    const hash = hashUrl(entry.url);
    if (seen.has(hash)) continue;

    const text = `${entry.title} ${entry.summary}`;
    const subcategory = detectSubcategory(text, SUBCATEGORIES);

    let article = {
      title: entry.title,
      slug: slugify(entry.title, { lower: true, strict: true }).slice(0, 80),
      url: entry.url,
      category: "finante",
      subcategory,
      subcategoryKeywords: SUBCATEGORIES[subcategory] || [],
      published: entry.published,
      summary: entry.summary,
      contentHtml: "",
      sourceName: entry.sourceName,
      author: "Echipa FinRo",
    };

    if (!dryRun) {
      article.contentHtml = await scrapeContent(entry.url);
    }
    article = generateMeta(article, ["finanțe personale", "România", "2025"]);

    newArticles.push({ article, hash });
    seen.add(hash);
    if (newArticles.length >= maxArticles) break;
  }

  log.info(`New articles: ${newArticles.length}`);

  if (!dryRun) {
    for (const { article, hash } of newArticles) {
      const html = generateArticleHtml(article, "💰");
      fs.writeFileSync(path.join(OUTPUT_DIR, `${article.slug}.html`), html, "utf-8");
      saveArticleMeta(article, hash);
      log.info(`  ✓ ${article.slug}`);
    }
    saveSeen("seen_finance.json", seen);
    const total = updateIndex("finante");
    log.info(`  Index: ${total} finance articles`);
  } else {
    for (const { article } of newArticles) {
      log.info(`  [DRY] ${article.subcategory.padEnd(12)} | ${article.title.slice(0, 60)}`);
    }
  }

  log.info(`Finance Agent complete. ${newArticles.length} processed.\n`);
}

run().catch((err) => {
  log.error(`Fatal: ${err.message}`);
  process.exit(1);
});
