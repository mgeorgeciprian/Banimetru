#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# FinRo.ro — Server Health Check & Monitoring
# ═══════════════════════════════════════════════════════════════════════
# Run manually or via cron to check server health.
# Usage: bash monitor.sh [--alert]
# With --alert, sends notification on failure (configure webhook below)
# ═══════════════════════════════════════════════════════════════════════

DOMAIN="finro.ro"
PROJECT_DIR="/var/www/finro"
ALERT_WEBHOOK=""  # Slack/Discord webhook URL (optional)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" = "OK" ]; then
        echo -e "  ${GREEN}✓${NC} $name"
    else
        echo -e "  ${RED}✗${NC} $name — $result"
        ERRORS=$((ERRORS + 1))
    fi
}

echo ""
echo "═══════════════════════════════════════"
echo "  FinRo.ro Health Check — $(date)"
echo "═══════════════════════════════════════"
echo ""

# ─── System ───
echo "System:"
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -lt 85 ]; then
    check "Disk usage" "OK"
else
    check "Disk usage" "${DISK_USAGE}% (warning: >85%)"
fi

MEM_USAGE=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USAGE" -lt 90 ]; then
    check "Memory usage" "OK"
else
    check "Memory usage" "${MEM_USAGE}% (warning: >90%)"
fi

LOAD=$(uptime | awk -F'load average:' '{print $2}' | awk -F',' '{print $1}' | tr -d ' ')
check "Load average" "OK"

echo ""

# ─── Services ───
echo "Services:"
if systemctl is-active --quiet nginx; then
    check "nginx" "OK"
else
    check "nginx" "NOT RUNNING"
fi

if systemctl is-active --quiet fail2ban; then
    check "fail2ban" "OK"
else
    check "fail2ban" "NOT RUNNING"
fi

if systemctl is-active --quiet cron; then
    check "cron" "OK"
else
    check "cron" "NOT RUNNING"
fi

echo ""

# ─── Website ───
echo "Website:"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    check "HTTPS response" "OK"
else
    check "HTTPS response" "HTTP $HTTP_CODE"
fi

# Check SSL expiry
SSL_EXPIRY=$(echo | openssl s_client -connect $DOMAIN:443 -servername $DOMAIN 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
if [ -n "$SSL_EXPIRY" ]; then
    DAYS_LEFT=$(( ($(date -d "$SSL_EXPIRY" +%s) - $(date +%s)) / 86400 ))
    if [ "$DAYS_LEFT" -gt 14 ]; then
        check "SSL certificate" "OK"
    else
        check "SSL certificate" "Expires in $DAYS_LEFT days!"
    fi
else
    check "SSL certificate" "Could not check"
fi

echo ""

# ─── Content Agents ───
echo "Content Agents (last run):"
for agent in finance insurance tech; do
    LOG_FILE="/var/log/finro/agent_${agent}.log"
    if [ -f "$LOG_FILE" ]; then
        LAST_MOD=$(stat -c %Y "$LOG_FILE" 2>/dev/null || echo "0")
        NOW=$(date +%s)
        AGE_HOURS=$(( (NOW - LAST_MOD) / 3600 ))
        if [ "$AGE_HOURS" -lt 26 ]; then
            check "Agent: $agent" "OK"
        else
            check "Agent: $agent" "Last run ${AGE_HOURS}h ago (stale >26h)"
        fi
    else
        check "Agent: $agent" "No log file found"
    fi
done

echo ""

# ─── Article counts ───
echo "Content:"
for cat in finante asigurari tech; do
    COUNT=$(find $PROJECT_DIR/website/articles/$cat -name "*.html" 2>/dev/null | wc -l)
    echo -e "  📄 $cat: $COUNT articles"
done

TOTAL_DATA=$(du -sh $PROJECT_DIR/website/data/ 2>/dev/null | awk '{print $1}')
echo -e "  📊 Data index: $TOTAL_DATA"

echo ""

# ─── Summary ───
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
else
    echo -e "${RED}$ERRORS issue(s) detected!${NC}"
    
    # Send alert if webhook configured
    if [ -n "$ALERT_WEBHOOK" ] && [ "$1" = "--alert" ]; then
        curl -s -X POST "$ALERT_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"⚠️ FinRo.ro: $ERRORS health check issue(s) on $(hostname)\"}" > /dev/null
        echo "Alert sent to webhook"
    fi
fi
echo ""
