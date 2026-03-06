# M365 Security Audit Platform — Setup Guide

This guide walks you through everything needed to go from a fresh Ubuntu VM to a live deployment.

---

## Prerequisites

- Ubuntu 22.04 VM with a public IP address
- Docker and Docker Compose installed (see below if not)
- A domain name you control (e.g. `audit.yourcompany.com`)
- Access to your own Microsoft 365 tenant as Global Administrator
- An OpenAI API key

---

## Part 1 — Install Docker (if not already installed)

```bash
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
docker --version   # confirm it works
```

---

## Part 2 — Generate the Certificate

The platform authenticates to client M365 tenants using a certificate (not a client secret). This is required for SharePoint Online access on Linux.

Run this on your Ubuntu VM from the project root:

```bash
cd /root/m365-audit-platform
./scripts/generate_cert.sh "YourStrongCertPassword123!"
```

This creates two files in `certs/`:
- `monkey365.pfx` — private key + certificate. **Never share this. It stays on the server.**
- `monkey365.cer` — public key only. You will upload this to Azure in Part 3.

Write down the password you used — you need it as `CERT_PASSWORD` in your `.env`.

---

## Part 3 — Create the Azure App Registration

You do this once in **your own** M365 tenant. Clients then grant this app access to their tenants via admin consent.

### 3.1 Register the app

1. Go to [portal.azure.com](https://portal.azure.com) and sign in as **Global Administrator of your own tenant**
2. Navigate to **Microsoft Entra ID** → **App registrations** → **New registration**
3. Fill in:
   - **Name:** `M365 Security Audit` (visible to client admins during consent)
   - **Supported account types:** `Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant)`
   - **Redirect URI:** Platform = **Web**, URI = `https://audit.yourcompany.com/auth/callback`
4. Click **Register**

On the overview page, copy:
- **Application (client) ID** → this is your `AZURE_CLIENT_ID`
- **Directory (tenant) ID** → this is your `AZURE_TENANT_ID`

### 3.2 Upload the certificate

1. In your App Registration → **Certificates & secrets** → **Certificates** tab
2. Click **Upload certificate**
3. Upload `certs/monkey365.cer` (the `.cer` file — not the `.pfx`)
4. Add a description, e.g. `monkey365-cert` → click **Add**
5. You'll see a thumbprint listed — that confirms it worked

### 3.3 Add API permissions

In your App Registration → **API permissions** → **Add a permission**

#### Microsoft Graph — Application permissions

Click **Microsoft Graph** → **Application permissions** → search and add each:

| Permission | What it audits |
|---|---|
| `User.Read.All` | All users, MFA status |
| `Application.Read.All` | App registrations, service principals |
| `Policy.Read.All` | Conditional Access policies |
| `Organization.Read.All` | Org-level settings |
| `RoleManagement.Read.Directory` | Admin role assignments |
| `GroupMember.Read.All` | Group membership |
| `Directory.Read.All` | All directory objects |
| `Group.Read.All` | M365 and security groups |
| `SecurityEvents.Read.All` | Security alerts |
| `IdentityRiskEvent.Read.All` | Risk detections |
| `UserAuthenticationMethod.Read.All` | MFA method details per user |
| `AppCatalog.Read.All` | Teams app catalog |
| `Channel.ReadBasic.All` | Teams channels |
| `ChannelMember.Read.All` | Channel membership |
| `ChannelSettings.Read.All` | Channel configuration |
| `TeamSettings.Read.All` | Team-level settings |
| `PrivilegedEligibilitySchedule.Read.AzureADGroup` | PIM group eligibility |
| `PrivilegedAccess.Read.AzureADGroup` | PIM active assignments |
| `RoleManagementPolicy.Read.AzureADGroup` | PIM policies |

#### Exchange Online — Application permissions

Click **Add a permission** → **APIs my organization uses** → search `Office 365 Exchange Online` → **Application permissions** → add:
- `Exchange.ManageAsApp`

#### SharePoint — Application permissions

Click **Add a permission** → **SharePoint** → **Application permissions** → add:
- `Sites.FullControl.All`

#### Grant admin consent

After adding all permissions, click **Grant admin consent for [your tenant name]** → **Yes**.

All rows should now show a green checkmark under Status.

> **Note on Exchange:** For `Exchange.ManageAsApp` to work in client tenants, the platform's service principal must be assigned the **Exchange Administrator** role in each client tenant. Monkey365 handles this via the permission itself — the client's admin consent flow grants this automatically.

---

## Part 4 — Configure Your Domain and HTTPS

Microsoft OAuth requires HTTPS for the redirect URI. Choose one of the two options below.

---

### Option A: Cloudflare (Recommended)

Cloudflare proxies traffic to your server and handles TLS for your clients. You use a **Cloudflare Origin Certificate** to encrypt the Cloudflare→server leg as well, so all traffic is encrypted end-to-end.

#### Step 1: Get your server's public IP

```bash
curl -s ifconfig.me
```

#### Step 2: Add your domain to Cloudflare (if not already there)

If your domain isn't managed by Cloudflare yet:
1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → **Add a site**
2. Enter your root domain (e.g. `yourcompany.com`) and follow the steps
3. Cloudflare will show you two nameservers (e.g. `dana.ns.cloudflare.com`)
4. Log into your domain registrar and update the nameservers to those two values
5. Wait for propagation — usually 5–30 minutes. You'll receive an email from Cloudflare when active.

If your domain is already on Cloudflare, skip to Step 3.

#### Step 3: Create a DNS A record for your subdomain

1. In Cloudflare → select your domain → **DNS** → **Records** → **Add record**
2. Fill in:
   - **Type:** `A`
   - **Name:** `audit` (this creates `audit.yourcompany.com`)
   - **IPv4 address:** your server's public IP from Step 1
   - **Proxy status:** click the cloud icon so it turns **orange (Proxied)**
3. Click **Save**

The orange cloud is critical — it means Cloudflare proxies all traffic. Grey cloud means direct connection only.

#### Step 4: Set the SSL/TLS encryption mode to Full

1. In Cloudflare → your domain → **SSL/TLS** → **Overview**
2. Set the mode to **Full**

> **Full vs Full Strict:** Both work with a Cloudflare Origin Certificate. "Full" is sufficient and more forgiving. "Full Strict" also works and adds an extra validation layer.

#### Step 5: Generate a Cloudflare Origin Certificate

This is a free certificate Cloudflare issues for the Cloudflare→origin connection. It is trusted by Cloudflare but not by browsers directly (which is fine — browsers only talk to Cloudflare, not your origin).

1. In Cloudflare → your domain → **SSL/TLS** → **Origin Server**
2. Click **Create Certificate**
3. Leave defaults:
   - Key type: **RSA (2048)**
   - Hostnames: your domain and wildcard (e.g. `yourcompany.com`, `*.yourcompany.com`)
   - Validity: **15 years**
4. Click **Create**
5. Copy the **Origin Certificate** and **Private Key** — you will only see the private key once

#### Step 6: Save the certificate files on your server

```bash
mkdir -p /root/m365-audit-platform/nginx/certs

# Paste the Origin Certificate (everything from -----BEGIN CERTIFICATE----- to -----END CERTIFICATE-----)
nano /root/m365-audit-platform/nginx/certs/origin.crt

# Paste the Private Key (everything from -----BEGIN PRIVATE KEY----- to -----END PRIVATE KEY-----)
nano /root/m365-audit-platform/nginx/certs/origin.key

# Lock down permissions
chmod 600 /root/m365-audit-platform/nginx/certs/origin.key
chmod 644 /root/m365-audit-platform/nginx/certs/origin.crt
```

#### Step 7: Update nginx/nginx.conf for HTTPS

Replace the entire contents of `nginx/nginx.conf` with the following (replace `audit.yourcompany.com`):

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name audit.yourcompany.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name audit.yourcompany.com;

    ssl_certificate /etc/nginx/certs/origin.crt;
    ssl_certificate_key /etc/nginx/certs/origin.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    location /health {
        proxy_pass http://api:8000/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://api:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /auth/ {
        proxy_pass http://api:8000/auth/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location / {
        proxy_pass http://frontend:80/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Step 8: Mount the certs in Docker Compose

The nginx service in `docker-compose.yml` needs to see the cert files. Add the volume and the 443 port mapping:

```yaml
  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro    # add this line
    ports:
      - "80:80"
      - "443:443"                             # add this line
    depends_on:
      - api
      - frontend
```

#### Step 9: Open firewall ports and restart nginx

```bash
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp
ufw enable

cd /root/m365-audit-platform
docker compose restart nginx
```

#### Step 10: Verify

```bash
curl -I https://audit.yourcompany.com/health
# HTTP/2 200
```

> **Note:** Cloudflare Origin Certificates never expire for 15 years and require no renewal cron job. The only thing to update is if you change domains.

---

### Option B: Let's Encrypt (TLS terminates at your server)

Use this if you prefer TLS to terminate on your server rather than going through Cloudflare.

#### Step 1: Point DNS to your server

In your DNS provider — if using Cloudflare, add the A record but keep the cloud **grey (DNS only)**:

- **Type:** `A`
- **Name:** `audit`
- **Value:** your server's public IP
- **Proxy:** OFF (grey cloud)

Wait for DNS to propagate:
```bash
nslookup audit.yourcompany.com
# Should return your server's IP directly
```

#### Step 2: Open firewall ports

```bash
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp
ufw enable
```

#### Step 3: Get a certificate from Let's Encrypt

Stop the nginx container first so certbot can bind port 80:

```bash
cd /root/m365-audit-platform
docker compose stop nginx

apt install -y certbot
certbot certonly --standalone -d audit.yourcompany.com
```

Certificates are saved to:
- `/etc/letsencrypt/live/audit.yourcompany.com/fullchain.pem`
- `/etc/letsencrypt/live/audit.yourcompany.com/privkey.pem`

#### Step 4: Update nginx/nginx.conf

Replace the full contents of `nginx/nginx.conf` with the following (replace `audit.yourcompany.com` with your actual domain):

```nginx
server {
    listen 80;
    server_name audit.yourcompany.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name audit.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/audit.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/audit.yourcompany.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    location /api/ {
        proxy_pass http://api:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /auth/ {
        proxy_pass http://api:8000/auth/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location / {
        proxy_pass http://frontend:80/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Step 5: Mount the certificates in Docker Compose

Open `docker-compose.yml` and add to the nginx service volumes and ports:

```yaml
  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro    # add this
    ports:
      - "80:80"
      - "443:443"                                # add this
```

#### Step 6: Set up automatic certificate renewal

Let's Encrypt certificates expire after 90 days. Add a cron job to renew automatically:

```bash
crontab -e
```

Add this line:
```
0 3 * * * certbot renew --quiet && docker compose -f /root/m365-audit-platform/docker-compose.yml restart nginx
```

This runs at 3am every day, renews if within 30 days of expiry, and reloads nginx.

---

## Part 5 — Configure Email via Your M365 Mailbox

Reports are sent from a dedicated mailbox in your own Microsoft 365 tenant using SMTP AUTH.

### 5.1 Create a dedicated mailbox

Create a mailbox specifically for sending audit reports so you can easily monitor it and control access.

In [Microsoft 365 Admin Center](https://admin.microsoft.com):

**Option A — Shared mailbox (recommended, no licence cost):**
1. **Teams & groups** → **Shared mailboxes** → **Add a shared mailbox**
2. Name: `Security Assessments`, Email: `assessments@yourcompany.com`
3. Click **Save changes**

**Option B — Regular user mailbox:**
1. **Users** → **Active users** → **Add a user**
2. Create a dedicated account: `assessments@yourcompany.com`
3. Set a strong password

### 5.2 Enable SMTP AUTH on your tenant

SMTP AUTH may be disabled by default in newer M365 tenants. Enable it:

1. Go to [admin.exchange.microsoft.com](https://admin.exchange.microsoft.com)
2. **Settings** → **Mail flow** → **SMTP AUTH**
3. Enable it and save

Or via PowerShell (from any machine with the Exchange Online module):

```powershell
Install-Module -Name ExchangeOnlineManagement -Force
Connect-ExchangeOnline -UserPrincipalName admin@yourcompany.com
Set-TransportConfig -SmtpClientAuthenticationDisabled $false
```

### 5.3 Enable SMTP AUTH on the specific mailbox

```powershell
Connect-ExchangeOnline -UserPrincipalName admin@yourcompany.com
Set-CASMailbox -Identity "assessments@yourcompany.com" -SmtpClientAuthenticationDisabled $false

# Verify:
Get-CASMailbox -Identity "assessments@yourcompany.com" | Select SmtpClientAuthenticationDisabled
# Must return: False
```

### 5.4 Handle MFA on the sending mailbox

If the sending mailbox has MFA enforced (likely if it's a regular user account), SMTP AUTH will fail with a password alone. You have two options:

**Option A — App Password (simplest)**

1. Sign in at [myaccount.microsoft.com](https://myaccount.microsoft.com) **as the sending mailbox account**
2. Go to **Security info** → **Add sign-in method** → **App password**
3. Name it (e.g. `audit-platform`) and copy the generated password
4. Use this app password as `SMTP_PASSWORD` in `.env` — not the account's regular password

**Option B — Exclude from MFA via Conditional Access**

If the mailbox is a shared mailbox or a dedicated service account, you can exclude it from MFA:

1. In Entra ID → **Security** → **Conditional Access** → **Policies**
2. Find your MFA policy → **Users** → **Exclude** → add the sending mailbox account
3. This is safe for non-human service accounts with strong passwords

### 5.5 SMTP settings for .env

```env
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=assessments@yourcompany.com
SMTP_PASSWORD=<mailbox password or app password from step 5.4>
EMAIL_FROM=assessments@yourcompany.com
EMAIL_FROM_NAME=Your Company Security Team
```

---

## Part 6 — Fill in .env

```bash
cd /root/m365-audit-platform
cp .env.example .env
nano .env
```

Complete reference — fill in every value:

```env
# Azure (from Part 3)
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_TENANT_ID=yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

# Certificate (from Part 2)
CERT_PATH=/app/certs/monkey365.pfx
CERT_PASSWORD=YourStrongCertPassword123!

# URLs — your public domain (from Part 4)
APP_BASE_URL=https://audit.yourcompany.com
REDIRECT_URI=https://audit.yourcompany.com/auth/callback

# OpenAI
OPENAI_API_KEY=sk-...

# Email via M365 (from Part 5)
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=assessments@yourcompany.com
SMTP_PASSWORD=your-mailbox-or-app-password
EMAIL_FROM=assessments@yourcompany.com
EMAIL_FROM_NAME=Your Company Security Team

# Security — generate with: openssl rand -hex 32
SECRET_KEY=paste-your-generated-secret-here

# These are correct for Docker Compose — do not change
REDIS_URL=redis://redis:6379/0
DATABASE_URL=sqlite:////app/data/audit.db
```

Generate a secret key:
```bash
openssl rand -hex 32
```

---

## Part 7 — Deploy

```bash
cd /root/m365-audit-platform
docker compose up -d --build
```

Check all services are up:
```bash
docker compose ps
```

Expected — all services running or healthy:
```
NAME        STATUS
redis       Up (healthy)
api         Up
worker      Up
frontend    Up
nginx       Up
```

---

## Part 8 — Verify the Deployment

**Health check:**
```bash
curl https://audit.yourcompany.com/health
# {"status":"ok"}
```

**Test a job start:**
```bash
curl -X POST https://audit.yourcompany.com/api/start \
  -H "Content-Type: application/json" \
  -d '{"email":"you@yourcompany.com","company":"Test Corp"}'
# {"job_id":"...","consent_url":"https://login.microsoftonline.com/..."}
```

Open the `consent_url` in a browser. Have a test tenant's Global Administrator log in and accept. They'll land on `/thank-you`.

Watch the worker process the job:
```bash
docker compose logs -f worker
```

You'll see: Monkey365 starting → per-service OpenAI analysis → PDF generation → email sent.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Microsoft: "redirect URI mismatch" | `REDIRECT_URI` in `.env` doesn't exactly match App Registration | Must match exactly including `https://` and no trailing slash |
| `/error?reason=invalid_tenant` | Client declined consent or Microsoft didn't send `tenant` param | Check with client; confirm App Registration redirect URI is correct |
| Worker: cert errors from PowerShell | Wrong cert password or thumbprint mismatch | Re-run `generate_cert.sh`, re-upload `.cer` to Azure, update `CERT_PASSWORD` |
| SMTP: `5.7.57 AUTH not permitted` | SMTP AUTH disabled on tenant or mailbox | Follow Part 5.2 and 5.3 |
| SMTP: `535 Authentication unsuccessful` | Wrong password or MFA blocking | Generate an App Password (Part 5.4 Option A) |
| Cloudflare: 522 error | VM firewall blocking port 80 | `ufw allow 80/tcp` |
| Let's Encrypt renewal fails | Port 80 blocked | Ensure port 80 is open during renewal window |
| No JSON output from Monkey365 | API permissions not consented in your own tenant | App Registration → API permissions → Grant admin consent |
| Email going to spam | Sending domain not SPF/DKIM authenticated | Set up SPF and DKIM records for your M365 domain in DNS |

---

## Ongoing Maintenance

**View logs:**
```bash
docker compose logs -f worker    # audit job progress
docker compose logs -f api       # API requests
docker compose logs -f nginx     # incoming traffic
```

**Restart a service:**
```bash
docker compose restart worker
```

**Update the platform:**
```bash
git pull
docker compose up -d --build
```

**Back up the job database:**
```bash
docker compose exec api sqlite3 /app/data/audit.db ".backup /app/data/audit.db.bak"
```
