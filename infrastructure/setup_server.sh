#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# FinRo.ro — Complete Server Setup Script
# ═══════════════════════════════════════════════════════════════════════
# Target: Hetzner Cloud CX22 (Ubuntu 24.04 LTS)
# Run as root on a fresh VPS: bash setup_server.sh
#
# What this does:
#   1. System update & security hardening
#   2. Creates deploy user with SSH key auth
#   3. Installs nginx, Python 3, Node.js 20, certbot
#   4. Configures nginx for finro.ro with SSL
#   5. Sets up project directories
#   6. Installs agent dependencies
#   7. Configures cron jobs for daily agents
#   8. Sets up UFW firewall
#   9. Configures fail2ban
#  10. Sets up log rotation
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── CONFIGURATION (EDIT THESE) ───
DOMAIN="finro.ro"
DOMAIN_WWW="www.finro.ro"
DEPLOY_USER="deploy"
EMAIL="george@finro.ro"              # For Let's Encrypt notifications
SSH_PORT=2222                         # Custom SSH port (security)
TIMEZONE="Europe/Bucharest"
PROJECT_DIR="/var/www/finro"
AGENT_RUNTIME="python"               # "python" or "nodejs"

# ─── Colors ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  FinRo.ro Server Setup — $(date)"
echo "  Domain: ${DOMAIN}"
echo "  VPS: $(hostname)"
echo "═══════════════════════════════════════════════════════"
echo ""

# ─── Check root ───
if [ "$EUID" -ne 0 ]; then
    err "Please run as root: sudo bash setup_server.sh"
fi

# ═══════════════════════════════════════
# PHASE 1: System Basics
# ═══════════════════════════════════════
info "Phase 1: System update & basics"

# Set timezone
timedatectl set-timezone "$TIMEZONE"
log "Timezone set to $TIMEZONE"

# Update system
apt update && apt upgrade -y
apt install -y \
    curl wget git unzip htop nano \
    software-properties-common \
    apt-transport-https ca-certificates \
    gnupg lsb-release
log "System updated"

# ═══════════════════════════════════════
# PHASE 2: Create Deploy User
# ═══════════════════════════════════════
info "Phase 2: Creating deploy user"

if ! id "$DEPLOY_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
    usermod -aG sudo "$DEPLOY_USER"
    
    # Copy root SSH keys to deploy user
    mkdir -p /home/$DEPLOY_USER/.ssh
    if [ -f /root/.ssh/authorized_keys ]; then
        cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/
    fi
    chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
    chmod 700 /home/$DEPLOY_USER/.ssh
    chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys 2>/dev/null || true
    
    # Allow deploy user sudo without password for deployments
    echo "$DEPLOY_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx, /usr/bin/systemctl restart nginx" > /etc/sudoers.d/$DEPLOY_USER
    chmod 440 /etc/sudoers.d/$DEPLOY_USER
    log "User '$DEPLOY_USER' created with SSH keys"
else
    warn "User '$DEPLOY_USER' already exists, skipping"
fi

# ═══════════════════════════════════════
# PHASE 3: SSH Hardening
# ═══════════════════════════════════════
info "Phase 3: SSH hardening"

# Backup original sshd config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup

cat > /etc/ssh/sshd_config.d/finro-hardening.conf << EOF
# FinRo SSH Hardening
Port ${SSH_PORT}
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowUsers ${DEPLOY_USER} root
EOF

systemctl restart sshd
log "SSH hardened on port $SSH_PORT (key-only auth)"
warn "IMPORTANT: Test SSH on new port before closing this session!"
warn "  ssh -p $SSH_PORT $DEPLOY_USER@$(curl -s ifconfig.me)"

# ═══════════════════════════════════════
# PHASE 4: Firewall (UFW)
# ═══════════════════════════════════════
info "Phase 4: Configuring firewall"

apt install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow $SSH_PORT/tcp comment "SSH"
ufw allow 80/tcp comment "HTTP"
ufw allow 443/tcp comment "HTTPS"
ufw --force enable
log "UFW firewall active (SSH:$SSH_PORT, HTTP, HTTPS)"

# ═══════════════════════════════════════
# PHASE 5: Fail2ban
# ═══════════════════════════════════════
info "Phase 5: Installing fail2ban"

apt install -y fail2ban

cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ${SSH_PORT}
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 86400

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
maxretry = 10
findtime = 60
bantime = 7200
EOF

systemctl enable fail2ban
systemctl restart fail2ban
log "Fail2ban configured"

# ═══════════════════════════════════════
# PHASE 6: Install nginx
# ═══════════════════════════════════════
info "Phase 6: Installing nginx"

apt install -y nginx
systemctl enable nginx

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Performance tuning
cat > /etc/nginx/conf.d/performance.conf << 'EOF'
# FinRo nginx performance tuning
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_min_length 256;
gzip_types
    text/plain
    text/css
    text/xml
    text/javascript
    application/json
    application/javascript
    application/xml
    application/rss+xml
    image/svg+xml;

# Security headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# Connection limits
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=static:10m rate=30r/s;
EOF

log "nginx installed and tuned"

# ═══════════════════════════════════════
# PHASE 7: nginx Site Configuration
# ═══════════════════════════════════════
info "Phase 7: Configuring nginx for $DOMAIN"

cat > /etc/nginx/sites-available/finro << NGINXEOF
# ═══════════════════════════════════════
# FinRo.ro — nginx Configuration
# ═══════════════════════════════════════

# Redirect HTTP → HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${DOMAIN_WWW};
    
    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://${DOMAIN}\$request_uri;
    }
}

# Redirect www → non-www (HTTPS)
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${DOMAIN_WWW};
    
    # SSL certs (will be configured by certbot)
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    
    return 301 https://${DOMAIN}\$request_uri;
}

# Main site
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};
    
    root ${PROJECT_DIR}/website;
    index index.html;
    
    # SSL
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    
    # Logging
    access_log /var/log/nginx/finro_access.log;
    error_log /var/log/nginx/finro_error.log;
    
    # ─── Static Assets — Long cache ───
    location ~* \.(css|js|jpg|jpeg|png|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        add_header Vary "Accept-Encoding";
        limit_req zone=static burst=50 nodelay;
        try_files \$uri =404;
    }
    
    # ─── HTML pages — Short cache for fresh content ───
    location ~* \.html$ {
        expires 1h;
        add_header Cache-Control "public, must-revalidate";
        limit_req zone=general burst=20 nodelay;
        try_files \$uri =404;
    }
    
    # ─── JSON data (article indexes) ───
    location /data/ {
        expires 30m;
        add_header Cache-Control "public";
        add_header Access-Control-Allow-Origin "*";
        try_files \$uri =404;
    }
    
    # ─── Article pretty URLs ───
    # /finante/article-slug → /articles/finante/article-slug.html
    location /finante/ {
        try_files /articles/finante/\$uri.html /articles/finante/\$uri /finante/index.html =404;
    }
    
    location /asigurari/ {
        try_files /articles/asigurari/\$uri.html /articles/asigurari/\$uri /asigurari/index.html =404;
    }
    
    location /tech/ {
        try_files /articles/tech/\$uri.html /articles/tech/\$uri /tech/index.html =404;
    }
    
    # ─── Main pages ───
    location / {
        limit_req zone=general burst=20 nodelay;
        try_files \$uri \$uri/ /index.html;
    }
    
    # ─── Security: Block sensitive files ───
    location ~ /\. { deny all; }
    location ~* \.(git|env|log|bak|sql|sh)$ { deny all; }
    
    # ─── Sitemap ───
    location = /sitemap.xml {
        try_files /sitemap.xml =404;
    }
    
    # ─── Robots.txt ───
    location = /robots.txt {
        try_files /robots.txt =404;
    }
    
    # ─── ads.txt (required for AdSense) ───
    location = /ads.txt {
        try_files /ads.txt =404;
    }
    
    # ─── Custom error pages ───
    error_page 404 /404.html;
    error_page 500 502 503 504 /50x.html;
}
NGINXEOF

ln -sf /etc/nginx/sites-available/finro /etc/nginx/sites-enabled/finro
log "nginx site configured for $DOMAIN"

# ═══════════════════════════════════════
# PHASE 8: Project Directories
# ═══════════════════════════════════════
info "Phase 8: Creating project directories"

mkdir -p $PROJECT_DIR/{website/{css,js,articles/{finante,asigurari,tech},data,images},agents/{python,nodejs}}
mkdir -p /var/www/certbot
mkdir -p /var/log/finro

# Set ownership
chown -R $DEPLOY_USER:$DEPLOY_USER $PROJECT_DIR
chown -R $DEPLOY_USER:$DEPLOY_USER /var/log/finro

# Create placeholder index for initial test
cat > $PROJECT_DIR/website/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html><head><title>FinRo.ro — Coming Soon</title></head>
<body style="background:#0A0E17;color:#F1F3F8;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center"><h1 style="color:#D4A843">FinRo.ro</h1><p>Site-ul se configurează. Revino curând!</p></div>
</body></html>
HTMLEOF

# Create robots.txt
cat > $PROJECT_DIR/website/robots.txt << 'ROBOTSEOF'
User-agent: *
Allow: /

Sitemap: https://finro.ro/sitemap.xml

# Block agent directories
Disallow: /data/seen_*.json
ROBOTSEOF

# Create ads.txt placeholder
cat > $PROJECT_DIR/website/ads.txt << 'ADSEOF'
# Replace with your actual AdSense publisher ID
# google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0
ADSEOF

chown -R $DEPLOY_USER:$DEPLOY_USER $PROJECT_DIR
log "Project directories created at $PROJECT_DIR"

# ═══════════════════════════════════════
# PHASE 9: SSL with Let's Encrypt
# ═══════════════════════════════════════
info "Phase 9: SSL certificate setup"

apt install -y certbot python3-certbot-nginx

# First, test nginx config with HTTP only (comment out SSL blocks)
# Create temporary HTTP-only config for initial cert
cat > /etc/nginx/sites-available/finro-temp << TEMPEOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${DOMAIN_WWW};
    root ${PROJECT_DIR}/website;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
TEMPEOF

# Use temp config for cert generation
rm -f /etc/nginx/sites-enabled/finro
ln -sf /etc/nginx/sites-available/finro-temp /etc/nginx/sites-enabled/finro-temp
nginx -t && systemctl reload nginx

info "Requesting SSL certificate..."
info "Make sure DNS A records point to this server first!"
warn "If this fails, run certbot manually after DNS is set up:"
warn "  certbot --nginx -d $DOMAIN -d $DOMAIN_WWW --email $EMAIL --agree-tos"

certbot certonly --webroot -w /var/www/certbot \
    -d $DOMAIN -d $DOMAIN_WWW \
    --email $EMAIL --agree-tos --non-interactive || {
    warn "SSL cert request failed — DNS may not be pointed yet."
    warn "After pointing DNS, run:"
    warn "  certbot --nginx -d $DOMAIN -d $DOMAIN_WWW --email $EMAIL --agree-tos"
    warn "Then: rm /etc/nginx/sites-enabled/finro-temp"
    warn "Then: ln -sf /etc/nginx/sites-available/finro /etc/nginx/sites-enabled/finro"
    warn "Then: systemctl reload nginx"
}

# Switch to full config if cert exists
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    rm -f /etc/nginx/sites-enabled/finro-temp
    ln -sf /etc/nginx/sites-available/finro /etc/nginx/sites-enabled/finro
    nginx -t && systemctl reload nginx
    log "SSL active! HTTPS configured."
    
    # Auto-renewal cron
    echo "0 3 * * * root certbot renew --quiet --post-hook 'systemctl reload nginx'" > /etc/cron.d/certbot-renew
    log "SSL auto-renewal configured"
else
    warn "Running on HTTP only until SSL is configured"
fi

# ═══════════════════════════════════════
# PHASE 10: Python 3 + Node.js 20
# ═══════════════════════════════════════
info "Phase 10: Installing runtimes"

# Python
apt install -y python3 python3-pip python3-venv
log "Python $(python3 --version) installed"

# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
log "Node.js $(node --version) installed"

# ═══════════════════════════════════════
# PHASE 11: Agent Dependencies
# ═══════════════════════════════════════
info "Phase 11: Installing agent dependencies"

# Python deps (in virtual env)
su - $DEPLOY_USER << 'PYSETUP'
cd /var/www/finro
python3 -m venv agents/python/venv
source agents/python/venv/bin/activate
pip install requests beautifulsoup4 feedparser python-slugify
deactivate
PYSETUP
log "Python agent venv created"

# Node.js deps
su - $DEPLOY_USER << 'NODESETUP'
cd /var/www/finro/agents/nodejs
if [ -f package.json ]; then
    npm install
fi
NODESETUP
log "Node.js agent deps installed"

# ═══════════════════════════════════════
# PHASE 12: Cron Jobs for Agents
# ═══════════════════════════════════════
info "Phase 12: Setting up agent cron jobs"

if [ "$AGENT_RUNTIME" = "nodejs" ]; then
    AGENT1="cd $PROJECT_DIR/agents/nodejs && /usr/bin/node agent_finance.js"
    AGENT2="cd $PROJECT_DIR/agents/nodejs && /usr/bin/node agent_insurance.js"
    AGENT3="cd $PROJECT_DIR/agents/nodejs && /usr/bin/node agent_tech.js"
else
    AGENT1="cd $PROJECT_DIR/agents/python && source venv/bin/activate && python3 agent_finance.py && deactivate"
    AGENT2="cd $PROJECT_DIR/agents/python && source venv/bin/activate && python3 agent_insurance.py && deactivate"
    AGENT3="cd $PROJECT_DIR/agents/python && source venv/bin/activate && python3 agent_tech.py && deactivate"
fi

# Install cron for deploy user
su - $DEPLOY_USER -c "crontab -" << CRONEOF
# ═══ FinRo.ro Content Agents ═══
# Finance: 06:00 EET (04:00 UTC)
0 4 * * * $AGENT1 >> /var/log/finro/agent_finance.log 2>&1

# Insurance: 07:00 EET (05:00 UTC)
0 5 * * * $AGENT2 >> /var/log/finro/agent_insurance.log 2>&1

# Tech: 08:00 EET (06:00 UTC)
0 6 * * * $AGENT3 >> /var/log/finro/agent_tech.log 2>&1

# Sitemap rebuild: 09:00 EET (07:00 UTC)
0 7 * * * cd $PROJECT_DIR && /usr/bin/python3 agents/python/build_sitemap.py >> /var/log/finro/sitemap.log 2>&1
CRONEOF
log "Cron jobs configured for $AGENT_RUNTIME agents"

# ═══════════════════════════════════════
# PHASE 13: Log Rotation
# ═══════════════════════════════════════
info "Phase 13: Log rotation"

cat > /etc/logrotate.d/finro << 'LOGEOF'
/var/log/finro/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 deploy deploy
}

/var/log/nginx/finro_*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 $(cat /var/run/nginx.pid)
    endscript
}
LOGEOF
log "Log rotation configured"

# ═══════════════════════════════════════
# PHASE 14: Swap (for small VPS)
# ═══════════════════════════════════════
info "Phase 14: Configuring swap"

if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    log "2GB swap configured"
else
    warn "Swap already exists"
fi

# ═══════════════════════════════════════
# DONE
# ═══════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════"
echo -e "  ${GREEN}FinRo.ro Server Setup Complete!${NC}"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Server IP:    $(curl -s ifconfig.me)"
echo "  SSH Port:     $SSH_PORT"
echo "  SSH User:     $DEPLOY_USER"
echo "  Web Root:     $PROJECT_DIR/website/"
echo "  Agent Logs:   /var/log/finro/"
echo "  nginx Logs:   /var/log/nginx/finro_*.log"
echo ""
echo "  ─── NEXT STEPS ───"
echo ""
echo "  1. DNS: Add A records at Cloudflare:"
echo "     ${DOMAIN}     →  $(curl -s ifconfig.me)"
echo "     ${DOMAIN_WWW} →  $(curl -s ifconfig.me)"
echo ""
echo "  2. TEST SSH (from your local machine):"
echo "     ssh -p $SSH_PORT $DEPLOY_USER@$(curl -s ifconfig.me)"
echo ""
echo "  3. DEPLOY CODE (from your local machine):"
echo "     scp -P $SSH_PORT -r finro/website/* $DEPLOY_USER@$(curl -s ifconfig.me):$PROJECT_DIR/website/"
echo "     scp -P $SSH_PORT -r finro/agents/* $DEPLOY_USER@$(curl -s ifconfig.me):$PROJECT_DIR/agents/"
echo ""
echo "  4. SSL (if not auto-configured):"
echo "     certbot --nginx -d $DOMAIN -d $DOMAIN_WWW --email $EMAIL --agree-tos"
echo ""
echo "  5. AdSense: Update ads.txt with your publisher ID"
echo ""
echo "═══════════════════════════════════════════════════════"
