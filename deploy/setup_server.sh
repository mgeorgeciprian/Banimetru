#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# FinRo.ro — Server Setup Script
# Target: Hetzner Cloud CX22 / Ubuntu 24.04 LTS
# Run as root: curl -sL https://raw.githubusercontent.com/.../setup.sh | bash
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration (EDIT THESE) ───
DOMAIN="finro.ro"
EMAIL="george@amatech.ro"          # For Let's Encrypt notifications
PROJECT_DIR="/var/www/finro"
AGENT_RUNTIME="python"              # "python" or "nodejs"
SWAP_SIZE="2G"                      # Swap for 2GB RAM servers

# ─── Colors ───
RED='\033[0;31m'
GREEN='\033[0;32m'
GOLD='\033[0;33m'
NC='\033[0m'

echo -e "${GOLD}"
echo "═══════════════════════════════════════"
echo "  FinRo.ro Server Setup"
echo "  Target: Ubuntu 24.04 + nginx"
echo "═══════════════════════════════════════"
echo -e "${NC}"

# ─── 1. System Update ───
echo -e "${GREEN}[1/10] Updating system...${NC}"
apt update && apt upgrade -y
apt install -y \
    nginx \
    certbot python3-certbot-nginx \
    ufw \
    fail2ban \
    git \
    curl \
    wget \
    unzip \
    htop \
    logrotate \
    cron

# ─── 2. Create Swap (for small VPS) ───
echo -e "${GREEN}[2/10] Setting up swap...${NC}"
if [ ! -f /swapfile ]; then
    fallocate -l $SWAP_SIZE /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Optimize for low-RAM servers
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    echo "  Swap created: $SWAP_SIZE"
else
    echo "  Swap already exists"
fi

# ─── 3. Firewall (UFW) ───
echo -e "${GREEN}[3/10] Configuring firewall...${NC}"
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 'Nginx Full'    # HTTP + HTTPS
ufw --force enable
echo "  Firewall active: SSH + HTTP + HTTPS allowed"

# ─── 4. Fail2Ban ───
echo -e "${GREEN}[4/10] Configuring fail2ban...${NC}"
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
ignoreip = 127.0.0.1/8

[sshd]
enabled = true
port = ssh
maxretry = 3

[nginx-http-auth]
enabled = true

[nginx-botsearch]
enabled = true

[nginx-req-limit]
enabled = true
filter = nginx-req-limit
action = iptables-multiport[name=ReqLimit, port="http,https", protocol=tcp]
logpath = /var/log/nginx/error.log
findtime = 60
maxretry = 20
bantime = 7200
EOF

cat > /etc/fail2ban/filter.d/nginx-req-limit.conf << 'EOF'
[Definition]
failregex = limiting requests, excess:.* by zone.*client: <HOST>
ignoreregex =
EOF

systemctl enable fail2ban
systemctl restart fail2ban

# ─── 5. Create App User ───
echo -e "${GREEN}[5/10] Creating app user...${NC}"
if ! id "finro" &>/dev/null; then
    useradd -m -s /bin/bash -d /home/finro finro
    usermod -aG www-data finro
    echo "  User 'finro' created"
else
    echo "  User 'finro' already exists"
fi

# ─── 6. Project Directory ───
echo -e "${GREEN}[6/10] Setting up project directories...${NC}"
mkdir -p $PROJECT_DIR/{website,agents,logs,backups}
mkdir -p $PROJECT_DIR/website/{articles/{finante,asigurari,tech},data,css,js}
mkdir -p /var/log/finro

chown -R finro:www-data $PROJECT_DIR
chmod -R 755 $PROJECT_DIR
chown -R finro:finro /var/log/finro

echo "  Project dir: $PROJECT_DIR"

# ─── 7. Install Runtime ───
echo -e "${GREEN}[7/10] Installing agent runtime...${NC}"
if [ "$AGENT_RUNTIME" = "nodejs" ]; then
    # Node.js 20 LTS
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt install -y nodejs
    echo "  Node.js $(node -v) installed"
    
    # Install agent dependencies
    if [ -f "$PROJECT_DIR/agents/nodejs/package.json" ]; then
        cd $PROJECT_DIR/agents/nodejs
        sudo -u finro npm install
    fi
else
    # Python 3 (usually pre-installed on Ubuntu 24.04)
    apt install -y python3 python3-pip python3-venv
    echo "  Python $(python3 --version) installed"
    
    # Create virtualenv for agents
    sudo -u finro python3 -m venv $PROJECT_DIR/agents/python/venv
    if [ -f "$PROJECT_DIR/agents/python/requirements.txt" ]; then
        sudo -u finro $PROJECT_DIR/agents/python/venv/bin/pip install -r $PROJECT_DIR/agents/python/requirements.txt
    fi
fi

# ─── 8. Nginx Configuration ───
echo -e "${GREEN}[8/10] Configuring nginx...${NC}"

# Main nginx.conf optimizations
cat > /etc/nginx/nginx.conf << 'NGINX_MAIN'
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 1024;
    multi_accept on;
}

http {
    # ─── Basic ───
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_tokens off;
    client_max_body_size 10m;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # ─── Logging ───
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # ─── Gzip Compression ───
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml
        application/rss+xml
        application/atom+xml
        image/svg+xml
        font/woff2;

    # ─── Rate Limiting ───
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=static:10m rate=30r/s;

    # ─── Includes ───
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
NGINX_MAIN

# Site configuration
cat > /etc/nginx/sites-available/finro << NGINX_SITE
# ═══════════════════════════════════════
# FinRo.ro — nginx site configuration
# ═══════════════════════════════════════

# Redirect www to non-www
server {
    listen 80;
    listen [::]:80;
    server_name www.$DOMAIN;
    return 301 https://$DOMAIN\$request_uri;
}

# Main site
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    root $PROJECT_DIR/website;
    index index.html;

    # ─── Security Headers ───
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://pagead2.googlesyndication.com https://adservice.google.com https://www.googletagmanager.com https://fonts.googleapis.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://pagead2.googlesyndication.com https://*.google.com; frame-src https://googleads.g.doubleclick.net https://tpc.googlesyndication.com;" always;

    # ─── Static Asset Caching ───
    location ~* \.(css|js)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
        limit_req zone=static burst=20 nodelay;
    }

    location ~* \.(jpg|jpeg|png|gif|ico|svg|webp|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        limit_req zone=static burst=20 nodelay;
    }

    # ─── HTML Pages (shorter cache for fresh content) ───
    location ~* \.html$ {
        expires 1h;
        add_header Cache-Control "public, must-revalidate";
        limit_req zone=general burst=10 nodelay;
    }

    # ─── JSON Data API ───
    location /data/ {
        expires 15m;
        add_header Cache-Control "public, must-revalidate";
        add_header Access-Control-Allow-Origin "*";
    }

    # ─── Article Routes (clean URLs) ───
    location /finante/ {
        alias $PROJECT_DIR/website/articles/finante/;
        try_files \$uri \$uri.html \$uri/ =404;
    }

    location /asigurari/ {
        alias $PROJECT_DIR/website/articles/asigurari/;
        try_files \$uri \$uri.html \$uri/ =404;
    }

    location /tech/ {
        alias $PROJECT_DIR/website/articles/tech/;
        try_files \$uri \$uri.html \$uri/ =404;
    }

    location /investitii/ {
        alias $PROJECT_DIR/website/articles/investitii/;
        try_files \$uri \$uri.html \$uri/ =404;
    }

    # ─── Sitemap & Robots ───
    location = /robots.txt {
        add_header Content-Type text/plain;
        return 200 "User-agent: *\nAllow: /\nSitemap: https://$DOMAIN/sitemap.xml\n\nUser-agent: FinRo-Bot\nAllow: /\n";
    }

    location = /sitemap.xml {
        root $PROJECT_DIR/website;
    }

    # ─── ads.txt (required for AdSense) ───
    location = /ads.txt {
        root $PROJECT_DIR/website;
        default_type text/plain;
    }

    # ─── Error Pages ───
    error_page 404 /404.html;
    location = /404.html {
        root $PROJECT_DIR/website;
        internal;
    }

    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
        internal;
    }

    # ─── Block common exploits ───
    location ~ /\. { deny all; }
    location ~* (\.php|\.asp|\.aspx|\.jsp|\.cgi)$ { return 444; }
    location ~ /wp- { return 444; }

    # ─── Default ───
    location / {
        try_files \$uri \$uri/ \$uri.html /index.html;
        limit_req zone=general burst=10 nodelay;
    }
}
NGINX_SITE

# Enable site
ln -sf /etc/nginx/sites-available/finro /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx config
nginx -t
systemctl restart nginx
echo "  nginx configured and running"

# ─── 9. SSL Certificate (Let's Encrypt) ───
echo -e "${GREEN}[9/10] Setting up SSL...${NC}"
echo ""
echo "  To get SSL certificate, make sure DNS is pointing to this server, then run:"
echo "  certbot --nginx -d $DOMAIN -d www.$DOMAIN --email $EMAIL --agree-tos --non-interactive"
echo ""
echo "  Or run manually: certbot --nginx -d $DOMAIN"
echo ""

# Auto-renewal cron (certbot usually sets this up, but let's be sure)
echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'" | crontab -u root -

# ─── 10. Agent Cron Jobs ───
echo -e "${GREEN}[10/10] Setting up agent cron jobs...${NC}"

if [ "$AGENT_RUNTIME" = "nodejs" ]; then
    AGENT_CMD_1="cd $PROJECT_DIR/agents/nodejs && /usr/bin/node agent_finance.js"
    AGENT_CMD_2="cd $PROJECT_DIR/agents/nodejs && /usr/bin/node agent_insurance.js"
    AGENT_CMD_3="cd $PROJECT_DIR/agents/nodejs && /usr/bin/node agent_tech.js"
    AGENT_CMD_4="cd $PROJECT_DIR/agents/nodejs && /usr/bin/node agent_investitii.js"
else
    VENV="$PROJECT_DIR/agents/python/venv/bin/python3"
    AGENT_CMD_1="cd $PROJECT_DIR/agents/python && $VENV agent_finance.py"
    AGENT_CMD_2="cd $PROJECT_DIR/agents/python && $VENV agent_insurance.py"
    AGENT_CMD_3="cd $PROJECT_DIR/agents/python && $VENV agent_tech.py"
    AGENT_CMD_4="cd $PROJECT_DIR/agents/python && $VENV agent_investitii.py"
fi

# Set up cron for finro user
sudo -u finro bash -c "cat << CRON | crontab -
# FinRo.ro Content Agents — TWICE DAILY
# ─── MORNING RUN (overnight & international content) ───
# Finance — 06:00 EET (04:00 UTC)
0 4 * * * $AGENT_CMD_1 >> /var/log/finro/finance.log 2>&1
# Insurance — 06:30 EET (04:30 UTC)
30 4 * * * $AGENT_CMD_2 >> /var/log/finro/insurance.log 2>&1
# Tech — 07:00 EET (05:00 UTC)
0 5 * * * $AGENT_CMD_3 >> /var/log/finro/tech.log 2>&1
# Investitii — 07:30 EET (05:30 UTC)
30 5 * * * $AGENT_CMD_4 >> /var/log/finro/investitii.log 2>&1

# ─── AFTERNOON RUN Mon-Fri (BNR updates, ZF, BVB closing) ───
# Finance — 15:00 EET (13:00 UTC)
0 13 * * 1-5 $AGENT_CMD_1 >> /var/log/finro/finance.log 2>&1
# Insurance — 15:30 EET (13:30 UTC)
30 13 * * 1-5 $AGENT_CMD_2 >> /var/log/finro/insurance.log 2>&1
# Tech — 16:00 EET (14:00 UTC)
0 14 * * 1-5 $AGENT_CMD_3 >> /var/log/finro/tech.log 2>&1
# Investitii — 16:30 EET (14:30 UTC)
30 14 * * 1-5 $AGENT_CMD_4 >> /var/log/finro/investitii.log 2>&1

# Weekly backup — Sunday 02:00 EET
0 0 * * 0 tar -czf $PROJECT_DIR/backups/articles-\\\$(date +\\%Y\\%m\\%d).tar.gz -C $PROJECT_DIR/website articles/ data/
CRON"

echo "  Cron jobs installed for user 'finro'"

# ─── Log Rotation ───
cat > /etc/logrotate.d/finro << 'LOGROTATE'
/var/log/finro/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 finro finro
}
LOGROTATE

# ─── Email Alerts (msmtp) ───
echo -e "${GREEN}[+] Configuring email alerts via msmtp...${NC}"
apt install -y msmtp msmtp-mta

cat > /etc/msmtprc << 'MSMTP'
# FinRo.ro — msmtp config for alert emails
# Supports Gmail, Outlook, or any SMTP provider
# For Gmail: enable App Passwords at myaccount.google.com/apppasswords

defaults
auth           on
tls            on
tls_trust_file /etc/ssl/certs/ca-certificates.crt
logfile        /var/log/msmtp.log

# ─── EDIT THIS SECTION ───
account        default
host           smtp.gmail.com
port           587
from           alerts@finro.ro
user           YOUR_EMAIL@gmail.com
password       YOUR_APP_PASSWORD
MSMTP

chmod 600 /etc/msmtprc
echo "  msmtp installed — edit /etc/msmtprc with your SMTP credentials"

# ─── Healthcheck Cron (every 5 min with alerts) ───
if [ -f "$PROJECT_DIR/deploy/healthcheck.sh" ]; then
    chmod +x $PROJECT_DIR/deploy/healthcheck.sh
    echo "*/5 * * * * $PROJECT_DIR/deploy/healthcheck.sh --notify >> /var/log/finro/healthcheck.log 2>&1" >> /tmp/finro_health_cron
    crontab -u finro /tmp/finro_health_cron
    rm /tmp/finro_health_cron
    echo "  Healthcheck running every 5 minutes with Telegram + Email alerts"
fi

# ─── Create ads.txt placeholder ───
echo "# Replace with your AdSense publisher ID" > $PROJECT_DIR/website/ads.txt
echo "# google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0" >> $PROJECT_DIR/website/ads.txt
chown finro:www-data $PROJECT_DIR/website/ads.txt

# ─── Summary ───
echo ""
echo -e "${GOLD}═══════════════════════════════════════${NC}"
echo -e "${GOLD}  Setup Complete!${NC}"
echo -e "${GOLD}═══════════════════════════════════════${NC}"
echo ""
echo "  Domain:       $DOMAIN"
echo "  Web root:     $PROJECT_DIR/website/"
echo "  Agents:       $PROJECT_DIR/agents/"
echo "  Logs:         /var/log/finro/"
echo "  Backups:      $PROJECT_DIR/backups/"
echo "  Runtime:      $AGENT_RUNTIME"
echo ""
echo "  Next steps:"
echo "  1. Upload your project files to $PROJECT_DIR/"
echo "     scp -r finro/* finro@YOUR_SERVER_IP:$PROJECT_DIR/"
echo ""
echo "  2. Point DNS (Cloudflare) A record:"
echo "     $DOMAIN → $(curl -s ifconfig.me)"
echo "     www.$DOMAIN → $(curl -s ifconfig.me)"
echo ""
echo "  3. Get SSL certificate:"
echo "     certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo ""
echo "  4. Update ads.txt with your AdSense publisher ID"
echo ""
echo "  5. Test agents:"
echo "     sudo -u finro $AGENT_CMD_1 --dry-run"
echo ""
echo -e "${GREEN}  Server is ready! 🚀${NC}"
