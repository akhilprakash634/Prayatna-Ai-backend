#!/usr/bin/env bash
set -e

# ==============================================================================
# Prayatna AI - Automated Nginx Reverse Proxy & SSL (Let's Encrypt) Setup
# ==============================================================================

DOMAIN="${1:-prayatna.demoapi.thescalecraft.in}"
EMAIL="${2:-akhilprakash634@gmail.com}"

# Sanitize inputs (in case of duplicate paste)
DOMAIN=$(echo "$DOMAIN" | awk '{print $1}' | sed 's/[^a-zA-Z0-9.-]//g')
EMAIL=$(echo "$EMAIL" | awk '{print $1}' | grep -o '[a-zA-Z0-9._%+-]\+@[a-zA-Z0-9.-]\+\.[a-zA-Z]\{2,\}' | head -n1 || echo "akhilprakash634@gmail.com")
if [ -z "$EMAIL" ]; then EMAIL="akhilprakash634@gmail.com"; fi

echo "=========================================================="
echo "   Setting up SSL & Nginx for: $DOMAIN"
echo "   Contact Email:              $EMAIL"
echo "=========================================================="

# 1. Update package list and install Nginx + Certbot
echo ">>> [1/5] Installing Nginx and Certbot..."
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo systemctl daemon-reload

# 2. Allow HTTP/HTTPS traffic through UFW firewall
echo ">>> [2/5] Configuring firewall rules (Ports 80 & 443)..."
sudo ufw allow 80/tcp || true
sudo ufw allow 443/tcp || true
sudo ufw allow 'Nginx Full' || true

# 3. Create Nginx reverse proxy configuration
echo ">>> [3/5] Creating Nginx configuration for $DOMAIN..."
NGINX_CONF="/etc/nginx/sites-available/prayatna-ai"

# Clean up any conflicting old configs
sudo rm -f /etc/nginx/sites-enabled/default
for conf in /etc/nginx/sites-enabled/*; do
    if [ -f "$conf" ] && [ "$conf" != "/etc/nginx/sites-enabled/prayatna-ai" ]; then
        if grep -q "$DOMAIN" "$conf" 2>/dev/null; then
            echo "Removing conflicting config: $conf"
            sudo rm -f "$conf"
        fi
    fi
done

sudo bash -c "cat > $NGINX_CONF" <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Standard proxy headers
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # Disable proxy buffering for real-time AI chat streaming (SSE)
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header X-Accel-Buffering no;
        proxy_read_timeout 600s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 600s;
    }
}
EOF

# Enable configuration
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/prayatna-ai

# Test Nginx syntax and reload
echo "Testing Nginx configuration syntax..."
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

# 4. Request SSL Certificate via Certbot
echo ">>> [4/5] Clearing stale Certbot locks and requesting SSL Certificate..."
# Kill any background or hanging certbot instances
sudo pkill -9 -f certbot || true
sudo rm -f /var/lib/letsencrypt/.certbot.lock /var/log/letsencrypt/.certbot.lock /etc/letsencrypt/.certbot.lock

sudo certbot --nginx \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    -m "$EMAIL" \
    --redirect

# 5. Verify certificate auto-renewal and test health
echo ">>> [5/5] Testing certificate auto-renewal..."
sudo certbot renew --dry-run

echo "=========================================================="
echo "   SSL & Reverse Proxy Setup Complete!"
echo "   HTTPS URL: https://$DOMAIN"
echo "   Health:    https://$DOMAIN/health"
echo "=========================================================="

