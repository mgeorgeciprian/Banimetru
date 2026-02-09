#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# FinRo.ro — Health Check & Monitoring Script
# Run via cron every 5 minutes or use as manual diagnostic
# Usage: ./healthcheck.sh [--notify]
# ═══════════════════════════════════════════════════════════════

DOMAIN="finro.ro"
PROJECT_DIR="/var/www/finro"
LOG_FILE="/var/log/finro/healthcheck.log"
NOTIFY=${1:-""}

# Timestamp
TS=$(date '+%Y-%m-%d %H:%M:%S')

check_pass() { echo "[$TS] ✓ $1" >> $LOG_FILE; }
check_fail() { echo "[$TS] ✗ FAIL: $1" >> $LOG_FILE; FAILURES+=("$1"); }

FAILURES=()

# ─── 1. nginx running? ───
if systemctl is-active --quiet nginx; then
    check_pass "nginx is running"
else
    check_fail "nginx is DOWN"
    systemctl restart nginx 2>/dev/null && check_pass "nginx auto-restarted"
fi

# ─── 2. Website responding? ───
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$DOMAIN" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    check_pass "Website responding (HTTP $HTTP_CODE)"
else
    check_fail "Website returned HTTP $HTTP_CODE"
fi

# ─── 3. SSL certificate valid? ───
SSL_EXPIRY=$(echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null | grep notAfter | cut -d= -f2)
if [ -n "$SSL_EXPIRY" ]; then
    EXPIRY_EPOCH=$(date -d "$SSL_EXPIRY" +%s 2>/dev/null)
    NOW_EPOCH=$(date +%s)
    DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
    if [ "$DAYS_LEFT" -gt 7 ]; then
        check_pass "SSL valid ($DAYS_LEFT days remaining)"
    else
        check_fail "SSL expiring in $DAYS_LEFT days!"
    fi
else
    check_fail "Could not check SSL certificate"
fi

# ─── 4. Disk space ───
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -lt 85 ]; then
    check_pass "Disk usage: ${DISK_USAGE}%"
else
    check_fail "Disk usage HIGH: ${DISK_USAGE}%"
fi

# ─── 5. Memory ───
MEM_USAGE=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USAGE" -lt 90 ]; then
    check_pass "Memory usage: ${MEM_USAGE}%"
else
    check_fail "Memory usage HIGH: ${MEM_USAGE}%"
fi

# ─── 6. Agent logs (did they run today?) ───
TODAY=$(date '+%Y-%m-%d')
for AGENT in finance insurance tech; do
    AGENT_LOG="/var/log/finro/${AGENT}.log"
    if [ -f "$AGENT_LOG" ]; then
        LAST_RUN=$(grep -c "$TODAY" "$AGENT_LOG" 2>/dev/null || echo "0")
        if [ "$LAST_RUN" -gt 0 ]; then
            check_pass "Agent $AGENT ran today ($LAST_RUN log entries)"
        else
            check_fail "Agent $AGENT did NOT run today"
        fi
    else
        check_fail "Agent $AGENT log missing"
    fi
done

# ─── 7. Article count ───
for CAT in finante asigurari tech; do
    COUNT=$(find "$PROJECT_DIR/website/articles/$CAT" -name "*.html" 2>/dev/null | wc -l)
    check_pass "Articles in $CAT: $COUNT"
done

# ─── Summary ───
if [ ${#FAILURES[@]} -eq 0 ]; then
    echo "[$TS] ═══ ALL CHECKS PASSED ═══" >> $LOG_FILE
else
    echo "[$TS] ═══ ${#FAILURES[@]} FAILURES ═══" >> $LOG_FILE
    for f in "${FAILURES[@]}"; do
        echo "[$TS]   → $f" >> $LOG_FILE
    done
    
    # ─── Send Notifications ───
    if [ "$NOTIFY" = "--notify" ]; then
        ALERT_MSG="🚨 FinRo.ro Alert: ${#FAILURES[@]} issues detected: ${FAILURES[*]}"
        
        # ══════════════════════════════════════════════════
        # TELEGRAM (edit these 2 values)
        # Setup: Message @BotFather → /newbot → get token
        #        Then visit https://api.telegram.org/botTOKEN/getUpdates for chat_id
        # ══════════════════════════════════════════════════
        TELEGRAM_TOKEN="PASTE_YOUR_BOT_TOKEN_HERE"
        TELEGRAM_CHAT_ID="PASTE_YOUR_CHAT_ID_HERE"
        
        if [ "$TELEGRAM_TOKEN" != "PASTE_YOUR_BOT_TOKEN_HERE" ]; then
            curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
                -d "chat_id=${TELEGRAM_CHAT_ID}" \
                -d "text=${ALERT_MSG}" \
                -d "parse_mode=HTML" > /dev/null
            echo "[$TS] Telegram alert sent" >> $LOG_FILE
        fi
        
        # ══════════════════════════════════════════════════
        # EMAIL via msmtp (edit these values)
        # Install: apt install msmtp msmtp-mta
        # ══════════════════════════════════════════════════
        ALERT_EMAIL="george@amatech.ro"
        
        if command -v msmtp &> /dev/null; then
            echo -e "Subject: 🚨 FinRo.ro Server Alert\nFrom: alerts@finro.ro\nTo: ${ALERT_EMAIL}\n\n${ALERT_MSG}\n\nTimestamp: ${TS}\nServer: $(hostname)\n\nFailed checks:\n$(printf '  • %s\n' "${FAILURES[@]}")" | msmtp "$ALERT_EMAIL"
            echo "[$TS] Email alert sent to ${ALERT_EMAIL}" >> $LOG_FILE
        fi
    fi
fi

# Print to stdout if running manually
if [ -t 1 ]; then
    echo ""
    echo "═══ FinRo.ro Health Check ═══"
    tail -20 $LOG_FILE
fi
