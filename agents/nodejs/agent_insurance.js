#!/usr/bin/env node
/**
 * ═══════════════════════════════════════════════════════════════
 * FinRo.ro — Agent 2: Insurance Content Agent (Node.js)
 * ═══════════════════════════════════════════════════════════════
 * Schedule: Daily at 07:00 EET
 * Usage: node agent_insurance.js [--dry-run] [--max-articles 5]
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

const OUTPUT_DIR = path.join(BASE_DIR, "website", "articles", "asigurari");
const LOG_DIR = path.join(__dirname, "logs");
ensureDirs(OUTPUT_DIR, LOG_DIR);

const log = createLogger("agent_insurance", LOG_DIR);
const parser = new Parser({ timeout: 15000, headers: { "User-Agent": "FinRo-Bot/1.0" } });

const SOURCES = [
  { id: "1asig", name: "1asig.ro", rss: "https://www.1asig.ro/rss/", type: "rss" },
  { id: "zf_asig", name: "ZF Asigurări", rss: "https://www.zf.ro/rss", type: "rss", filterKeywords: ["asigur", "RCA", "CASCO", "poliț"] },
  { id: "asf", name: "ASF Romania", url: "https://asfromania.ro/ro/a/1/informatii-publice/comunicate", type: "scrape", selector: ".view-content .views-row" },
];

const SUBCATEGORIES = {
  rca: ["RCA", "asigurare auto", "obligatorie", "daune auto", "poliță auto", "BAAR"],
  casco: ["CASCO", "miniCASCO", "asigurare facultativă", "avarie", "furt auto"],
  sanatate: ["asigurare sănătate", "medical", "spitalizare", "asigurare privată"],
  calatorie: ["asigurare călătorie", "travel", "carte verde", "asistență rutieră"],
  locuinta: ["asigurare locuință", "PAD", "PAID", "cutremur", "inundații"],
};

async function fetchRss(source) {
  log.info(`  Fetching RSS: ${source.name}`);
  try {
    const feed = await parser.parseURL(source.rss);
    let items = (feed.items || []).slice(0, 15);

    if (source.filterKeywords) {
      items = items.filter((item) => {
        const text = `${item.title || ""} ${item.contentSnippet || ""}`.toLowerCase();
        return source.filterKeywords.some((kw) => text.includes(kw.toLowerCase()));
      });
    }

    const entries = items.map((item) => ({
      title: (item.title || "").trim(),
      url: item.link || "",
      published: item.pubDate || item.isoDate || new Date().toISOString(),
      summary: (item.contentSnippet || "").slice(0, 500),
      sourceId: source.id,
      sourceName: source.name,
    }));
    log.info(`  → ${entries.length} entries`);
    return entries;
  } catch (err) {
    log.error(`  ✗ ${source.name}: ${err.message}`);
    return [];
  }
}

async function scrapePage(source) {
  log.info(`  Scraping: ${source.name}`);
  try {
    const { data } = await axios.get(source.url, {
      timeout: 15000,
      headers: { "User-Agent": "FinRo-Bot/1.0" },
    });
    const $ = cheerio.load(data);
    const entries = [];

    $(source.selector).slice(0, 10).each((_, el) => {
      const link = $(el).find("a").first();
      const title = link.text().trim();
      let href = link.attr("href") || "";
      if (href && !href.startsWith("http")) {
        href = new URL(href, source.url).toString();
      }
      const summary = $(el).find("p, .summary, .description").first().text().trim().slice(0, 500);

      if (title && href) {
        entries.push({
          title, url: href,
          published: new Date().toISOString(),
          summary,
          sourceId: source.id,
          sourceName: source.name,
        });
      }
    });

    log.info(`  → ${entries.length} entries`);
    return entries;
  } catch (err) {
    log.error(`  ✗ ${source.name}: ${err.message}`);
    return [];
  }
}

async function scrapeContent(url) {
  try {
    const { data } = await axios.get(url, { timeout: 15000, headers: { "User-Agent": "FinRo-Bot/1.0" } });
    const $ = cheerio.load(data);
    for (const sel of [".entry-content", ".article-content", ".article-body", "article"]) {
      const el = $(sel).first();
      if (el.length) {
        const paras = [];
        el.find("p").each((_, p) => {
          const t = $(p).text().trim();
          if (t.length > 30) paras.push(t);
        });
        if (paras.join(" ").length > 100) return paras.join("\n\n").slice(0, 2000);
      }
    }
    return "";
  } catch { return ""; }
}

async function run() {
  const { dryRun, maxArticles } = parseArgs();
  log.info("=".repeat(60));
  log.info(`FinRo Insurance Agent (Node.js) — dry=${dryRun}, max=${maxArticles}`);
  log.info("=".repeat(60));

  const seen = loadSeen("seen_insurance.json");
  const allEntries = [];

  for (const source of SOURCES) {
    const entries = source.type === "rss" ? await fetchRss(source) : await scrapePage(source);
    allEntries.push(...entries);
  }

  const newArticles = [];
  for (const entry of allEntries) {
    if (!entry.title || !entry.url) continue;
    const hash = hashUrl(entry.url);
    if (seen.has(hash)) continue;

    const subcategory = detectSubcategory(`${entry.title} ${entry.summary}`, SUBCATEGORIES);
    let article = {
      title: entry.title,
      slug: slugify(entry.title, { lower: true, strict: true }).slice(0, 80),
      url: entry.url, category: "asigurari", subcategory,
      subcategoryKeywords: SUBCATEGORIES[subcategory] || [],
      published: entry.published, summary: entry.summary,
      contentHtml: "", sourceName: entry.sourceName, author: "Echipa FinRo",
    };

    if (!dryRun) article.contentHtml = await scrapeContent(entry.url);
    article = generateMeta(article, ["asigurări", "România", "2025"]);

    newArticles.push({ article, hash });
    seen.add(hash);
    if (newArticles.length >= maxArticles) break;
  }

  if (!dryRun) {
    for (const { article, hash } of newArticles) {
      fs.writeFileSync(
        path.join(OUTPUT_DIR, `${article.slug}.html`),
        generateArticleHtml(article, "🛡️"), "utf-8"
      );
      saveArticleMeta(article, hash);
      log.info(`  ✓ ${article.slug}`);
    }
    saveSeen("seen_insurance.json", seen);
    updateIndex("asigurari");
  } else {
    for (const { article } of newArticles) {
      log.info(`  [DRY] ${article.subcategory.padEnd(12)} | ${article.title.slice(0, 60)}`);
    }
  }

  log.info(`Insurance Agent complete. ${newArticles.length} processed.\n`);
}

run().catch((err) => { log.error(`Fatal: ${err.message}`); process.exit(1); });
