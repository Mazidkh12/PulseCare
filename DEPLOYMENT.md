# PulseCare Clinic Management System — Production Deployment Guide

## Overview

PulseCare Clinic Management System is an enterprise outpatient case-taking and healthcare clinic management platform built with Python, Django 6.1 (MVT architecture), and MySQL.

This document provides step-by-step instructions for staging and production deployment, database configuration, security hardening, and operational maintenance.

---

## 1. System Requirements & Prerequisites

- **Operating System**: Linux (Ubuntu 22.04 LTS / 24.04 LTS or Debian 12 recommended)
- **Python**: Version 3.12+ (or 3.14 compatible)
- **Database**: MySQL Server 8.0+ or MariaDB 10.6+
- **Web Server / Reverse Proxy**: Nginx 1.20+
- **WSGI Application Server**: Gunicorn 21+ or uWSGI
- **SSL / TLS**: Valid domain name with Let's Encrypt SSL certificates (Certbot)

---

## 2. Directory Structure & Virtual Environment Setup

### 2.1 Clone Repository and Create System User

```bash
# Create dedicated application user
sudo adduser --system --group --home /var/www/pulsecare pulsecare

# Switch to application directory
cd /var/www/pulsecare
sudo git clone <repository-url> app
cd /var/www/pulsecare/app
```

### 2.2 Install Dependencies

```bash
# Update system packages
sudo apt update && sudo apt install -y python3-venv python3-dev default-libmysqlclient-dev build-essential pkg-config

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and install requirements
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

---

## 3. MySQL Database Setup

### 3.1 Create Database and User

Log in to MySQL as root:

```bash
sudo mysql -u root -p
```

Execute the following SQL commands:

```sql
-- Create database with full Unicode UTF-8 support
CREATE DATABASE patient_case_management_db 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

-- Create dedicated clinic application database user
CREATE USER 'pulsecare_user'@'localhost' IDENTIFIED BY 'StrongRandomDatabasePassword2026!';

-- Grant required operational privileges
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER, LOCK TABLES, REFERENCES 
    ON patient_case_management_db.* TO 'pulsecare_user'@'localhost';

FLUSH PRIVILEGES;
EXIT;
```

---

## 4. Environment Variable Configuration

Create the production environment file at `/var/www/pulsecare/app/.env`:

```bash
cp .env.example .env
sudo chown pulsecare:pulsecare .env
sudo chmod 600 .env
```

Edit `.env` with production parameters:

```ini
# ==============================================================================
# PulseCare Clinic - Production Environment Settings
# ==============================================================================

# Core Django Settings
# Generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
DJANGO_SECRET_KEY=replace-with-a-cryptographically-random-50-character-secret-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=clinic.yourdomain.com,www.clinic.yourdomain.com

# MySQL Database Connection
DB_NAME=patient_case_management_db
DB_USER=pulsecare_user
DB_PASSWORD=StrongRandomDatabasePassword2026!
DB_HOST=127.0.0.1
DB_PORT=3306

# Production Security & Session Hardening
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True
DJANGO_SESSION_COOKIE_AGE=1800
```

> **Security Rule**: Never check `.env` into Git or version control. `.gitignore` strictly excludes all `.env` files.

---

## 5. Database Migrations & Static Files Collection

```bash
source .venv/bin/activate

# Execute database migrations
python manage.py migrate

# Collect static assets into staticfiles directory
python manage.py collectstatic --noinput

# Create initial clinic administrator
python manage.py createsuperuser
```

---

## 6. WSGI Server Configuration (Gunicorn)

### 6.1 Create Systemd Service Unit

Create `/etc/systemd/system/pulsecare.service`:

```ini
[Unit]
Description=PulseCare Clinic Management System Gunicorn Daemon
After=network.target mysql.service

[Service]
User=pulsecare
Group=pulsecare
WorkingDirectory=/var/www/pulsecare/app
EnvironmentFile=/var/www/pulsecare/app/.env
ExecStart=/var/www/pulsecare/app/.venv/bin/gunicorn \
    --workers 4 \
    --threads 2 \
    --bind 127.0.0.1:8000 \
    --timeout 60 \
    --access-logfile /var/log/pulsecare/access.log \
    --error-logfile /var/log/pulsecare/error.log \
    config.wsgi:application

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6.2 Enable and Start Service

```bash
sudo mkdir -p /var/log/pulsecare
sudo chown -R pulsecare:pulsecare /var/log/pulsecare

sudo systemctl daemon-reload
sudo systemctl enable pulsecare
sudo systemctl start pulsecare
sudo systemctl status pulsecare
```

---

## 7. Nginx Reverse Proxy & SSL Configuration

### 7.1 Nginx Site Configuration

Create `/etc/nginx/sites-available/pulsecare`:

```nginx
server {
    server_name clinic.yourdomain.com;

    client_max_body_size 10M;

    # Static assets served directly by Nginx
    location /static/ {
        alias /var/www/pulsecare/app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }

    # Media uploads (protected)
    location /media/ {
        alias /var/www/pulsecare/app/media/;
        expires 7d;
    }

    # Proxy all dynamic requests to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Security Headers
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy same-origin always;
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/pulsecare /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7.2 HTTPS & Certbot SSL

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d clinic.yourdomain.com
```

Certbot automatically configures auto-renewal crons and sets up TLS 1.3 certificates.

---

## 8. Database Backup Strategy

To ensure zero loss of clinical records, configure automated daily backups using `mysqldump`.

Create `/usr/local/bin/backup_pulsecare_db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/pulsecare"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/pulsecare_backup_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Dump database with transactions enabled
mysqldump --single-transaction --quick --lock-tables=false \
    -u pulsecare_user -pStrongRandomDatabasePassword2026! \
    patient_case_management_db | gzip > "$BACKUP_FILE"

# Keep last 30 daily backups
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +30 -exec rm {} \;
```

Set executable and add to crontab:

```bash
sudo chmod +x /usr/local/bin/backup_pulsecare_db.sh
# Run every night at 02:00 AM
echo "0 2 * * * root /usr/local/bin/backup_pulsecare_db.sh" | sudo tee -a /etc/crontab
```

---

## 9. Deployment Verification Checklist

Before opening the portal to receptionists and physicians:

- [ ] `python manage.py check` passes with 0 issues.
- [ ] `python manage.py check --deploy` shows no unaddressed security warnings.
- [ ] `DJANGO_DEBUG=False` in `.env`.
- [ ] `DJANGO_SECRET_KEY` is a unique 50+ character random string.
- [ ] `DJANGO_ALLOWED_HOSTS` matches production FQDN.
- [ ] HTTPS redirect is working (`http://` redirects to `https://`).
- [ ] Session cookies have `Secure` and `HttpOnly` flags active.
- [ ] CSRF cookies have `Secure` flag active.
- [ ] Custom 403, 404, and 500 error pages render without technical stack traces.
- [ ] MySQL user privileges are strictly restricted to `patient_case_management_db`.
- [ ] Automated database backup cron is active and tested.
- [ ] All 238+ automated unit and end-to-end tests pass cleanly (`python manage.py test`).
