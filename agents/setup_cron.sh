#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# FinRo.ro — Cron Setup for Automated Content Agents
# 4 Agents, Twice Daily (Morning + Afternoon)
# ═══════════════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "══════════════════════════════════════"
echo " FinRo.ro Agent Cron Setup"
echo "══════════════════════════════════════"
echo ""
echo "Select agent runtime:"
echo "  1) Python"
echo "  2) Node.js"
read -p "Choice [1/2]: " RUNTIME

if [ "$RUNTIME" = "2" ]; then
    echo "Installing Node.js dependencies..."
    cd "$SCRIPT_DIR/nodejs" && npm install
    CMD1="cd $SCRIPT_DIR/nodejs && /usr/bin/node agent_finance.js"
    CMD2="cd $SCRIPT_DIR/nodejs && /usr/bin/node agent_insurance.js"
    CMD3="cd $SCRIPT_DIR/nodejs && /usr/bin/node agent_tech.js"
    CMD4="cd $SCRIPT_DIR/nodejs && /usr/bin/node agent_investitii.js"
else
    echo "Installing Python dependencies..."
    pip install -r "$SCRIPT_DIR/python/requirements.txt" --break-system-packages -q
    CMD1="cd $SCRIPT_DIR/python && /usr/bin/python3 agent_finance.py"
    CMD2="cd $SCRIPT_DIR/python && /usr/bin/python3 agent_insurance.py"
    CMD3="cd $SCRIPT_DIR/python && /usr/bin/python3 agent_tech.py"
    CMD4="cd $SCRIPT_DIR/python && /usr/bin/python3 agent_investitii.py"
fi

sudo mkdir -p /var/log/finro
sudo chown $(whoami) /var/log/finro

echo "Installing cron jobs (twice daily)..."
(crontab -l 2>/dev/null | grep -v "finro"; cat <<EOF
# ═══ FinRo.ro — TWICE DAILY Content Agents ═══
# ─── MORNING (daily, all week) ───
0 4 * * * $CMD1 >> /var/log/finro/finance.log 2>&1
30 4 * * * $CMD2 >> /var/log/finro/insurance.log 2>&1
0 5 * * * $CMD3 >> /var/log/finro/tech.log 2>&1
30 5 * * * $CMD4 >> /var/log/finro/investitii.log 2>&1

# ─── AFTERNOON (Mon-Fri only, catches BNR/BVB/ZF updates) ───
0 13 * * 1-5 $CMD1 >> /var/log/finro/finance.log 2>&1
30 13 * * 1-5 $CMD2 >> /var/log/finro/insurance.log 2>&1
0 14 * * 1-5 $CMD3 >> /var/log/finro/tech.log 2>&1
30 14 * * 1-5 $CMD4 >> /var/log/finro/investitii.log 2>&1
EOF
) | crontab -

echo ""
echo "✓ Cron installed! Schedule (EET):"
echo ""
echo "  MORNING (daily):"
echo "    06:00  Finance"
echo "    06:30  Insurance"
echo "    07:00  Tech"
echo "    07:30  Investitii"
echo ""
echo "  AFTERNOON (Mon-Fri):"
echo "    15:00  Finance    ← catches BNR exchange rates"
echo "    15:30  Insurance  ← catches ASF updates"
echo "    16:00  Tech"
echo "    16:30  Investitii ← catches BVB closing data"
echo ""
echo "  Deduplication ensures no duplicate articles."
echo "  Logs: /var/log/finro/"
echo "  Verify: crontab -l"
