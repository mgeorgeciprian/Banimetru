#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# FinRo.ro — Deploy Script
# ═══════════════════════════════════════════════════════════════════════
# Run from your LOCAL machine to deploy/update the website and agents.
# Usage: bash deploy.sh [full|website|agents]
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── CONFIGURATION ───
SERVER_IP="YOUR_SERVER_IP"        # ← Replace with Hetzner VPS IP
SSH_PORT=2222
DEPLOY_USER="deploy"
REMOTE_DIR="/var/www/finro"

# ─── Colors ───
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'
log() { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${CYAN}[→]${NC} $1"; }

SSH_CMD="ssh -p $SSH_PORT $DEPLOY_USER@$SERVER_IP"
SCP_CMD="scp -P $SSH_PORT"

DEPLOY_TYPE="${1:-full}"

echo ""
echo "═══════════════════════════════════════"
echo "  FinRo.ro Deploy — $DEPLOY_TYPE"
echo "═══════════════════════════════════════"
echo ""

# ─── Deploy Website ───
if [ "$DEPLOY_TYPE" = "full" ] || [ "$DEPLOY_TYPE" = "website" ]; then
    info "Deploying website files..."
    
    # Sync website files (exclude data/ to preserve generated articles)
    rsync -avz --delete \
        --exclude 'articles/' \
        --exclude 'data/' \
        -e "ssh -p $SSH_PORT" \
        website/ $DEPLOY_USER@$SERVER_IP:$REMOTE_DIR/website/
    
    log "Website deployed"
fi

# ─── Deploy Agents ───
if [ "$DEPLOY_TYPE" = "full" ] || [ "$DEPLOY_TYPE" = "agents" ]; then
    info "Deploying agent files..."
    
    # Sync Python agents
    rsync -avz \
        --exclude 'venv/' \
        --exclude 'logs/' \
        --exclude '__pycache__/' \
        -e "ssh -p $SSH_PORT" \
        agents/python/ $DEPLOY_USER@$SERVER_IP:$REMOTE_DIR/agents/python/
    
    # Sync Node.js agents
    rsync -avz \
        --exclude 'node_modules/' \
        --exclude 'logs/' \
        -e "ssh -p $SSH_PORT" \
        agents/nodejs/ $DEPLOY_USER@$SERVER_IP:$REMOTE_DIR/agents/nodejs/
    
    # Install deps on server
    info "Installing agent dependencies on server..."
    $SSH_CMD << 'REMOTE'
        cd /var/www/finro/agents/python
        if [ -d venv ]; then
            source venv/bin/activate
            pip install -r requirements.txt -q
            deactivate
        fi
        
        cd /var/www/finro/agents/nodejs
        if [ -f package.json ]; then
            npm install --production 2>/dev/null
        fi
REMOTE
    
    log "Agents deployed"
fi

# ─── Reload nginx ───
info "Reloading nginx..."
$SSH_CMD "sudo systemctl reload nginx"
log "nginx reloaded"

echo ""
echo "═══════════════════════════════════════"
echo -e "  ${GREEN}Deploy complete!${NC}"
echo "  https://finro.ro"
echo "═══════════════════════════════════════"
echo ""
