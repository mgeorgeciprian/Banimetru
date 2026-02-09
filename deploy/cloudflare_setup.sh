#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# FinRo.ro — Cloudflare Configuration Guide
# Run after DNS propagation to optimize CDN + caching
# ═══════════════════════════════════════════════════════════════

cat << 'GUIDE'
═══════════════════════════════════════════════════════════════
 CLOUDFLARE SETUP FOR FINRO.RO
═══════════════════════════════════════════════════════════════

1. CREATE CLOUDFLARE ACCOUNT
   → https://dash.cloudflare.com/sign-up (free tier)

2. ADD DOMAIN
   → Add finro.ro → Select Free plan
   → Copy the 2 nameservers Cloudflare gives you

3. UPDATE NAMESERVERS AT REGISTRAR
   → Go to your ROTLD registrar panel
   → Replace existing nameservers with Cloudflare ones
   → Wait 24-48h for propagation (usually faster)

4. DNS RECORDS (Cloudflare Dashboard → DNS)
   ┌──────┬──────────────┬────────────────────┬───────────┐
   │ Type │ Name         │ Content            │ Proxy     │
   ├──────┼──────────────┼────────────────────┼───────────┤
   │ A    │ finro.ro     │ YOUR_SERVER_IP     │ Proxied ☁ │
   │ A    │ www          │ YOUR_SERVER_IP     │ Proxied ☁ │
   │ AAAA │ finro.ro     │ YOUR_IPv6 (if any) │ Proxied ☁ │
   └──────┴──────────────┴────────────────────┴───────────┘

5. SSL/TLS SETTINGS
   → SSL/TLS → Overview → Set to "Full (Strict)"
   → Edge Certificates → Always Use HTTPS: ON
   → Edge Certificates → Minimum TLS: 1.2
   → Edge Certificates → Automatic HTTPS Rewrites: ON

6. SPEED OPTIMIZATION
   → Speed → Optimization
   → Auto Minify: HTML ✓, CSS ✓, JavaScript ✓
   → Brotli: ON
   → Early Hints: ON
   → HTTP/2: ON (default)
   → HTTP/3 (QUIC): ON

7. CACHING RULES
   → Caching → Configuration
   → Browser Cache TTL: Respect Existing Headers
   → Crawler Hints: ON

   → Rules → Page Rules (3 free):
   
   Rule 1: Cache static assets aggressively
   URL: finro.ro/css/*
   Settings: Cache Level: Cache Everything, Edge TTL: 7 days

   Rule 2: Cache images
   URL: finro.ro/images/*
   Settings: Cache Level: Cache Everything, Edge TTL: 30 days

   Rule 3: Cache articles but revalidate
   URL: finro.ro/finante/*
   Settings: Cache Level: Cache Everything, Edge TTL: 4 hours

8. SECURITY
   → Security → Settings
   → Security Level: Medium
   → Challenge Passage: 30 minutes
   → Browser Integrity Check: ON

   → Security → Bots
   → Bot Fight Mode: ON

9. PAGE RULES FOR ADSENSE COMPATIBILITY
   Cloudflare's Rocket Loader can break AdSense.
   → Speed → Optimization → Rocket Loader: OFF
   
   If you use Cloudflare's HTML minification and AdSense
   breaks, create a page rule:
   URL: finro.ro/*
   Settings: Disable Performance (only if needed)

10. VERIFY SETUP
    → Check: https://www.ssllabs.com/ssltest/?d=finro.ro
    → Check: https://pagespeed.web.dev/?url=https://finro.ro
    → Check: dig finro.ro +short (should show Cloudflare IPs)

═══════════════════════════════════════════════════════════════
 ESTIMATED MONTHLY COST BREAKDOWN
═══════════════════════════════════════════════════════════════

  Hetzner CX22 VPS .............. €4.50/month
  Cloudflare Free ............... €0.00/month
  Domain finro.ro ............... ~€0.80/month (€10/year)
  Let's Encrypt SSL ............. €0.00/month
  ─────────────────────────────────────────────
  TOTAL ......................... ~€5.30/month

  At 89,000 monthly readers with average RPM of €30-50:
  Estimated AdSense revenue: €2,670 - €4,450/month
  ROI: ~500-800x monthly infrastructure cost

═══════════════════════════════════════════════════════════════
GUIDE
