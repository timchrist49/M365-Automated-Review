# M365 Security Audit Platform — Design Document

**Date:** 2026-03-06
**Status:** Approved
**Type:** MVP — Free Assessment Tool

---

## Overview

An internal web platform that automates end-to-end Microsoft 365 security audits for clients. The operator sends clients a link; clients consent via Microsoft admin consent flow; Monkey365 runs a full M365 audit in the background; OpenAI analyzes all findings; a comprehensive branded PDF report is emailed to the client.

---

## System Architecture

```
Ubuntu VM
├── React SPA (Nginx)           — client-facing consent + status UI
├── FastAPI                     — OAuth orchestration, REST API
├── Celery Worker               — long-running audit job execution
├── Redis                       — Celery message broker
├── SQLite                      — job state persistence
├── PowerShell 7 + Monkey365   — M365 audit engine
├── OpenAI API (gpt-5-nano)    — findings analysis
├── WeasyPrint                  — PDF generation
└── SMTP/SendGrid               — report email delivery
```

### End-to-End Flow

```
1. Client visits URL → enters email + company name
2. Frontend → POST /api/start → backend returns consent_url
3. Client redirected to Microsoft admin consent endpoint
4. Client's Global Admin logs in and accepts permissions
5. Microsoft redirects to /auth/callback?tenant={id}&state={job_id}
6. Backend stores tenant_id, queues Celery audit job
7. Client sees "Check your email" page
8. Celery worker:
   a. Generates audit.ps1 with client tenant_id
   b. Runs: pwsh -File audit.ps1 → JSON output
   c. Chunks JSON by service area → OpenAI analysis
   d. Synthesizes all findings → executive summary
   e. Renders WeasyPrint PDF
   f. Emails PDF to client
   g. Cleans up temp files
   h. Updates job status → COMPLETE
```

---

## Azure App Registration (Your Tenant)

### Settings

| Setting | Value |
|---|---|
| Name | M365 Security Assessment |
| Supported account types | Accounts in any organizational directory (Multi-tenant) |
| Redirect URI | https://your-domain.com/auth/callback (Web) |
| Authentication method | Certificate (required for SharePoint on Linux) |

### API Permissions (Application — all require admin consent)

**Microsoft Graph:**
- User.Read.All
- Application.Read.All
- Policy.Read.All
- Organization.Read.All
- RoleManagement.Read.Directory
- GroupMember.Read.All
- Directory.Read.All
- PrivilegedEligibilitySchedule.Read.AzureADGroup
- PrivilegedAccess.Read.AzureADGroup
- RoleManagementPolicy.Read.AzureADGroup
- Group.Read.All
- SecurityEvents.Read.All
- IdentityRiskEvent.Read.All
- UserAuthenticationMethod.Read.All
- AppCatalog.Read.All (Teams)
- Channel.ReadBasic.All (Teams)
- ChannelMember.Read.All (Teams)
- ChannelSettings.Read.All (Teams)
- TeamSettings.Read.All (Teams)

**Office 365 Exchange Online:**
- Exchange.ManageAsApp

**SharePoint:**
- Sites.FullControl.All

### Entra Roles (assigned to service principal in client tenant post-consent)

| Role | Purpose |
|---|---|
| Global Reader | Exchange Online access |
| SharePoint Administrator | SharePoint Online access |

### OAuth Admin Consent URL

```
https://login.microsoftonline.com/common/adminconsent
  ?client_id={YOUR_APP_ID}
  &redirect_uri=https://your-domain.com/auth/callback
  &state={job_id}
```

> The client's Global Administrator (not Global Reader) must consent. After consent, your app's service principal is provisioned in their tenant. All subsequent API calls use client credentials (certificate) — no user session required.

---

## Authentication: Certificate (Not Client Secret)

**Critical:** On Linux (NIX/.NET Core), Monkey365's auth matrix confirms SharePoint Online does NOT support Client Secret authentication. Certificate authentication is required for full M365 coverage.

```
/app/certs/
├── monkey365.pfx    — certificate + private key (chmod 600)
└── monkey365.cer    — public key uploaded to App Registration
```

---

## Monkey365 Invocation

```powershell
# audit.ps1 — generated per job by Celery worker
Import-Module monkey365

$certPath = "/app/certs/monkey365.pfx"
$certPass = ($env:CERT_PASSWORD | ConvertTo-SecureString -AsPlainText -Force)

$param = @{
    ClientId         = $env:AZURE_CLIENT_ID
    Certificate      = $certPath
    CertFilePassword = $certPass
    TenantID         = $env:TARGET_TENANT_ID    # injected per job
    Instance         = 'Microsoft365'
    Collect          = @('ExchangeOnline', 'MicrosoftTeams', 'Purview', 'SharePointOnline', 'AdminPortal')
    IncludeEntraID   = $true
    ExportTo         = @('JSON')
    OutDir           = "/tmp/monkey365/$env:JOB_ID"
}
Invoke-Monkey365 @param
```

### Linux Prerequisites
- PowerShell 7 (cross-platform, supported by Monkey365 on Linux >= PS 6.0.4)
- Monkey365 installed via: `Install-Module -Name monkey365 -Scope CurrentUser`

---

## Job State Machine

```
PENDING → CONSENTED → RUNNING → ANALYZING → COMPLETE
                                           → FAILED
```

SQLite schema:

```sql
CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,   -- UUID
    email       TEXT NOT NULL,
    company     TEXT NOT NULL,
    tenant_id   TEXT,               -- set after consent
    status      TEXT NOT NULL,
    created_at  DATETIME,
    updated_at  DATETIME,
    error_msg   TEXT
);
```

- Celery task timeout: 45 minutes
- One active job per email address (rate limit)
- State token (job_id as `state`) expires after 1 hour

---

## OpenAI Analysis

**Model:** gpt-5-nano
**Strategy:** Chunk by service area — zero findings dropped

```python
response = openai_client.chat.completions.create(
    model="gpt-5-nano",
    reasoning_effort="medium",
    max_completion_tokens=16000,   # reasoning tokens + output
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": chunk_data}
    ]
)
# Final synthesis call uses max_completion_tokens=32000
```

### Chunking Strategy

```
monkey365_output.json
├── entra_id/     → chunk 1 → findings_entra.md
├── exchange/     → chunk 2 → findings_exchange.md
├── sharepoint/   → chunk 3 → findings_sharepoint.md
├── teams/        → chunk 4 → findings_teams.md
├── purview/      → chunk 5 → findings_purview.md
└── admin_portal/ → chunk 6 → findings_admin.md
                           ↓
                   synthesis call → executive_summary.md
```

Each chunk includes ALL findings (pass/fail/warn) with:
- Check name, status, severity
- Affected resource
- CIS benchmark reference
- Current value vs expected value

Per-chunk output format:
- Critical / High / Medium / Low findings — full detail + remediation
- Passing checks — listed to show client what's working

---

## PDF Report Structure (WeasyPrint)

```
1.  Cover Page — logo placeholder, client name, date, overall risk score
2.  Executive Summary + Overall Risk Score
3.  Risk Dashboard — heatmap per service area (color-coded severity)
4.  Entra ID — all findings (critical → passing)
5.  Exchange Online — all findings
6.  SharePoint Online — all findings
7.  Microsoft Teams — all findings
8.  Purview — all findings
9.  Admin Portal — all findings
10. Passing Checks Summary — what the client is doing right
11. Prioritized Remediation Roadmap — Quick wins / 30 / 60 / 90 days
12. CIS Benchmark Compliance Summary
```

Branding: placeholder template for MVP; full brand kit (logo, colors, fonts) added in v2.

---

## Email Delivery

```
To:      client-provided email
Subject: Your M365 Security Assessment Report — [Company Name]
Body:    Professional message noting confidentiality of findings
Attach:  report_{job_id}.pdf (deleted from disk after send)
```

SMTP provider configurable via `.env` (SendGrid, Mailgun, or standard SMTP).

---

## Security Hardening

| Concern | Mitigation |
|---|---|
| Certificate on disk | chmod 600, never committed to git |
| Tenant ID exposure | Server-side only, never returned to frontend |
| Job ID guessing | UUID v4 (not sequential) |
| Report persistence | Generated in /tmp, emailed, deleted immediately |
| Consent link reuse | state token expires after 1 hour |
| SSRF via tenant input | Validate tenant_id as UUID format |
| Abuse / spam | Max 1 active job per email address |
| Transport security | Nginx reverse proxy + Let's Encrypt (HTTPS) |

---

## Docker Compose Services

```yaml
services:
  frontend:   # React build served by Nginx
  api:        # FastAPI
  worker:     # Celery worker (runs pwsh, calls OpenAI)
  redis:      # Celery broker
```

All services on a private Docker network. Only Nginx exposed externally (ports 80/443).

---

## Tech Stack Summary

| Layer | Technology |
|---|---|
| Frontend | React + Nginx |
| Backend API | FastAPI (Python) |
| Job Queue | Celery + Redis |
| Database | SQLite |
| Audit Engine | PowerShell 7 + Monkey365 |
| AI Analysis | OpenAI gpt-5-nano (reasoning_effort=medium) |
| PDF Generation | WeasyPrint |
| Email | SendGrid/SMTP (configurable) |
| Auth | Entra ID multi-tenant admin consent + certificate |
| Deployment | Docker Compose on Ubuntu VM |

---

## References

- Monkey365: https://github.com/silverhack/monkey365
- Monkey365 Docs: https://silverhack.github.io/monkey365/
- Monkey365 Permissions: https://silverhack.github.io/monkey365/getting_started/permissions/
- Monkey365 Auth Matrix: https://silverhack.github.io/monkey365/authentication/supported_auth_methods_byapp/
- Microsoft Admin Consent: https://learn.microsoft.com/en-us/entra/identity-platform/v2-admin-consent
