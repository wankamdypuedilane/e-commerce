#!/bin/bash
set -e

# =============================================================================
# Django E-Commerce Bootstrap Script (cloud-init)
# Runs automatically on EC2 startup to configure the entire app
# =============================================================================

LOG="/var/log/ecom-bootstrap.log"
exec > >(tee -a "$LOG")
exec 2>&1

echo "[$(date)] === Starting E-Commerce Bootstrap ==="

# Update system
echo "[$(date)] Updating system packages..."
apt-get update
apt-get upgrade -y

# Install dependencies
echo "[$(date)] Installing dependencies..."
apt-get install -y \
  python3.12 \
  python3.12-venv \
  python3.12-dev \
  git \
  postgresql-client \
  nginx \
  curl \
  wget \
  build-essential \
  libssl-dev \
  libffi-dev

# Clone repository
echo "[$(date)] Cloning repository..."
cd /home/ubuntu
git clone ${git_repo_url} e-commerce
cd e-commerce

# Create .env file with secrets
echo "[$(date)] Creating .env file..."
cat > /home/ubuntu/e-commerce/.env << 'ENV_EOF'
DJANGO_SECRET_KEY=${django_secret_key}
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=${allowed_hosts}
STRIPE_PUBLIC_KEY=${stripe_public_key}
STRIPE_SECRET_KEY=${stripe_secret_key}
BREVO_SMTP_LOGIN=${brevo_smtp_login}
BREVO_SMTP_KEY=${brevo_smtp_key}
EMAIL_FROM=${email_from}
ENV_EOF

# Configure database variables based on database_url.
# Supports PostgreSQL URL, otherwise falls back to SQLite.
if [[ "${database_url}" =~ ^postgres(ql)?:// ]]; then
  DB_NAME=$(python3.12 -c "import urllib.parse as p;u=p.urlparse('${database_url}');print(u.path.lstrip('/'))")
  DB_USER=$(python3.12 -c "import urllib.parse as p;u=p.urlparse('${database_url}');print(p.unquote(u.username or ''))")
  DB_PASSWORD=$(python3.12 -c "import urllib.parse as p;u=p.urlparse('${database_url}');print(p.unquote(u.password or ''))")
  DB_HOST=$(python3.12 -c "import urllib.parse as p;u=p.urlparse('${database_url}');print(u.hostname or '')")
  DB_PORT=$(python3.12 -c "import urllib.parse as p;u=p.urlparse('${database_url}');print(u.port or 5432)")

  cat >> /home/ubuntu/e-commerce/.env << ENV_EOF
DB_ENGINE=postgres
DB_NAME=$${DB_NAME}
DB_USER=$${DB_USER}
DB_PASSWORD=$${DB_PASSWORD}
DB_HOST=$${DB_HOST}
DB_PORT=$${DB_PORT}
ENV_EOF
else
  cat >> /home/ubuntu/e-commerce/.env << 'ENV_EOF'
DB_ENGINE=sqlite
DB_NAME=/home/ubuntu/e-commerce/db.sqlite3
ENV_EOF
fi

chown ubuntu:ubuntu /home/ubuntu/e-commerce/.env
chmod 600 /home/ubuntu/e-commerce/.env

# Create virtual environment
echo "[$(date)] Creating Python virtual environment..."
python3.12 -m venv Ecom
source Ecom/bin/activate

# Install Python dependencies
echo "[$(date)] Installing Python packages..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Run migrations
echo "[$(date)] Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "[$(date)] Collecting static files..."
python manage.py collectstatic --noinput

# Create Gunicorn systemd service
echo "[$(date)] Creating Gunicorn systemd service..."
cat > /etc/systemd/system/ecom.service << 'GUNICORN_EOF'
[Unit]
Description=E-Commerce Django Gunicorn Service
After=network.target postgresql.service

[Service]
Type=notify
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/e-commerce
Environment="PATH=/home/ubuntu/e-commerce/Ecom/bin"
Environment="DJANGO_SETTINGS_MODULE=ecommerce.settings"

ExecStart=/home/ubuntu/e-commerce/Ecom/bin/gunicorn \
  --workers 3 \
  --worker-class sync \
  --bind 127.0.0.1:8000 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  ecommerce.wsgi:application

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
GUNICORN_EOF

# Configure Nginx as reverse proxy
echo "[$(date)] Configuring Nginx..."
cat > /etc/nginx/sites-available/ecommerce << 'NGINX_EOF'
upstream gunicorn_app {
  server 127.0.0.1:8000 fail_timeout=0;
}

server {
    listen 80;
    server_name _;
    client_max_body_size 10M;

    location / {
        proxy_pass http://gunicorn_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /static/ {
        alias /home/ubuntu/e-commerce/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /home/ubuntu/e-commerce/media/;
        expires 7d;
    }
}
NGINX_EOF

# Enable Nginx site configuration
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/ecommerce /etc/nginx/sites-enabled/ecommerce

# Test Nginx configuration
nginx -t

# Reload systemd and start services
echo "[$(date)] Starting services..."
systemctl daemon-reload
systemctl enable ecom
systemctl start ecom
systemctl restart nginx

# Wait for Gunicorn to be ready
sleep 3

# Check service status
echo "[$(date)] Checking service status..."
systemctl status ecom --no-pager || true
systemctl status nginx --no-pager || true

# Test application endpoint
echo "[$(date)] Testing application health..."
if curl -f http://localhost/admin/ > /dev/null 2>&1; then
  echo "[✓] SUCCESS: Application is responding!"
else
  echo "[!] WARNING: Application may be starting up, check logs"
fi

echo "[$(date)] === Bootstrap Complete ==="

# Log diagnostic info
echo "[$(date)] === System Info ==="
uname -a
python3.12 --version
django-admin --version
gunicorn --version
nginx -v
