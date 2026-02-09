#!/usr/bin/env node
/**
 * FinRo.ro Agent 3: Tech Reviews Content Agent (Node.js)
 * Schedule: Daily at 08:00 EET
 * Usage: node agent_tech.js [--dry-run] [--max-articles 5]
 */
const fs = require("fs");
const path = require("path");
const axios = require("axios");
const cheerio = require("cheerio");
const Parser = require("rss-parser");
const slugify = require("slugify");
const U = require("./utils");

const OUTPUT_DIR = path.join(U.BASE_DIR, "website", "articles", "tech");
const LOG_DIR = path.join(__dirname, "logs");
U.ensureDirs(OUTPUT_DIR, LOG_DIR);
const log = U.createLogger("agent_tech", LOG_DIR);
const rss = new Parser({ timeout: 15000, headers: { "User-Agent": "FinRo-Bot/1.0" } });

const SOURCES = [
  { id: "arenait", name: "ArenaIT.ro", url: "https://arenait.ro/feed/" },
  { id: "go4it", name: "Go4IT.ro", url: "https://www.go4it.ro/feed/" },
  { id: "playtech", name: "Playtech.ro", url: "https://playtech.ro/feed/" },
  { id: "techradar", name: "TechRadar", url: "https://www.techradar.com/rss", filter: ["review", "best", "vs"] },
  { id: "theverge", name: "The Verge", url: "https://www.theverge.com/rss/reviews/index.xml" },
];

const SUBS = {
  telefoane: ["telefon", "smartphone", "Samsung", "iPhone", "Pixel", "OnePlus", "Xiaomi", "Galaxy"],
  laptopuri: ["laptop", "notebook", "MacBook", "ThinkPad", "Dell XPS", "ASUS", "Lenovo"],
  software: ["app", "software", "VPN", "antivirus", "Windows", "macOS", "browser"],
  ai: ["AI", "ChatGPT", "Claude", "Gemini", "Copilot", "LLM", "GPT"],
  accesorii: ["casti", "headphones", "earbuds", "smartwatch", "tableta", "monitor"],
};

function extractRating(t) {
  var m = t.match(/(\d+\.?\d?)\s*\/\s*10/i);
  if (m) { var v = parseFloat(m[1]); if (v <= 10) return v + "/10"; }
  return "";
}

async function fetchFeed(src) {
  log.info("  Fetch: " + src.name);
  try {
    var feed = await rss.parseURL(src.url);
    var items = (feed.items || []).slice(0, 15);
    if (src.filter) {
      items = items.filter(function(i) {
        var t = ((i.title||"") + " " + (i.contentSnippet||"")).toLowerCase();
        return src.filter.some(function(k) { return t.includes(k); });
      });
    }
    log.info("  -> " + items.length + " items");
    return items.map(function(i) {
      return {
        title: (i.title||"").trim(), url: i.link||"",
        published: i.pubDate || i.isoDate || new Date().toISOString(),
        summary: (i.contentSnippet||"").slice(0, 500),
        sourceId: src.id, sourceName: src.name
      };
    });
  } catch(e) { log.error("  X " + src.name + ": " + e.message); return []; }
}

async function scrape(url) {
  try {
    var r = await axios.get(url, {timeout:15000, headers:{"User-Agent":"FinRo-Bot/1.0"}});
    var $ = cheerio.load(r.data);
    var sels = [".entry-content",".article-content",".post-content","article"];
    for (var i=0; i<sels.length; i++) {
      var el = $(sels[i]).first();
      if (el.length) {
        var ps = [];
        el.find("p").each(function(_,p){var t=$(p).text().trim(); if(t.length>30)ps.push(t);});
        var txt = ps.join("\n\n");
        if (txt.length > 100) return txt.slice(0, 2500);
      }
    }
    return "";
  } catch(e) { return ""; }
}

async function run() {
  var o = U.parseArgs();
  log.info("=".repeat(60));
  log.info("FinRo Tech Agent (Node.js)");
  var seen = U.loadSeen("seen_tech.json");
  var all = [];
  for (var i=0; i<SOURCES.length; i++) { all = all.concat(await fetchFeed(SOURCES[i])); }
  log.info("Total: " + all.length);

  var arts = [];
  for (var j=0; j<all.length; j++) {
    var e = all[j];
    if (!e.title || !e.url) continue;
    var h = U.hashUrl(e.url);
    if (seen.has(h)) continue;
    var sub = U.detectSubcategory(e.title+" "+e.summary, SUBS);
    var a = {
      title: e.title,
      slug: slugify(e.title, {lower:true, strict:true}).slice(0,80),
      url: e.url, category: "tech", subcategory: sub,
      subcategoryKeywords: SUBS[sub]||[],
      published: e.published, summary: e.summary,
      contentHtml: "", sourceName: e.sourceName, author: "Echipa FinRo", rating: ""
    };
    if (!o.dryRun) {
      a.contentHtml = await scrape(e.url);
      a.rating = extractRating(a.summary + " " + a.contentHtml);
    }
    a = U.generateMeta(a, ["tehnologie","recenzie","2025"]);
    arts.push({article:a, hash:h});
    seen.add(h);
    if (arts.length >= o.maxArticles) break;
  }

  if (!o.dryRun) {
    for (var k=0; k<arts.length; k++) {
      var ar = arts[k].article;
      fs.writeFileSync(path.join(OUTPUT_DIR, ar.slug+".html"), U.generateArticleHtml(ar,"⚡"), "utf-8");
      U.saveArticleMeta(ar, arts[k].hash);
      log.info("  OK " + ar.slug);
    }
    U.saveSeen("seen_tech.json", seen);
    U.updateIndex("tech");
  } else {
    arts.forEach(function(x){ log.info("  [DRY] "+x.article.subcategory.padEnd(12)+" | "+x.article.title.slice(0,60)); });
  }
  log.info("Tech Agent done. " + arts.length + " articles.\n");
}

run().catch(function(e){ log.error("Fatal: "+e.message); process.exit(1); });
