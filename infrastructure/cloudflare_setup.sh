#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# FinRo.ro — Cloudflare DNS Setup Guide
# ═══════════════════════════════════════════════════════════════════════
# This is a REFERENCE script showing the Cloudflare API calls.
# You can also configure everything via the Cloudflare dashboard.
# ═══════════════════════════════════════════════════════════════════════

# ─── CONFIGURATION ───
CF_API_TOKEN="YOUR_CLOUDFLARE_API_TOKEN"   # Create at: https://dash.cloudflare.com/profile/api-tokens
CF_ZONE_ID="YOUR_ZONE_ID"                  # Found in Cloudflare dashboard → Overview
SERVER_IP="YOUR_HETZNER_IP"
DOMAIN="finro.ro"

echo "═══════════════════════════════════════"
echo "  Cloudflare DNS Setup for $DOMAIN"
echo "═══════════════════════════════════════"
echo ""
echo "MANUAL STEPS (Cloudflare Dashboard):"
echo ""
echo "1. Go to https://dash.cloudflare.com"
echo "2. Add site: $DOMAIN"
echo "3. Select FREE plan"
echo "4. Update nameservers at your registrar to Cloudflare's NS"
echo "5. Add these DNS records:"
echo ""
echo "   ┌─────────┬──────────────┬───────────────┬────────┐"
echo "   │  Type   │    Name      │    Content    │ Proxy  │"
echo "   ├─────────┼──────────────┼───────────────┼────────┤"
echo "   │  A      │  $DOMAIN     │  $SERVER_IP   │  ✅    │"
echo "   │  A      │  www         │  $SERVER_IP   │  ✅    │"
echo "   │  AAAA   │  $DOMAIN     │  (if IPv6)    │  ✅    │"
echo "   └─────────┴──────────────┴───────────────┴────────┘"
echo ""
echo "6. SSL/TLS Settings:"
echo "   • Mode: Full (Strict)"
echo "   • Always Use HTTPS: ON"
echo "   • Minimum TLS: 1.2"
echo "   • Automatic HTTPS Rewrites: ON"
echo ""
echo "7. Speed → Optimization:"
echo "   • Auto Minify: CSS, JS, HTML — ALL ON"
echo "   • Brotli: ON"
echo "   • Early Hints: ON"
echo "   • Rocket Loader: OFF (can break AdSense)"
echo ""
echo "8. Caching → Configuration:"
echo "   • Caching Level: Standard"
echo "   • Browser Cache TTL: 1 month"
echo ""
echo "9. Page Rules (3 free):"
echo "   Rule 1: ${DOMAIN}/articles/*"
echo "           Cache Level: Cache Everything"
echo "           Edge Cache TTL: 1 day"
echo ""
echo "   Rule 2: ${DOMAIN}/*.html"
echo "           Cache Level: Cache Everything"  
echo "           Edge Cache TTL: 2 hours"
echo ""
echo "   Rule 3: ${DOMAIN}/data/*.json"
echo "           Cache Level: Cache Everything"
echo "           Edge Cache TTL: 30 minutes"
echo ""

# ─── API-based DNS creation (optional, for automation) ───
if [ "$CF_API_TOKEN" != "YOUR_CLOUDFLARE_API_TOKEN" ]; then
    echo "Creating DNS records via API..."
    
    # A record for root domain
    curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        --data "{\"type\":\"A\",\"name\":\"$DOMAIN\",\"content\":\"$SERVER_IP\",\"ttl\":1,\"proxied\":true}" | python3 -m json.tool
    
    # A record for www
    curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        --data "{\"type\":\"A\",\"name\":\"www\",\"content\":\"$SERVER_IP\",\"ttl\":1,\"proxied\":true}" | python3 -m json.tool
    
    echo "DNS records created!"
fi
