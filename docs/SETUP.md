# M365 Security Audit Platform — Setup Guide

This guide walks you through everything needed to go from a fresh Ubuntu server to a live deployment that can scan any customer's Microsoft 365 tenant.

---

## Prerequisites

- Ubuntu 22.04 (or 24.04) VM with a public IP address
- Docker and Docker Compose installed (see Part 1)
- A domain name you control (e.g. `audit.yourcompany.com`)
- Global Administrator access to your **own** Microsoft 365 tenant
- An OpenAI API key

---

## Part 1 — Install Docker

```bash
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
docker --version   # confirm
```

---

## Part 2 — Clone the Repository

```bash
git clone https://github.com/YOUR_ORG/m365-audit-platform.git /root/m365-audit-platform
cd /root/m365-audit-platform
```

---

## Part 3 — Generate the Certificate

The platform authenticates to client M365 tenants using a **certificate** (not a client secret). This is required for SharePoint Online access on Linux.

```bash
cd /root/m365-audit-platform
./scripts/generate_cert.sh "YourStrongCertPassword123!"
```

This creates two files in `certs/`:
- `monkey365.pfx` — private key + certificate. **Never share this. It stays on the server.**
- `monkey365.cer` — public key only. Upload this to Azure in Part 4.

Write down the password — you need it as `CERT_PASSWORD` in your `.env`.

---

## Part 4 — Create the Azure App Registration

You do this **once** in your **own** M365 tenant. Customers then grant this app access to their tenants via admin consent.

### 4.1 Register the app

1. Go to [portal.azure.com](https://portal.azure.com) → sign in as **Global Administrator of your own tenant**
2. **Microsoft Entra ID** → **App registrations** → **New registration**
3. Fill in:
   - **Name:** `M365 Security Audit` (clients see this name during consent)
   - **Supported account types:** `Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant)`
   - **Redirect URI:** Platform = **Web**, URI = `https://your-domain.com/auth/callback`
4. Click **Register**

On the overview page, copy:
- **Application (client) ID** → `AZURE_CLIENT_ID`
- **Directory (tenant) ID** → `AZURE_TENANT_ID`

### 4.2 Upload the certificate

1. App Registration → **Certificates & secrets** → **Certificates** tab
2. Click **Upload certificate** → upload `certs/monkey365.cer` (the `.cer` file, not `.pfx`)
3. Add a description → click **Add**
4. A thumbprint is shown — that confirms it worked

### 4.3 Add API permissions

Go to **API permissions** → **Add a permission**

#### Microsoft Graph — Application permissions

Click **Microsoft Graph** → **Application permissions** → search and add each:

| Permission | Purpose |
|---|---|
| `Application.ReadWrite.All` | **Delete our service principal** from client tenant after each audit (full cleanup). Without this, only admin roles are revoked; the SP itself remains. |
| `RoleManagement.ReadWrite.Directory` | **Assign Exchange / SharePoint / Teams admin roles** to our SP in client tenants so Monkey365 can collect all service data |
| `User.Read.All` | All users, MFA status |
| `Application.Read.All` | App registrations, service principals |
| `Policy.Read.All` | Conditional Access policies |
| `Organization.Read.All` | Org-level settings |
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
| `Mail.Send` | Send audit report emails from your mailbox |

> **Why `Application.ReadWrite.All`?** After each audit the platform deletes its own service principal from the client tenant. This ensures zero residual access between scans. Without this permission the platform falls back to revoking only the elevated admin roles, which leaves the SP object (with basic read permissions) in the tenant.

> **Why `RoleManagement.ReadWrite.Directory`?** Monkey365 needs Exchange Administrator, SharePoint Administrator, and Teams Administrator roles assigned to our SP to collect full service data. The platform assigns these roles automatically at the start of each scan and they are removed with the SP at the end.

#### Exchange Online — Application permissions

Click **Add a permission** → **APIs my organization uses** → search `Office 365 Exchange Online` → **Application permissions** → add:
- `Exchange.ManageAsApp`

#### SharePoint — Application permissions

Click **Add a permission** → **SharePoint** → **Application permissions** → add:
- `Sites.FullControl.All`

#### Grant admin consent

After adding all permissions, click **Grant admin consent for [your tenant name]** → **Yes**.

All rows should show a green checkmark under **Status**.

---

## Part 5 — Configure Your Domain and HTTPS

Microsoft OAuth requires HTTPS for the redirect URI.

---

### Option A: Cloudflare (Recommended)

Cloudflare proxies traffic to your server and handles TLS. Use a **Cloudflare Origin Certificate** to encrypt the Cloudflare→server leg.

#### Step 1: Get your server's public IP

```bash
curl -s ifconfig.me
```

#### Step 2: Add your domain to Cloudflare

If your domain isn't on Cloudflare yet: [dash.cloudflare.com](https://dash.cloudflare.com) → **Add a site** → follow the nameserver migration steps.

#### Step 3: Add a DNS A record

Cloudflare → your domain → **DNS** → **Add record**:
- **Type:** `A`
- **Name:** `audit`
- **IPv4:** your server's public IP
- **Proxy status:** orange cloud (Proxied)

#### Step 4: Set SSL/TLS mode to Full

Cloudflare → your domain → **SSL/TLS** → **Overview** → set to **Full**

#### Step 5: Generate a Cloudflare Origin Certificate

Cloudflare → your domain → **SSL/TLS** → **Origin Server** → **Create Certificate**

- Key type: RSA (2048)
- Validity: 15 years
- Click **Create** — copy the **Origin Certificate** and **Private Key** immediately (key shown once only)

#### Step 6: Save the certificate files on your server

```bash
mkdir -p /root/m365-audit-platform/nginx/certs

nano /root/m365-audit-platform/nginx/certs/origin.crt   # paste Origin Certificate
nano /root/m365-audit-platform/nginx/certs/origin.key   # paste Private Key

chmod 600 /root/m365-audit-platform/nginx/certs/origin.key
chmod 644 /root/m365-audit-platform/nginx/certs/origin.crt
```

#### Step 7: Verify nginx/nginx.conf

The `nginx/nginx.conf` in the repo already has HTTPS configured. Replace `your-domain.com` with your actual domain if needed.

#### Step 8: Open firewall ports

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

> Cloudflare Origin Certificates are valid for 15 years — no renewal cron job needed.

---

### Option B: Let's Encrypt

#### Step 1: Point DNS to your server (grey cloud / DNS only in Cloudflare)

#### Step 2: Open firewall ports

```bash
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
```

#### Step 3: Get a Let's Encrypt certificate

```bash
cd /root/m365-audit-platform
docker compose stop nginx
apt install -y certbot
certbot certonly --standalone -d your-domain.com
```

#### Step 4: Update nginx/nginx.conf

In the `nginx/nginx.conf` server block, replace the certificate paths with:
```nginx
ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
```

#### Step 5: Mount certs in docker-compose.yml

Add to the nginx service volumes:
```yaml
- /etc/letsencrypt:/etc/letsencrypt:ro
```

#### Step 6: Auto-renewal cron

```bash
crontab -e
# Add:
0 3 * * * certbot renew --quiet && docker compose -f /root/m365-audit-platform/docker-compose.yml restart nginx
```

---

## Part 6 — Configure Email (Microsoft Graph API)

Reports are sent via Microsoft Graph API — no SMTP, modern OAuth2 only.

### 6.1 Create a dedicated mailbox

In [Microsoft 365 Admin Center](https://admin.microsoft.com):

- **Teams & groups** → **Shared mailboxes** → **Add a shared mailbox**
  - Name: `Security Assessments`, Email: `assessments@yourcompany.com`

Or create a regular user mailbox if preferred.

### 6.2 The Mail.Send permission is already added in Part 4

It was included in the permissions table above. Ensure admin consent was granted.

### 6.3 Set email variables in .env

```env
EMAIL_FROM=assessments@yourcompany.com
EMAIL_FROM_NAME=Your Company Security Team
ADMIN_EMAIL=admin@yourcompany.com
```

`ADMIN_EMAIL` receives a BCC copy of every client report and all failure alerts.

---

## Part 7 — Fill in .env

```bash
cd /root/m365-audit-platform
cp .env.example .env
nano .env
```

Complete reference:

```env
# Azure (from Part 4)
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_TENANT_ID=yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

# Certificate (from Part 3)
CERT_PATH=/app/certs/monkey365.pfx
CERT_PASSWORD=YourStrongCertPassword123!

# URLs (from Part 5)
APP_BASE_URL=https://your-domain.com
REDIRECT_URI=https://your-domain.com/auth/callback
ALLOWED_ORIGINS=https://your-domain.com

# OpenAI
OPENAI_API_KEY=sk-...

# Email (from Part 6)
EMAIL_FROM=assessments@yourcompany.com
EMAIL_FROM_NAME=Your Company Security Team
ADMIN_EMAIL=admin@yourcompany.com

# PostgreSQL — set POSTGRES_PASSWORD to a strong random value, keep the rest as-is
POSTGRES_PASSWORD=change-this-to-a-strong-password
DATABASE_URL=postgresql://m365audit:change-this-to-a-strong-password@postgres:5432/m365audit

# Redis — do not change
REDIS_URL=redis://redis:6379/0

# Security — generate with: openssl rand -hex 32
# App will refuse to start if this is not set.
SECRET_KEY=paste-64-char-hex-here
```

Generate the secret key:
```bash
openssl rand -hex 32
```

> **Important:** `POSTGRES_PASSWORD` must match in both the `POSTGRES_PASSWORD` line and the `DATABASE_URL` connection string. They are kept separate so Docker Compose can pass the password to the Postgres container directly.

---

## Part 8 — Deploy

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
NAME        SERVICE    STATUS
postgres    postgres   Up (healthy)
redis       redis      Up (healthy)
api         api        Up
worker      worker     Up
beat        beat       Up
frontend    frontend   Up
nginx       nginx      Up
```

---

## Part 9 — Verify the Deployment

**Health check:**
```bash
curl https://your-domain.com/health
# {"status":"ok"}
```

**Test a job start:**
```bash
curl -X POST https://your-domain.com/api/start \
  -H "Content-Type: application/json" \
  -d '{"email":"you@yourcompany.com","company":"Test Corp"}'
# {"job_id":"...","consent_url":"https://login.microsoftonline.com/..."}
```

Open the `consent_url` in a browser. Have a test tenant's Global Administrator log in and accept. They'll land on `/thank-you`.

Watch the worker process the job:
```bash
docker compose logs -f worker
```

You'll see: role assignment → Monkey365 scanning → parallel OpenAI analysis → PDF generation → email sent → service principal deleted from client tenant.

---

## How the Audit Lifecycle Works

Understanding this helps diagnose issues:

1. **Customer submits form** → job created (PENDING), Microsoft admin consent URL returned
2. **Customer's Global Admin consents** → our app's service principal is created in their tenant with the permissions they consented to
3. **Platform assigns elevated roles** → Exchange Administrator, SharePoint Administrator, Teams Administrator roles are assigned to our SP in their tenant (required for full service data collection). This may take up to 4 minutes after fresh consent due to Azure AD propagation.
4. **Monkey365 scans** → collects findings across Entra ID, Exchange Online, SharePoint Online, Teams, Purview, Defender, Intune, and Admin Portal
5. **AI analysis** → all services analysed in parallel via OpenAI; executive summary synthesised
6. **PDF generated** → professional report with charts, findings, remediation roadmap
7. **Email sent** → client receives report; admin receives BCC copy
8. **Service principal deleted** → our SP is fully removed from the client tenant (requires `Application.ReadWrite.All`). If that permission was not consented, elevated admin roles are revoked instead as a fallback.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| App won't start: `SECRET_KEY` validation error | `SECRET_KEY` not set in `.env` | Run `openssl rand -hex 32` and add to `.env` |
| Microsoft: "redirect URI mismatch" | `REDIRECT_URI` in `.env` doesn't exactly match App Registration | Must match exactly — `https://`, no trailing slash |
| `/error?reason=invalid_tenant` | Client declined consent or Microsoft didn't send `tenant` param | Confirm with client; verify App Registration redirect URI |
| Worker: cert errors from PowerShell | Wrong cert password or wrong `.pfx` file | Re-run `generate_cert.sh`, re-upload `.cer` to Azure, update `CERT_PASSWORD` |
| Role assignment failing with 403 | `RoleManagement.ReadWrite.Directory` not consented or still propagating | Check API permissions in App Registration; platform retries for up to 4 minutes automatically |
| Exchange/Teams/SharePoint findings empty | Admin roles not assigned (403 above) | See row above; also check worker logs for role assignment warnings |
| SP not deleted after audit (403 on DELETE) | `Application.ReadWrite.All` not consented | Add permission in App Registration → grant admin consent; platform falls back to role revocation only |
| Email: `Failed to acquire Graph token` | `Mail.Send` permission not granted or admin consent missing | App Registration → API permissions → Grant admin consent |
| Email: `Graph API sendMail failed: 403` | Sending mailbox doesn't exist or `Mail.Send` not propagated | Verify mailbox exists; wait 5 min and retry |
| No JSON output from Monkey365 | Monkey365 couldn't authenticate | Check worker logs for PowerShell errors; verify cert and permissions |
| "Something went wrong" on form submit | API container not reachable (502) | `docker compose restart nginx` to re-resolve upstream IPs after a redeploy |
| Cloudflare: 522 error | VM firewall blocking Cloudflare IP ranges on port 80/443 | `ufw allow 80/tcp && ufw allow 443/tcp` |
| Email going to spam | Sending domain not SPF/DKIM authenticated | Set up SPF and DKIM DNS records for your M365 sending domain |
| Database connection error on startup | `DATABASE_URL` password doesn't match `POSTGRES_PASSWORD` | Ensure both values match in `.env` |

---

## Ongoing Maintenance

**View logs:**
```bash
docker compose logs -f worker    # audit job progress (Monkey365, OpenAI, email)
docker compose logs -f api       # API requests and errors
docker compose logs -f nginx     # incoming traffic, 502 errors
```

**Restart a service:**
```bash
docker compose restart worker
```

**Restart nginx after a redeploy** (resolves IP stale upstream):
```bash
docker compose restart nginx
```

**Update the platform:**
```bash
git pull
docker compose up -d --build
docker compose restart nginx     # always restart nginx after rebuilding api
```

**Back up the database:**
```bash
docker compose exec postgres pg_dump -U m365audit m365audit > backup_$(date +%Y%m%d).sql
```

**Restore a backup:**
```bash
docker compose exec -T postgres psql -U m365audit m365audit < backup_20260101.sql
```

---

## Security Notes

- The `certs/monkey365.pfx` file grants access to **every customer tenant** that has consented. Back it up securely and rotate it if compromised.
- The platform deletes its service principal from each customer tenant after every scan. Verify this in logs: look for `Service principal ... fully removed from tenant ... 204 No Content`.
- If a scan fails mid-way and the SP isn't cleaned up, the periodic beat task (`detect_stuck_jobs`) will attempt cleanup every 30 minutes for jobs stuck longer than 2 hours.
- `ALLOWED_ORIGINS` restricts which domains can call the API from a browser. Set it to exactly your frontend domain in production.
