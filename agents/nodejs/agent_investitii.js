#!/usr/bin/env node
/**
 * FinRo.ro Agent 4: Investitii Content Agent (Node.js)
 * International finance, ETF/BVB, real estate, corporate investments
 * Schedule: Daily at 09:00 EET
 * Usage: node agent_investitii.js [--dry-run] [--max-articles 8]
 */
const fs = require("fs");
const path = require("path");
const axios = require("axios");
const cheerio = require("cheerio");
const Parser = require("rss-parser");
const slugify = require("slugify");
const U = require("./utils");

const OUTPUT_DIR = path.join(U.BASE_DIR, "website", "articles", "investitii");
const LOG_DIR = path.join(__dirname, "logs");
U.ensureDirs(OUTPUT_DIR, LOG_DIR);
const log = U.createLogger("agent_investitii", LOG_DIR);
const rss = new Parser({ timeout: 15000, headers: { "User-Agent": "FinRo-Bot/1.0" } });

const SOURCES = [
  { id:"reuters", name:"Reuters Business", url:"https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best" },
  { id:"investing_ro", name:"Investing.com RO", url:"https://ro.investing.com/rss/news.rss" },
  { id:"ri_biz", name:"Romania Insider", url:"https://www.romania-insider.com/feed", filter:["ETF","BVB","investit","actiuni","fond","bursa","stock","bond","real estate","imobiliar","developer","fabrica","factory","milioane","FDI","corporat"] },
  { id:"zf", name:"Ziarul Financiar", url:"https://www.zf.ro/rss", filter:["BVB","ETF","bursa","investit","imobiliar","dezvoltat","proiect","fabrica"] },
  { id:"br", name:"Business Review", url:"https://business-review.eu/feed", filter:["property","real estate","residential","office","logistics","investment","Cluj","Brasov","Timisoara"] },
  { id:"profit", name:"Profit.ro", url:"https://www.profit.ro/rss", filter:["investit","fabrica","proiect","milioane","imobiliar","dezvoltat"] },
];

const SUBS = {
  finante_internationale: ["global","international","Fed","BCE","ECB","inflatie","dollar","euro","S&P","NASDAQ","crypto","bitcoin","oil","gold","aur","tariff"],
  etf_bvb: ["ETF","BVB","BET","bursa","actiuni","fond","TVBETETF","InterCapital","Patria","obligatiuni","bonds","Hidroelectrica","Banca Transilvania","Romgaz","dividend","portofoliu"],
  imobiliare: ["imobiliar","real estate","apartament","rezidential","dezvoltator","developer","constructi","Coresi","AFI","One United","IULIUS","Speedwell","NEPI","WDP","birouri","office","retail","mall","hotel","pret","chirii"],
  investitii_corporative: ["investit","fabrica","factory","plant","FDI","corporat","multinational","strain","foreign","milioane euro","Continental","Bosch","Knauf","Stada","Renault","Dacia","locuri de munca"]
};

const CITIES = {
  brasov:["Brasov","Coresi","AFI Park Brasov","Ghimbav"],
  bucuresti:["Bucuresti","Bucharest","Ilfov","One United","Floreasca","Pipera"],
  timisoara:["Timisoara","Iulius Town","Paltim","Continental Timisoara"],
  cluj:["Cluj","Cluj-Napoca","RIVUS","Iulius Mall Cluj"],
  emergente:["Oradea","Sibiu","Iasi","Constanta","Craiova","Arad","Alba Iulia"]
};

function detectCities(text) {
  var lower = text.toLowerCase();
  var found = [];
  for (var key in CITIES) {
    if (CITIES[key].some(function(kw){ return lower.includes(kw.toLowerCase()); })) found.push(key);
  }
  return found;
}

function subIcon(s) {
  return {finante_internationale:"\uD83C\uDF0D",etf_bvb:"\uD83D\uDCC8",imobiliare:"\uD83C\uDFD7",investitii_corporative:"\uD83C\uDFED"}[s]||"\uD83D\uDCB0";
}

function subLabel(s) {
  return {finante_internationale:"Finante Internationale",etf_bvb:"ETF & BVB",imobiliare:"Imobiliare",investitii_corporative:"Investitii Corporative"}[s]||"Investitii";
}

async function fetchFeed(src) {
  log.info("  Fetch: " + src.name);
  try {
    var feed = await rss.parseURL(src.url);
    var items = (feed.items || []).slice(0, 20);
    if (src.filter) {
      items = items.filter(function(i) {
        var t = ((i.title||"") + " " + (i.contentSnippet||"")).toLowerCase();
        return src.filter.some(function(k){ return t.includes(k.toLowerCase()); });
      });
    }
    log.info("  -> " + items.length + " items");
    return items.map(function(i) {
      return { title:(i.title||"").trim(), url:i.link||"", published:i.pubDate||i.isoDate||new Date().toISOString(), summary:(i.contentSnippet||"").slice(0,500), sourceId:src.id, sourceName:src.name };
    });
  } catch(e) { log.error("  X " + src.name + ": " + e.message); return []; }
}

async function scrape(url) {
  try {
    var r = await axios.get(url, {timeout:15000, headers:{"User-Agent":"FinRo-Bot/1.0"}});
    var $ = cheerio.load(r.data);
    var sels = [".entry-content",".article-content",".post-content","article"];
    for (var i=0;i<sels.length;i++) {
      var el = $(sels[i]).first();
      if (el.length) {
        var ps = [];
        el.find("p").each(function(_,p){var t=$(p).text().trim(); if(t.length>30)ps.push(t);});
        if (ps.join(" ").length > 100) return ps.join("\n\n").slice(0,3000);
      }
    }
    return "";
  } catch(e) { return ""; }
}

function generateArticleHtml(a) {
  var icon = subIcon(a.subcategory);
  var label = subLabel(a.subcategory);
  var cityBadges = (a.cityTags||[]).map(function(c){return '<span class="card__badge card__badge--city">'+c+'</span>';}).join("");
  var paras = (a.contentHtml||"").split("\n\n").filter(function(p){return p.trim();}).map(function(p){return "<p>"+p+"</p>";}).join("\n");
  return '<!DOCTYPE html><html lang="ro"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>'+a.metaTitle+'</title><meta name="description" content="'+a.metaDescription+'"><meta property="og:type" content="article"><link rel="canonical" href="https://finro.ro/investitii/'+a.slug+'"><link rel="stylesheet" href="../../css/style.css"></head><body><div class="ad-slot ad-slot--top"><div class="ad-placeholder"><span class="ad-label">AD 728x90</span></div></div><main class="main"><div class="main__grid"><article class="article-page"><div class="article-page__header"><span class="card__category">'+icon+' '+label.toUpperCase()+'</span>'+cityBadges+'<h1>'+a.title+'</h1><div class="card__meta"><span>'+a.author+'</span><time>'+a.published.slice(0,10)+'</time><span>'+a.readingTime+' min</span></div></div><div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD 336x280</span></div></div><div class="article-page__content"><p><strong>'+a.summary+'</strong></p>'+paras+'</div><p class="article-page__source">Sursa: <a href="'+a.url+'" target="_blank" rel="nofollow">'+a.sourceName+'</a></p><div class="ad-slot ad-slot--in-content"><div class="ad-placeholder"><span class="ad-label">AD 728x90</span></div></div></article><aside class="sidebar"><div class="ad-slot ad-slot--sidebar"><div class="ad-placeholder"><span class="ad-label">AD 300x250</span></div></div><div class="ad-slot ad-slot--sidebar ad-slot--sticky"><div class="ad-placeholder"><span class="ad-label">AD 300x600</span></div></div></aside></div></main></body></html>';
}

async function run() {
  var o = U.parseArgs();
  o.maxArticles = o.maxArticles || 8;
  log.info("=".repeat(60));
  log.info("FinRo Investitii Agent (Node.js)");
  var seen = U.loadSeen("seen_investitii.json");
  var all = [];
  for (var i=0;i<SOURCES.length;i++) { all = all.concat(await fetchFeed(SOURCES[i])); }
  log.info("Total: " + all.length);

  var arts = [];
  for (var j=0;j<all.length;j++) {
    var e = all[j];
    if (!e.title || !e.url) continue;
    var h = U.hashUrl(e.url);
    if (seen.has(h)) continue;
    var text = e.title + " " + e.summary;
    var sub = U.detectSubcategory(text, SUBS);
    var cities = detectCities(text);
    var a = {
      title:e.title, slug:slugify(e.title,{lower:true,strict:true}).slice(0,80),
      url:e.url, category:"investitii", subcategory:sub,
      subcategoryKeywords:SUBS[sub]||[], cityTags:cities,
      published:e.published, summary:e.summary,
      contentHtml:"", sourceName:e.sourceName, author:"Echipa FinRo"
    };
    if (!o.dryRun) a.contentHtml = await scrape(e.url);
    a = U.generateMeta(a, ["investitii","Romania","2026"]);
    arts.push({article:a, hash:h});
    seen.add(h);
    if (arts.length >= o.maxArticles) break;
  }

  if (!o.dryRun) {
    for (var k=0;k<arts.length;k++) {
      var ar = arts[k].article;
      fs.writeFileSync(path.join(OUTPUT_DIR, ar.slug+".html"), generateArticleHtml(ar), "utf-8");
      // Save meta with city tags
      var meta = {
        title:ar.title, slug:ar.slug, category:"investitii", subcategory:ar.subcategory,
        city_tags:ar.cityTags, meta_title:ar.metaTitle, meta_description:ar.metaDescription,
        author:ar.author, published:ar.published, reading_time:ar.readingTime,
        source:ar.sourceName, hash_id:arts[k].hash, url:"/investitii/"+ar.slug
      };
      fs.writeFileSync(path.join(U.DATA_DIR, "article_"+arts[k].hash+".json"), JSON.stringify(meta,null,2), "utf-8");
      log.info("  OK " + ar.slug + " [" + ar.subcategory + "] cities=" + (ar.cityTags||[]).join(","));
    }
    U.saveSeen("seen_investitii.json", seen);
    U.updateIndex("investitii");
  } else {
    arts.forEach(function(x){
      var c = (x.article.cityTags||[]).join(",") || "-";
      log.info("  [DRY] " + x.article.subcategory.padEnd(25) + " | " + c.padEnd(15) + " | " + x.article.title.slice(0,50));
    });
  }
  log.info("Investitii Agent done. " + arts.length + " articles.\n");
}

run().catch(function(e){ log.error("Fatal: "+e.message); process.exit(1); });
