# M365 Security Audit Platform

Automated Microsoft 365 security assessment tool. Clients consent via Microsoft admin consent flow; Monkey365 audits their tenant; OpenAI generates a comprehensive PDF report delivered by email.

## Prerequisites

- Ubuntu VM with Docker and Docker Compose installed
- Microsoft Entra ID App Registration (multi-tenant, see setup below)
- OpenAI API key
- SMTP credentials (SendGrid recommended)
- Domain with HTTPS (Let's Encrypt recommended)

## Setup

### 1. Generate Certificate

```bash
./scripts/generate_cert.sh "YourCertPassword"
```

Upload `certs/monkey365.cer` to your Azure App Registration > Certificates & secrets > Certificates.

### 2. Azure App Registration

Create a multi-tenant app registration in your Entra ID tenant:

- **Supported account types:** Accounts in any organizational directory
- **Redirect URI:** `https://your-domain.com/auth/callback`
- **Authentication:** Certificate (upload monkey365.cer)

**API Permissions (Application):**

Microsoft Graph: `User.Read.All`, `Application.Read.All`, `Policy.Read.All`, `Organization.Read.All`,
`RoleManagement.Read.Directory`, `GroupMember.Read.All`, `Directory.Read.All`,
`PrivilegedEligibilitySchedule.Read.AzureADGroup`, `PrivilegedAccess.Read.AzureADGroup`,
`RoleManagementPolicy.Read.AzureADGroup`, `Group.Read.All`, `SecurityEvents.Read.All`,
`IdentityRiskEvent.Read.All`, `UserAuthenticationMethod.Read.All`,
`AppCatalog.Read.All`, `Channel.ReadBasic.All`, `ChannelMember.Read.All`,
`ChannelSettings.Read.All`, `TeamSettings.Read.All`

Exchange Online: `Exchange.ManageAsApp`

SharePoint: `Sites.FullControl.All`

Grant admin consent in your tenant after adding all permissions.

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values
```

Key variables:
| Variable | Description |
|----------|-------------|
| `AZURE_CLIENT_ID` | Your App Registration client ID |
| `AZURE_TENANT_ID` | Your tenant ID (issuer) |
| `CERT_PATH` | Path to monkey365.pfx inside container: `/app/certs/monkey365.pfx` |
| `CERT_PASSWORD` | Password used when generating the certificate |
| `APP_BASE_URL` | Public URL of your deployment, e.g. `https://audit.yourdomain.com` |
| `REDIRECT_URI` | OAuth callback: `https://audit.yourdomain.com/auth/callback` |
| `OPENAI_API_KEY` | OpenAI API key |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP port (587 for STARTTLS) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `EMAIL_FROM` | Sender email address |
| `EMAIL_FROM_NAME` | Sender display name |

### 4. Deploy

```bash
docker compose up -d --build
```

The platform will be available at `http://localhost` (or your domain with Nginx handling TLS).

### 5. HTTPS (Production)

Install Let's Encrypt:

```bash
apt install certbot
certbot certonly --standalone -d audit.yourdomain.com
```

Update `nginx/nginx.conf` to add an HTTPS server block pointing to `/etc/letsencrypt/live/`.

## Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Run backend tests
cd backend && python3 -m pytest tests/ -v
```

## Architecture

```
Client Browser
    │
    ▼
Nginx (port 80/443)
    ├── /api/* → FastAPI (api:8000)
    ├── /auth/* → FastAPI (api:8000)
    └── /* → React SPA (frontend:80)

FastAPI
    ├── POST /api/start — creates job, returns Microsoft consent URL
    ├── GET /api/status/{job_id} — job status polling
    └── GET /auth/callback — receives Microsoft consent, enqueues job

Redis ← Celery broker

Celery Worker
    └── execute_audit task:
        1. run_monkey365() — PowerShell 7 + Monkey365, outputs JSON
        2. analyze_findings() — OpenAI gpt-5-nano analysis per service + synthesis
        3. generate_pdf() — WeasyPrint HTML→PDF
        4. send_report_email() — SMTP delivery with PDF attachment

SQLite (job state machine)
    PENDING → CONSENTED → RUNNING → ANALYZING → COMPLETE / FAILED
```

## Audit Coverage

Monkey365 audits these M365 service areas:

- **Microsoft Entra ID** — MFA, Conditional Access, Privileged Identity Management, Guest Access
- **Exchange Online** — DKIM, DMARC, SPF, mailbox auditing, forwarding rules
- **SharePoint Online** — external sharing, permissions, data governance
- **Microsoft Teams** — guest access, external federation, meeting policies
- **Microsoft Purview** — DLP policies, sensitivity labels, retention policies
- **M365 Admin Portal** — admin roles, legacy auth, self-service settings

## Security Notes

- Certificate private key is never stored in code — PFX lives in `certs/` (gitignored)
- Redis and all internal services are on a private Docker bridge network
- Only Nginx is exposed externally (ports 80/443)
- Audit output JSON is written to a named Docker volume, deleted after email delivery
- Client tenant_id is validated as a UUID before any processing

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Callback redirects to `/error?reason=invalid_tenant` | Ensure Microsoft sent `tenant` parameter — check App Registration redirect URI matches exactly |
| Worker not processing jobs | Check Redis is healthy: `docker compose exec redis redis-cli ping` |
| PDF generation fails | WeasyPrint requires `libcairo2` — verify Dockerfile installed it |
| Email not delivered | Check SMTP credentials and that port 587 is not blocked by your host |
| Monkey365 auth fails | Verify certificate thumbprint in Azure matches PFX, and all API permissions have admin consent |
