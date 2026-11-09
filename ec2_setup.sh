#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "   Prayatna AI Backend - AWS EC2 Automated Server Setup   "
echo "=========================================================="

# 1. Update OS packages
echo ">>> [1/5] Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl git ufw

# 2. Configure 4GB Swap File (Prevents OOM)
echo ">>> [2/5] Configuring 4GB Swap file to prevent memory issues..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 4G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "Swap file created successfully!"
else
    echo "Swap file already exists, skipping."
fi

# 3. Install Docker and Docker Compose
echo ">>> [3/5] Installing Docker and Docker Compose..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm -f get-docker.sh
    sudo usermod -aG docker $USER
    echo "Docker installed successfully!"
else
    echo "Docker already installed, skipping."
fi

# 4. Configure UFW Firewall (SSH, HTTP, HTTPS, Port 8000)
echo ">>> [4/5] Configuring firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo ufw --force enable

# 5. Final instructions
echo ">>> [5/5] Server preparation complete!"
echo "=========================================================="
echo "NEXT STEPS TO LAUNCH BACKEND:"
echo "1. Run: newgrp docker"
echo "2. Clone your repository:"
echo "   git clone https://github.com/akhilprakash634/Prayatna-Ai-backend.git /home/ubuntu/Prayatna-Ai-backend"
echo "3. Enter directory and set up .env:"
echo "   cd /home/ubuntu/Prayatna-Ai-backend"
echo "   cp .env.example .env"
echo "   nano .env    # Add your GEMINI_API_KEY and passwords"
echo "4. Start container:"
echo "   docker compose up -d"
echo "5. Check status:"
echo "   curl http://localhost:8000/health"
echo "6. Setup Nginx & SSL (Let's Encrypt):"
echo "   ./setup_ssl.sh prayatna.demoapi.thescalecraft.in"
echo "=========================================================="
