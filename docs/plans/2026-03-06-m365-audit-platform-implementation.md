# M365 Security Audit Platform — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an end-to-end automated M365 security audit platform where clients click a link, consent via Microsoft admin consent, and receive a comprehensive AI-analyzed PDF report by email.

**Architecture:** FastAPI backend with Celery+Redis for async job execution, React frontend, PowerShell 7 + Monkey365 for M365 auditing, OpenAI gpt-5-nano for analysis, WeasyPrint for PDF generation. All services run via Docker Compose on Ubuntu.

**Tech Stack:** Python 3.11, FastAPI, Celery, Redis, SQLite, PowerShell 7, Monkey365, OpenAI SDK, WeasyPrint, React 18, Vite, Nginx, Docker Compose

---

## Project Structure (reference)

```
/root/m365-audit-platform/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── audit.py
│   │   │   └── auth.py
│   │   ├── tasks/
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py
│   │   │   └── audit_task.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── monkey365.py
│   │   │   ├── analyzer.py
│   │   │   ├── pdf_generator.py
│   │   │   └── email_sender.py
│   │   └── templates/
│   │       └── report.html
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_models.py
│   │   ├── test_audit_router.py
│   │   ├── test_auth_router.py
│   │   ├── test_monkey365.py
│   │   ├── test_analyzer.py
│   │   ├── test_pdf_generator.py
│   │   └── test_email_sender.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── Dockerfile.worker
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── pages/
│   │   │   ├── LandingPage.jsx
│   │   │   └── ThankYouPage.jsx
│   │   └── components/
│   │       └── LoadingSpinner.jsx
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── nginx/
│   └── nginx.conf
├── certs/
│   └── .gitkeep
├── scripts/
│   └── generate_cert.sh
├── docker-compose.yml
├── .env.example
└── .gitignore
```

---

## Phase 1: Project Scaffolding

### Task 1: Create directory structure and .gitignore

**Files:**
- Create: `/root/m365-audit-platform/.gitignore`
- Create: `/root/m365-audit-platform/.env.example`

**Step 1: Create .gitignore**

```bash
cd /root/m365-audit-platform
mkdir -p backend/app/routers backend/app/tasks backend/app/services backend/app/templates
mkdir -p backend/tests
mkdir -p frontend/src/pages frontend/src/components
mkdir -p nginx certs scripts
touch certs/.gitkeep
```

**Step 2: Write .gitignore**

Create `/root/m365-audit-platform/.gitignore`:

```gitignore
# Environment
.env
*.env

# Certificates — NEVER commit private keys
certs/*.pfx
certs/*.pem
certs/*.key
certs/*.cer
!certs/.gitkeep

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.venv/
venv/
*.egg-info/
dist/
htmlcov/
.coverage

# Node
node_modules/
frontend/dist/
frontend/.vite/

# Temp audit output
/tmp/monkey365/

# SQLite database
*.db
*.sqlite3

# IDE
.idea/
.vscode/
*.swp
```

**Step 3: Write .env.example**

Create `/root/m365-audit-platform/.env.example`:

```env
# Azure App Registration (Your Tenant)
AZURE_CLIENT_ID=your-app-client-id-here
AZURE_TENANT_ID=your-tenant-id-here
CERT_PASSWORD=your-certificate-password-here

# App URLs
APP_BASE_URL=https://your-domain.com
REDIRECT_URI=https://your-domain.com/auth/callback

# OpenAI
OPENAI_API_KEY=sk-...

# Email (SMTP)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
EMAIL_FROM=assessments@yourcompany.com
EMAIL_FROM_NAME=Your Company Security Team

# Redis
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=generate-a-long-random-string-here

# Paths (inside Docker)
CERT_PATH=/app/certs/monkey365.pfx
```

**Step 4: Commit**

```bash
cd /root/m365-audit-platform
git add .gitignore .env.example certs/.gitkeep
git commit -m "chore: scaffold project structure and environment config"
```

---

### Task 2: Backend requirements.txt and Dockerfile

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/Dockerfile`
- Create: `backend/Dockerfile.worker`

**Step 1: Write requirements.txt**

Create `/root/m365-audit-platform/backend/requirements.txt`:

```text
# Web framework
fastapi==0.115.0
uvicorn[standard]==0.30.6

# Database
sqlalchemy==2.0.35
aiosqlite==0.20.0

# Job queue
celery==5.4.0
redis==5.1.0

# OpenAI
openai==1.54.0

# PDF generation
weasyprint==62.3

# Email
aiosmtplib==3.0.2

# Config
pydantic-settings==2.5.2
python-multipart==0.0.12

# HTTP client (for any MS Graph calls)
httpx==0.27.2

# Testing
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
pytest-mock==3.14.0
```

**Step 2: Write Dockerfile (API)**

Create `/root/m365-audit-platform/backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install PowerShell 7
RUN apt-get update && apt-get install -y \
    wget \
    apt-transport-https \
    software-properties-common \
    curl \
    && wget -q "https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb" \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y powershell \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Monkey365 PowerShell module
RUN pwsh -Command "Install-Module -Name monkey365 -Scope AllUsers -Force -AcceptLicense"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 3: Write Dockerfile.worker (Celery)**

Create `/root/m365-audit-platform/backend/Dockerfile.worker`:

```dockerfile
FROM python:3.11-slim

# Same PS7 + Monkey365 install as API image
RUN apt-get update && apt-get install -y \
    wget \
    apt-transport-https \
    software-properties-common \
    curl \
    && wget -q "https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb" \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y powershell \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pwsh -Command "Install-Module -Name monkey365 -Scope AllUsers -Force -AcceptLicense"

COPY . .

CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
```

**Step 4: Commit**

```bash
cd /root/m365-audit-platform
git add backend/
git commit -m "chore: add backend requirements and Dockerfiles with PS7 + Monkey365"
```

---

### Task 3: Frontend scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/Dockerfile`

**Step 1: Write package.json**

Create `/root/m365-audit-platform/frontend/package.json`:

```json
{
  "name": "m365-audit-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.27.0",
    "axios": "^1.7.7"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.2",
    "vite": "^5.4.8"
  }
}
```

**Step 2: Write vite.config.js**

Create `/root/m365-audit-platform/frontend/vite.config.js`:

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    }
  }
})
```

**Step 3: Write index.html**

Create `/root/m365-audit-platform/frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>M365 Security Assessment</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

**Step 4: Write frontend Dockerfile**

Create `/root/m365-audit-platform/frontend/Dockerfile`:

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

**Step 5: Commit**

```bash
cd /root/m365-audit-platform
git add frontend/
git commit -m "chore: scaffold React frontend with Vite"
```

---

### Task 4: Docker Compose

**Files:**
- Create: `/root/m365-audit-platform/docker-compose.yml`
- Create: `/root/m365-audit-platform/nginx/nginx.conf`

**Step 1: Write docker-compose.yml**

Create `/root/m365-audit-platform/docker-compose.yml`:

```yaml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    networks:
      - internal

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    env_file: .env
    volumes:
      - ./certs:/app/certs:ro
      - audit_tmp:/tmp/monkey365
      - db_data:/app/data
    depends_on:
      - redis
    networks:
      - internal
    restart: unless-stopped

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile.worker
    env_file: .env
    volumes:
      - ./certs:/app/certs:ro
      - audit_tmp:/tmp/monkey365
      - db_data:/app/data
    depends_on:
      - redis
    networks:
      - internal
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
    networks:
      - internal
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - api
      - frontend
    networks:
      - internal
    restart: unless-stopped

networks:
  internal:
    driver: bridge

volumes:
  audit_tmp:
  db_data:
```

**Step 2: Write nginx.conf**

Create `/root/m365-audit-platform/nginx/nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;

    # API routes
    location /api/ {
        proxy_pass http://api:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # OAuth callback
    location /auth/ {
        proxy_pass http://api:8000/auth/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }

    # React SPA — all other routes
    location / {
        proxy_pass http://frontend:80/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Step 3: Commit**

```bash
cd /root/m365-audit-platform
git add docker-compose.yml nginx/
git commit -m "chore: add Docker Compose and Nginx reverse proxy config"
```

---

## Phase 2: Backend Core

### Task 5: Config and database setup

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`

**Step 1: Write failing test**

Create `/root/m365-audit-platform/backend/tests/__init__.py`: (empty)

Create `/root/m365-audit-platform/backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture
def test_db():
    from app.database import Base
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
```

Create `/root/m365-audit-platform/backend/tests/test_models.py`:

```python
from app.config import settings

def test_settings_has_required_fields():
    assert hasattr(settings, "AZURE_CLIENT_ID")
    assert hasattr(settings, "REDIS_URL")
    assert hasattr(settings, "OPENAI_API_KEY")
    assert hasattr(settings, "CERT_PATH")
```

**Step 2: Run test to verify it fails**

```bash
cd /root/m365-audit-platform/backend
pip install -r requirements.txt
pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

**Step 3: Write config.py**

Create `/root/m365-audit-platform/backend/app/__init__.py`: (empty)

Create `/root/m365-audit-platform/backend/app/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure
    AZURE_CLIENT_ID: str = ""
    AZURE_TENANT_ID: str = ""
    CERT_PASSWORD: str = ""
    CERT_PATH: str = "/app/certs/monkey365.pfx"

    # URLs
    APP_BASE_URL: str = "http://localhost:8000"
    REDIRECT_URI: str = "http://localhost:8000/auth/callback"

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Email
    SMTP_HOST: str = "smtp.sendgrid.net"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "Security Assessment Team"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Database
    DATABASE_URL: str = "sqlite:////app/data/audit.db"

    # Security
    SECRET_KEY: str = "dev-secret-change-in-production"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

**Step 4: Write database.py**

Create `/root/m365-audit-platform/backend/app/database.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
```

**Step 5: Run test to verify it passes**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_models.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/__init__.py backend/app/config.py backend/app/database.py backend/tests/
git commit -m "feat: add config settings and SQLite database setup"
```

---

### Task 6: Job model

**Files:**
- Create: `backend/app/models.py`

**Step 1: Write failing test**

Append to `/root/m365-audit-platform/backend/tests/test_models.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Job, JobStatus

def test_job_model_creates_with_uuid():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    from app.database import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    job = Job(email="client@test.com", company="Test Corp")
    db.add(job)
    db.commit()
    db.refresh(job)

    assert job.id is not None
    assert len(job.id) == 36  # UUID4 format
    assert job.status == JobStatus.PENDING
    assert job.tenant_id is None
    db.close()
```

**Step 2: Run to verify failure**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_models.py::test_job_model_creates_with_uuid -v
```

Expected: FAIL — `cannot import name 'Job'`

**Step 3: Write models.py**

Create `/root/m365-audit-platform/backend/app/models.py`:

```python
import uuid
from datetime import datetime, UTC
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, Text, Enum
from app.database import Base


class JobStatus(str, PyEnum):
    PENDING = "PENDING"
    CONSENTED = "CONSENTED"
    RUNNING = "RUNNING"
    ANALYZING = "ANALYZING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    tenant_id = Column(String(36), nullable=True)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    error_msg = Column(Text, nullable=True)
```

**Step 4: Run to verify pass**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_models.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat: add Job model with UUID primary key and status state machine"
```

---

### Task 7: FastAPI app entry point

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/routers/__init__.py`

**Step 1: Write main.py**

Create `/root/m365-audit-platform/backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import audit, auth

app = FastAPI(title="M365 Security Audit Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production via env var
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


app.include_router(audit.router, prefix="/api")
app.include_router(auth.router, prefix="/auth")


@app.get("/health")
def health():
    return {"status": "ok"}
```

Create `/root/m365-audit-platform/backend/app/routers/__init__.py`: (empty)

**Step 2: Verify app starts (no test needed — verified by import)**

```bash
cd /root/m365-audit-platform/backend
python -c "from app.main import app; print('App imports OK')"
```

Expected: `App imports OK`

**Step 3: Commit**

```bash
git add backend/app/main.py backend/app/routers/__init__.py
git commit -m "feat: add FastAPI app entry point with CORS and startup DB init"
```

---

## Phase 3: OAuth Flow

### Task 8: POST /api/start endpoint

**Files:**
- Create: `backend/app/routers/audit.py`
- Create: `backend/tests/test_audit_router.py`

**Step 1: Write failing test**

Create `/root/m365-audit-platform/backend/tests/test_audit_router.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_start_returns_consent_url():
    response = client.post("/api/start", json={
        "email": "admin@clientcorp.com",
        "company": "Client Corp"
    })
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "consent_url" in data
    assert "adminconsent" in data["consent_url"]
    assert "client_id" in data["consent_url"]


def test_start_rejects_duplicate_email():
    # First request
    client.post("/api/start", json={"email": "dup@test.com", "company": "Corp A"})
    # Second request with same email while first is active
    response = client.post("/api/start", json={"email": "dup@test.com", "company": "Corp B"})
    assert response.status_code == 409


def test_start_rejects_invalid_email():
    response = client.post("/api/start", json={"email": "not-an-email", "company": "Corp"})
    assert response.status_code == 422
```

**Step 2: Run to verify failure**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_audit_router.py -v
```

Expected: FAIL — router not yet created

**Step 3: Write audit.py router**

Create `/root/m365-audit-platform/backend/app/routers/audit.py`:

```python
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus

router = APIRouter()

MICROSOFT_ADMINCONSENT_URL = "https://login.microsoftonline.com/common/adminconsent"


class StartAuditRequest(BaseModel):
    email: EmailStr
    company: str


class StartAuditResponse(BaseModel):
    job_id: str
    consent_url: str


@router.post("/start", response_model=StartAuditResponse)
def start_audit(request: StartAuditRequest, db: Session = Depends(get_db)):
    # Rate limit: one active job per email
    existing = db.query(Job).filter(
        Job.email == request.email,
        Job.status.notin_([JobStatus.COMPLETE, JobStatus.FAILED])
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="An audit for this email is already in progress.")

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, email=request.email, company=request.company)
    db.add(job)
    db.commit()

    params = urlencode({
        "client_id": settings.AZURE_CLIENT_ID,
        "redirect_uri": settings.REDIRECT_URI,
        "state": job_id,
    })
    consent_url = f"{MICROSOFT_ADMINCONSENT_URL}?{params}"

    return StartAuditResponse(job_id=job_id, consent_url=consent_url)


@router.get("/status/{job_id}")
def get_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job.id, "status": job.status, "company": job.company}
```

**Step 4: Run to verify pass**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_audit_router.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/routers/audit.py backend/tests/test_audit_router.py
git commit -m "feat: add POST /api/start endpoint with rate limiting and consent URL generation"
```

---

### Task 9: GET /auth/callback endpoint

**Files:**
- Create: `backend/app/routers/auth.py`
- Create: `backend/tests/test_auth_router.py`

**Step 1: Write failing test**

Create `/root/m365-audit-platform/backend/tests/test_auth_router.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import Job, JobStatus
from app.database import SessionLocal

client = TestClient(app, follow_redirects=False)


def _create_job(job_id: str):
    db = SessionLocal()
    job = Job(id=job_id, email="test@client.com", company="Test Corp")
    db.add(job)
    db.commit()
    db.close()


def test_callback_valid_consent_queues_job():
    job_id = "aaaaaaaa-0000-0000-0000-000000000001"
    _create_job(job_id)

    with patch("app.routers.auth.run_audit_task") as mock_task:
        response = client.get(
            f"/auth/callback?tenant=bbbbbbbb-0000-0000-0000-000000000002&state={job_id}"
        )
    assert response.status_code == 302
    assert "/thank-you" in response.headers["location"]


def test_callback_missing_tenant_returns_error():
    response = client.get("/auth/callback?state=some-job-id")
    assert response.status_code == 302
    assert "error" in response.headers["location"]


def test_callback_invalid_job_id_returns_error():
    response = client.get("/auth/callback?tenant=bbbbbbbb-0000-0000-0000-000000000002&state=nonexistent-job")
    assert response.status_code == 302
    assert "error" in response.headers["location"]
```

**Step 2: Run to verify failure**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_auth_router.py -v
```

Expected: FAIL

**Step 3: Write auth.py router**

Create `/root/m365-audit-platform/backend/app/routers/auth.py`:

```python
import re
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus

router = APIRouter()

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def run_audit_task(job_id: str, tenant_id: str):
    """Import and dispatch Celery task. Separated for testability."""
    from app.tasks.audit_task import execute_audit
    execute_audit.delay(job_id, tenant_id)


@router.get("/callback")
def oauth_callback(
    state: str = "",
    tenant: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    frontend_base = settings.APP_BASE_URL

    if error:
        return RedirectResponse(url=f"{frontend_base}/error?reason=consent_denied")

    if not tenant or not UUID_RE.match(tenant):
        return RedirectResponse(url=f"{frontend_base}/error?reason=invalid_tenant")

    if not state:
        return RedirectResponse(url=f"{frontend_base}/error?reason=missing_state")

    job = db.query(Job).filter(Job.id == state).first()
    if not job or job.status != JobStatus.PENDING:
        return RedirectResponse(url=f"{frontend_base}/error?reason=invalid_job")

    # Store tenant_id and advance state
    job.tenant_id = tenant
    job.status = JobStatus.CONSENTED
    db.commit()

    # Dispatch async audit job
    run_audit_task(job.id, tenant)

    return RedirectResponse(url=f"{frontend_base}/thank-you?email={job.email}")
```

**Step 4: Run to verify pass**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_auth_router.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat: add /auth/callback handler — validates consent, queues Celery audit job"
```

---

## Phase 4: Celery Task Skeleton

### Task 10: Celery app configuration

**Files:**
- Create: `backend/app/tasks/__init__.py`
- Create: `backend/app/tasks/celery_app.py`

**Step 1: Write celery_app.py**

Create `/root/m365-audit-platform/backend/app/tasks/__init__.py`: (empty)

Create `/root/m365-audit-platform/backend/app/tasks/celery_app.py`:

```python
from celery import Celery
from app.config import settings

celery_app = Celery(
    "m365_audit",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.audit_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_time_limit=2700,        # 45 minutes hard limit
    task_soft_time_limit=2400,   # 40 minutes soft limit
    worker_max_tasks_per_child=1, # Fresh process per audit (memory safety)
)
```

**Step 2: Verify import**

```bash
cd /root/m365-audit-platform/backend
python -c "from app.tasks.celery_app import celery_app; print('Celery OK')"
```

Expected: `Celery OK`

**Step 3: Commit**

```bash
git add backend/app/tasks/
git commit -m "feat: configure Celery app with 45-minute timeout for long-running audits"
```

---

### Task 11: Audit task (orchestration shell)

**Files:**
- Create: `backend/app/tasks/audit_task.py`

**Step 1: Write the task skeleton**

Create `/root/m365-audit-platform/backend/app/tasks/audit_task.py`:

```python
import logging
from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)


def _update_job_status(job_id: str, status: JobStatus, error_msg: str = None):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = status
            if error_msg:
                job.error_msg = error_msg
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True, name="execute_audit")
def execute_audit(self, job_id: str, tenant_id: str):
    """
    Main audit orchestration task.
    Steps: run Monkey365 → analyze with OpenAI → generate PDF → email client
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        email = job.email
        company = job.company
    finally:
        db.close()

    try:
        # Step 1: Run Monkey365
        _update_job_status(job_id, JobStatus.RUNNING)
        from app.services.monkey365 import run_monkey365
        json_output_path = run_monkey365(job_id, tenant_id)

        # Step 2: Analyze findings with OpenAI
        _update_job_status(job_id, JobStatus.ANALYZING)
        from app.services.analyzer import analyze_findings
        analysis = analyze_findings(json_output_path)

        # Step 3: Generate PDF
        from app.services.pdf_generator import generate_pdf
        pdf_path = generate_pdf(job_id, company, analysis)

        # Step 4: Email report
        from app.services.email_sender import send_report_email
        send_report_email(email, company, pdf_path)

        _update_job_status(job_id, JobStatus.COMPLETE)
        logger.info(f"Audit complete for job {job_id}")

    except Exception as exc:
        logger.exception(f"Audit failed for job {job_id}: {exc}")
        _update_job_status(job_id, JobStatus.FAILED, error_msg=str(exc))
        raise
```

**Step 2: Commit**

```bash
git add backend/app/tasks/audit_task.py
git commit -m "feat: add Celery audit task orchestration — run/analyze/pdf/email pipeline"
```

---

## Phase 5: Monkey365 Service

### Task 12: PowerShell script generator + runner

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/monkey365.py`
- Create: `backend/tests/test_monkey365.py`

**Step 1: Write failing tests**

Create `/root/m365-audit-platform/backend/tests/test_monkey365.py`:

```python
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from app.services.monkey365 import build_ps_script, parse_monkey365_output


def test_build_ps_script_contains_required_params():
    script = build_ps_script(
        job_id="test-job-123",
        tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        cert_path="/app/certs/monkey365.pfx",
        client_id="client-id-here",
        out_dir="/tmp/monkey365/test-job-123"
    )
    assert "monkey365" in script
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in script
    assert "ExchangeOnline" in script
    assert "SharePointOnline" in script
    assert "AdminPortal" in script
    assert "MicrosoftTeams" in script
    assert "Purview" in script
    assert "JSON" in script
    assert "$env:CERT_PASSWORD" in script  # password never hardcoded


def test_parse_monkey365_output_extracts_all_services(tmp_path):
    # Simulate Monkey365 JSON output structure
    fake_output = {
        "EntraId": {"checks": [{"name": "MFA", "status": "FAIL", "severity": "High"}]},
        "ExchangeOnline": {"checks": [{"name": "DKIM", "status": "PASS", "severity": "None"}]},
        "SharePointOnline": {"checks": []},
        "MicrosoftTeams": {"checks": []},
        "Purview": {"checks": []},
        "AdminPortal": {"checks": []},
    }
    output_file = tmp_path / "monkey365_output.json"
    output_file.write_text(json.dumps(fake_output))

    result = parse_monkey365_output(str(tmp_path))
    assert "EntraId" in result
    assert "ExchangeOnline" in result
    assert result["EntraId"]["checks"][0]["name"] == "MFA"
```

**Step 2: Run to verify failure**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_monkey365.py -v
```

Expected: FAIL

**Step 3: Write monkey365.py**

Create `/root/m365-audit-platform/backend/app/services/__init__.py`: (empty)

Create `/root/m365-audit-platform/backend/app/services/monkey365.py`:

```python
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def build_ps_script(
    job_id: str,
    tenant_id: str,
    cert_path: str,
    client_id: str,
    out_dir: str,
) -> str:
    """Generate the PowerShell script for this audit job."""
    return f"""
Import-Module monkey365 -Force

$certPath = "{cert_path}"
$certPass = ($env:CERT_PASSWORD | ConvertTo-SecureString -AsPlainText -Force)

$param = @{{
    ClientId         = "{client_id}"
    Certificate      = $certPath
    CertFilePassword = $certPass
    TenantID         = "{tenant_id}"
    Instance         = 'Microsoft365'
    Collect          = @('ExchangeOnline', 'MicrosoftTeams', 'Purview', 'SharePointOnline', 'AdminPortal')
    IncludeEntraID   = $true
    ExportTo         = @('JSON')
    OutDir           = "{out_dir}"
}}

Invoke-Monkey365 @param
"""


def parse_monkey365_output(out_dir: str) -> dict:
    """Find and parse the JSON output file from Monkey365."""
    out_path = Path(out_dir)
    json_files = list(out_path.glob("*.json"))

    if not json_files:
        raise FileNotFoundError(f"No JSON output found in {out_dir}")

    # Monkey365 outputs one JSON file — take the first match
    with open(json_files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def run_monkey365(job_id: str, tenant_id: str) -> str:
    """
    Execute Monkey365 via PowerShell 7 subprocess.
    Returns the path to the output directory.
    """
    out_dir = f"/tmp/monkey365/{job_id}"
    os.makedirs(out_dir, exist_ok=True)

    script_content = build_ps_script(
        job_id=job_id,
        tenant_id=tenant_id,
        cert_path=settings.CERT_PATH,
        client_id=settings.AZURE_CLIENT_ID,
        out_dir=out_dir,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False, prefix=f"audit_{job_id}_"
    ) as script_file:
        script_file.write(script_content)
        script_path = script_file.name

    try:
        env = os.environ.copy()
        env["CERT_PASSWORD"] = settings.CERT_PASSWORD
        env["TARGET_TENANT_ID"] = tenant_id
        env["JOB_ID"] = job_id

        logger.info(f"Running Monkey365 for job {job_id}, tenant {tenant_id}")

        result = subprocess.run(
            ["pwsh", "-NonInteractive", "-NoProfile", "-File", script_path],
            env=env,
            capture_output=True,
            text=True,
            timeout=2400,  # 40 min — matches Celery soft limit
        )

        if result.returncode != 0:
            logger.error(f"Monkey365 stderr: {result.stderr}")
            raise RuntimeError(
                f"Monkey365 failed with exit code {result.returncode}: {result.stderr[:500]}"
            )

        logger.info(f"Monkey365 complete for job {job_id}")
        return out_dir

    finally:
        os.unlink(script_path)  # Always clean up script file
```

**Step 4: Run to verify pass**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_monkey365.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/monkey365.py backend/tests/test_monkey365.py
git commit -m "feat: add Monkey365 PS7 service — script generator, runner, and JSON parser"
```

---

## Phase 6: OpenAI Analyzer

### Task 13: OpenAI findings analyzer

**Files:**
- Create: `backend/app/services/analyzer.py`
- Create: `backend/tests/test_analyzer.py`

**Step 1: Write failing tests**

Create `/root/m365-audit-platform/backend/tests/test_analyzer.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from app.services.analyzer import chunk_findings_by_service, build_chunk_prompt


def test_chunk_findings_by_service_returns_all_services():
    raw = {
        "EntraId": {"checks": [{"name": "MFA"}]},
        "ExchangeOnline": {"checks": []},
        "SharePointOnline": {"checks": []},
        "MicrosoftTeams": {"checks": []},
        "Purview": {"checks": []},
        "AdminPortal": {"checks": []},
    }
    chunks = chunk_findings_by_service(raw)
    assert set(chunks.keys()) == {"EntraId", "ExchangeOnline", "SharePointOnline", "MicrosoftTeams", "Purview", "AdminPortal"}


def test_build_chunk_prompt_includes_service_name():
    prompt = build_chunk_prompt("ExchangeOnline", {"checks": [{"name": "DKIM", "status": "FAIL"}]})
    assert "ExchangeOnline" in prompt
    assert "DKIM" in prompt
    assert "Critical" in prompt   # severity levels mentioned in prompt
    assert "remediation" in prompt.lower()
```

**Step 2: Run to verify failure**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_analyzer.py -v
```

Expected: FAIL

**Step 3: Write analyzer.py**

Create `/root/m365-audit-platform/backend/app/services/analyzer.py`:

```python
import json
import logging
from typing import Any

from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.OPENAI_API_KEY)

KNOWN_SERVICES = [
    "EntraId", "ExchangeOnline", "SharePointOnline",
    "MicrosoftTeams", "Purview", "AdminPortal",
]

SERVICE_DISPLAY_NAMES = {
    "EntraId": "Microsoft Entra ID (Azure AD)",
    "ExchangeOnline": "Exchange Online",
    "SharePointOnline": "SharePoint Online",
    "MicrosoftTeams": "Microsoft Teams",
    "Purview": "Microsoft Purview",
    "AdminPortal": "M365 Admin Portal",
}

CHUNK_SYSTEM_PROMPT = """You are a senior Microsoft 365 security analyst writing a professional security assessment report section.

Analyze ALL the provided findings for this service area and produce a structured markdown report section.

Your output MUST include:

## [Service Name] Security Analysis

### Summary
2-3 sentence overview of the security posture for this service.

### Findings

For EVERY finding (pass AND fail), include it grouped by severity:

#### Critical Findings
- **[Check Name]** — [CIS Benchmark ref if available]
  - **Status:** FAIL
  - **Current State:** [what was found]
  - **Expected State:** [what it should be]
  - **Business Risk:** [clear business impact explanation]
  - **Remediation:** [specific step-by-step fix]

#### High Findings
[same format]

#### Medium Findings
[same format]

#### Low Findings
[same format]

#### Passing Checks
- [Check Name] — PASS: [brief note on what is correctly configured]

### Quick Wins
List 2-3 highest-impact remediations that can be done in under 1 hour.

Be specific, technical, and actionable. Never omit a finding. Use plain language for business risk explanations."""


SYNTHESIS_SYSTEM_PROMPT = """You are a senior Microsoft 365 security analyst writing the executive summary of a security assessment report.

Based on all the per-service analysis sections provided, produce:

## Executive Summary

A 3-5 sentence plain-language summary of the client's overall M365 security posture, written for a non-technical executive audience.

## Overall Risk Score

Score: [Critical / High / Medium / Low]
Justification: [2 sentences explaining the score]

## Risk Dashboard

| Service Area | Risk Level | Critical | High | Medium | Low | Passing |
|---|---|---|---|---|---|---|
| Entra ID | [level] | [count] | [count] | [count] | [count] | [count] |
| Exchange Online | ... |
| SharePoint Online | ... |
| Microsoft Teams | ... |
| Purview | ... |
| Admin Portal | ... |

## Prioritized Remediation Roadmap

### Immediate (Quick Wins — This Week)
[Top 5 highest-impact, lowest-effort fixes across all services]

### 30-Day Plan
[Medium-complexity remediations]

### 60-Day Plan
[Longer-term structural improvements]

### 90-Day Plan
[Strategic/architectural changes]

## CIS Benchmark Compliance Summary
Overall CIS M365 Foundations Benchmark compliance percentage and key gaps."""


def chunk_findings_by_service(raw_data: dict) -> dict:
    """Split Monkey365 JSON output into per-service chunks."""
    chunks = {}
    for service in KNOWN_SERVICES:
        if service in raw_data:
            chunks[service] = raw_data[service]
    # Also include any unexpected top-level keys (future-proofing)
    for key, value in raw_data.items():
        if key not in chunks and isinstance(value, dict):
            chunks[key] = value
    return chunks


def build_chunk_prompt(service_name: str, service_data: dict) -> str:
    display_name = SERVICE_DISPLAY_NAMES.get(service_name, service_name)
    data_json = json.dumps(service_data, indent=2)
    return (
        f"Analyze the following {display_name} security findings. "
        f"Include ALL findings — Critical, High, Medium, Low, and Passing.\n\n"
        f"Data:\n```json\n{data_json}\n```"
    )


def _call_openai(system_prompt: str, user_content: str, max_tokens: int = 16000) -> str:
    response = client.chat.completions.create(
        model="gpt-5-nano",
        reasoning_effort="medium",
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content


def analyze_findings(out_dir: str) -> dict:
    """
    Load Monkey365 JSON, chunk by service, analyze each with OpenAI,
    then synthesize into executive summary.
    Returns dict of {service: analysis_markdown, "synthesis": synthesis_markdown}
    """
    from app.services.monkey365 import parse_monkey365_output
    raw_data = parse_monkey365_output(out_dir)
    chunks = chunk_findings_by_service(raw_data)

    analyses = {}
    for service_name, service_data in chunks.items():
        logger.info(f"Analyzing {service_name} findings...")
        user_prompt = build_chunk_prompt(service_name, service_data)
        analyses[service_name] = _call_openai(CHUNK_SYSTEM_PROMPT, user_prompt, max_tokens=16000)

    # Final synthesis across all services
    logger.info("Running synthesis analysis...")
    all_analyses = "\n\n---\n\n".join(
        f"# {SERVICE_DISPLAY_NAMES.get(svc, svc)}\n\n{text}"
        for svc, text in analyses.items()
    )
    analyses["synthesis"] = _call_openai(
        SYNTHESIS_SYSTEM_PROMPT,
        f"Here are all per-service analysis sections:\n\n{all_analyses}",
        max_tokens=32000,
    )

    return analyses
```

**Step 4: Run tests to verify pass**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_analyzer.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/analyzer.py backend/tests/test_analyzer.py
git commit -m "feat: add OpenAI analyzer — per-service chunking and executive synthesis"
```

---

## Phase 7: PDF Generation

### Task 14: HTML report template and WeasyPrint renderer

**Files:**
- Create: `backend/app/templates/report.html`
- Create: `backend/app/services/pdf_generator.py`
- Create: `backend/tests/test_pdf_generator.py`

**Step 1: Write failing test**

Create `/root/m365-audit-platform/backend/tests/test_pdf_generator.py`:

```python
import os
import pytest
from unittest.mock import patch
from app.services.pdf_generator import generate_pdf, render_html


def test_render_html_includes_company_name():
    analysis = {
        "synthesis": "## Executive Summary\nThis tenant has several issues.",
        "EntraId": "## Entra ID\nSome findings here.",
    }
    html = render_html(company="Acme Corp", analysis=analysis, job_id="test-123")
    assert "Acme Corp" in html
    assert "Executive Summary" in html
    assert "Entra ID" in html


def test_render_html_includes_all_service_sections():
    services = ["EntraId", "ExchangeOnline", "SharePointOnline", "MicrosoftTeams", "Purview", "AdminPortal"]
    analysis = {svc: f"## {svc} findings" for svc in services}
    analysis["synthesis"] = "## Summary"
    html = render_html(company="Corp", analysis=analysis, job_id="j1")
    for svc in services:
        assert svc in html
```

**Step 2: Run to verify failure**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_pdf_generator.py -v
```

Expected: FAIL

**Step 3: Write HTML template**

Create `/root/m365-audit-platform/backend/app/templates/report.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <style>
    @page {
      size: A4;
      margin: 20mm 15mm 20mm 15mm;
      @bottom-center {
        content: "Confidential — " string(company) " M365 Security Assessment | Page " counter(page) " of " counter(pages);
        font-size: 8pt;
        color: #888;
      }
    }

    body { font-family: Arial, sans-serif; font-size: 10pt; color: #1a1a1a; }
    h1 { font-size: 28pt; color: #003087; margin-bottom: 4px; }
    h2 { font-size: 16pt; color: #003087; border-bottom: 2px solid #003087; padding-bottom: 4px; margin-top: 24px; }
    h3 { font-size: 12pt; color: #1a1a1a; margin-top: 16px; }
    h4 { font-size: 10pt; color: #555; margin-top: 12px; }

    .cover { page-break-after: always; text-align: center; padding-top: 80px; }
    .cover .logo-placeholder { width: 200px; height: 80px; background: #e8edf5; margin: 0 auto 32px; display: flex; align-items: center; justify-content: center; color: #888; font-size: 12pt; border: 2px dashed #ccc; }
    .cover .company { font-size: 18pt; color: #444; margin-top: 16px; }
    .cover .date { font-size: 11pt; color: #888; margin-top: 8px; }
    .cover .confidential { margin-top: 40px; font-size: 9pt; color: #cc0000; font-weight: bold; }

    .section { page-break-before: always; }

    table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 9pt; }
    th { background: #003087; color: white; padding: 6px 8px; text-align: left; }
    td { padding: 5px 8px; border-bottom: 1px solid #eee; }
    tr:nth-child(even) td { background: #f8f9fc; }

    .risk-critical { color: #cc0000; font-weight: bold; }
    .risk-high     { color: #e65c00; font-weight: bold; }
    .risk-medium   { color: #cc8800; font-weight: bold; }
    .risk-low      { color: #006600; }
    .risk-pass     { color: #008800; }

    .findings { margin: 0; }
    .finding-block { border-left: 4px solid #ccc; padding: 8px 12px; margin: 8px 0; background: #fafafa; }
    .finding-block.critical { border-color: #cc0000; background: #fff5f5; }
    .finding-block.high     { border-color: #e65c00; background: #fff8f5; }
    .finding-block.medium   { border-color: #cc8800; background: #fffbf0; }
    .finding-block.low      { border-color: #006600; background: #f5fff5; }

    pre, code { font-family: 'Courier New', monospace; font-size: 8.5pt; background: #f4f4f4; padding: 2px 4px; }
  </style>
  <title>M365 Security Assessment — {{ company }}</title>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover">
  <div class="logo-placeholder">[YOUR LOGO HERE]</div>
  <h1>M365 Security Assessment</h1>
  <div class="company">{{ company }}</div>
  <div class="date">{{ date }}</div>
  <div class="confidential">CONFIDENTIAL — For Authorized Recipients Only</div>
</div>

<!-- SYNTHESIS / EXECUTIVE SUMMARY -->
<div class="section">
{{ synthesis_html }}
</div>

<!-- PER-SERVICE SECTIONS -->
{% for service_name, display_name, content_html in service_sections %}
<div class="section">
  <h2>{{ display_name }}</h2>
  {{ content_html }}
</div>
{% endfor %}

</body>
</html>
```

**Step 4: Write pdf_generator.py**

Create `/root/m365-audit-platform/backend/app/services/pdf_generator.py`:

```python
import logging
import os
from datetime import datetime, UTC
from pathlib import Path

import markdown
from weasyprint import HTML

logger = logging.getLogger(__name__)

SERVICE_DISPLAY_NAMES = {
    "EntraId": "Microsoft Entra ID",
    "ExchangeOnline": "Exchange Online",
    "SharePointOnline": "SharePoint Online",
    "MicrosoftTeams": "Microsoft Teams",
    "Purview": "Microsoft Purview",
    "AdminPortal": "M365 Admin Portal",
}

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "report.html"


def _md_to_html(md_text: str) -> str:
    """Convert markdown to HTML."""
    return markdown.markdown(md_text, extensions=["tables", "fenced_code"])


def render_html(company: str, analysis: dict, job_id: str) -> str:
    """Render the full HTML report from analysis data."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    synthesis_html = _md_to_html(analysis.get("synthesis", ""))

    service_sections = []
    for key, display in SERVICE_DISPLAY_NAMES.items():
        if key in analysis:
            service_sections.append((key, display, _md_to_html(analysis[key])))

    # Simple template substitution (avoiding Jinja2 dependency)
    html = template.replace("{{ company }}", company)
    html = html.replace("{{ date }}", datetime.now(UTC).strftime("%B %d, %Y"))
    html = html.replace("{{ synthesis_html }}", synthesis_html)

    # Build service sections HTML
    sections_html = ""
    for service_name, display_name, content_html in service_sections:
        sections_html += f"""
        <div class="section">
          <h2>{display_name}</h2>
          {content_html}
        </div>
        """

    # Replace Jinja-style loop with built sections
    import re
    html = re.sub(
        r"\{%.*?%\}.*?\{%.*?%\}",
        sections_html,
        html,
        flags=re.DOTALL,
    )

    return html


def generate_pdf(job_id: str, company: str, analysis: dict) -> str:
    """Generate PDF report. Returns path to the generated PDF file."""
    out_dir = f"/tmp/monkey365/{job_id}"
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = f"{out_dir}/report_{job_id}.pdf"

    html_content = render_html(company=company, analysis=analysis, job_id=job_id)

    logger.info(f"Generating PDF for job {job_id}")
    HTML(string=html_content).write_pdf(pdf_path)
    logger.info(f"PDF generated: {pdf_path}")

    return pdf_path
```

**Step 5: Install markdown library**

Add to `backend/requirements.txt`:
```
markdown==3.7
```

**Step 6: Run tests to verify pass**

```bash
cd /root/m365-audit-platform/backend
pip install markdown
pytest tests/test_pdf_generator.py -v
```

Expected: All PASS

**Step 7: Commit**

```bash
git add backend/app/templates/ backend/app/services/pdf_generator.py backend/tests/test_pdf_generator.py backend/requirements.txt
git commit -m "feat: add WeasyPrint PDF generator with full-coverage HTML report template"
```

---

## Phase 8: Email Sender

### Task 15: SMTP email service

**Files:**
- Create: `backend/app/services/email_sender.py`
- Create: `backend/tests/test_email_sender.py`

**Step 1: Write failing test**

Create `/root/m365-audit-platform/backend/tests/test_email_sender.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.email_sender import build_email_message


def test_build_email_message_has_correct_fields():
    msg = build_email_message(
        to_email="client@corp.com",
        company="Corp Inc",
        pdf_path="/tmp/fake.pdf",
        from_email="assessments@myco.com",
        from_name="My Company",
    )
    assert msg["To"] == "client@corp.com"
    assert "Corp Inc" in msg["Subject"]
    assert msg["From"].startswith("My Company")
```

**Step 2: Run to verify failure**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_email_sender.py -v
```

Expected: FAIL

**Step 3: Write email_sender.py**

Create `/root/m365-audit-platform/backend/app/services/email_sender.py`:

```python
import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)

EMAIL_BODY_TEMPLATE = """Dear {company} Team,

Your complimentary Microsoft 365 Security Assessment is now complete.

Please find your confidential security report attached to this email.

IMPORTANT: This report contains sensitive security findings about your Microsoft 365 environment.
Please share it only with your IT leadership and security team.

Report highlights included:
- Full Microsoft Entra ID (Azure AD) audit
- Exchange Online security review
- SharePoint Online configuration assessment
- Microsoft Teams security posture
- Microsoft Purview compliance review
- M365 Admin Portal configuration review
- AI-generated remediation roadmap

If you have questions about any findings or need help with remediation,
please don't hesitate to reach out to our team.

Best regards,
{from_name}

---
This report was generated using Monkey365 and AI-powered analysis.
All findings reflect the configuration at the time of the assessment.
"""


def build_email_message(
    to_email: str,
    company: str,
    pdf_path: str,
    from_email: str,
    from_name: str,
) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = f"Your M365 Security Assessment Report — {company}"

    body = EMAIL_BODY_TEMPLATE.format(company=company, from_name=from_name)
    msg.attach(MIMEText(body, "plain"))

    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=f"M365_Security_Assessment_{company.replace(' ', '_')}.pdf",
            )
            msg.attach(attachment)

    return msg


def send_report_email(to_email: str, company: str, pdf_path: str) -> None:
    """Send the PDF report to the client via SMTP."""
    msg = build_email_message(
        to_email=to_email,
        company=company,
        pdf_path=pdf_path,
        from_email=settings.EMAIL_FROM,
        from_name=settings.EMAIL_FROM_NAME,
    )

    logger.info(f"Sending report email to {to_email} for {company}")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)

    logger.info(f"Report email sent to {to_email}")

    # Clean up PDF after sending
    if os.path.exists(pdf_path):
        os.unlink(pdf_path)
        logger.info(f"Cleaned up PDF: {pdf_path}")
```

**Step 4: Run tests to verify pass**

```bash
cd /root/m365-audit-platform/backend
pytest tests/test_email_sender.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/email_sender.py backend/tests/test_email_sender.py
git commit -m "feat: add SMTP email sender — attaches PDF and cleans up after send"
```

---

## Phase 9: Frontend

### Task 16: React app entry and routing

**Files:**
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`

**Step 1: Write main.jsx**

Create `/root/m365-audit-platform/frontend/src/main.jsx`:

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

**Step 2: Write App.jsx**

Create `/root/m365-audit-platform/frontend/src/App.jsx`:

```jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import LandingPage from './pages/LandingPage.jsx'
import ThankYouPage from './pages/ThankYouPage.jsx'

const styles = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f0f4f8;
    color: #1a1a2e;
    min-height: 100vh;
  }
`

export default function App() {
  return (
    <>
      <style>{styles}</style>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/thank-you" element={<ThankYouPage />} />
          <Route path="/error" element={<ErrorPage />} />
        </Routes>
      </BrowserRouter>
    </>
  )
}

function ErrorPage() {
  const params = new URLSearchParams(window.location.search)
  const reason = params.get('reason') || 'unknown'
  const messages = {
    consent_denied: 'The Microsoft consent was declined. Please try again and accept the permissions to proceed.',
    invalid_tenant: 'We could not identify your Microsoft tenant. Please contact us for assistance.',
    missing_state: 'Your session has expired. Please start the process again.',
    invalid_job: 'This assessment link is no longer valid. Please request a new one.',
  }
  return (
    <div style={{ display:'flex', justifyContent:'center', alignItems:'center', minHeight:'100vh' }}>
      <div style={{ maxWidth:480, padding:32, background:'white', borderRadius:12, boxShadow:'0 4px 24px rgba(0,0,0,0.1)', textAlign:'center' }}>
        <div style={{ fontSize:48, marginBottom:16 }}>⚠️</div>
        <h1 style={{ color:'#cc0000', marginBottom:12 }}>Something went wrong</h1>
        <p style={{ color:'#555', lineHeight:1.6 }}>{messages[reason] || 'An unexpected error occurred. Please contact us.'}</p>
        <a href="/" style={{ display:'inline-block', marginTop:24, padding:'10px 24px', background:'#003087', color:'white', borderRadius:6, textDecoration:'none' }}>
          Start Over
        </a>
      </div>
    </div>
  )
}
```

**Step 3: Commit**

```bash
cd /root/m365-audit-platform
git add frontend/src/main.jsx frontend/src/App.jsx
git commit -m "feat: add React app shell with routing and error page"
```

---

### Task 17: Landing page (client intake form)

**Files:**
- Create: `frontend/src/pages/LandingPage.jsx`

**Step 1: Write LandingPage.jsx**

Create `/root/m365-audit-platform/frontend/src/pages/LandingPage.jsx`:

```jsx
import { useState } from 'react'
import axios from 'axios'

const pageStyle = {
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  minHeight: '100vh',
  padding: '24px',
}

const cardStyle = {
  background: 'white',
  borderRadius: 16,
  boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
  padding: '48px 40px',
  maxWidth: 520,
  width: '100%',
}

const inputStyle = {
  width: '100%',
  padding: '12px 14px',
  border: '1.5px solid #ddd',
  borderRadius: 8,
  fontSize: 15,
  outline: 'none',
  transition: 'border-color 0.2s',
}

const btnStyle = (loading) => ({
  width: '100%',
  padding: '14px',
  background: loading ? '#aaa' : '#003087',
  color: 'white',
  border: 'none',
  borderRadius: 8,
  fontSize: 16,
  fontWeight: 600,
  cursor: loading ? 'not-allowed' : 'pointer',
  marginTop: 8,
  transition: 'background 0.2s',
})

export default function LandingPage() {
  const [email, setEmail] = useState('')
  const [company, setCompany] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await axios.post('/api/start', { email, company })
      // Redirect to Microsoft admin consent
      window.location.href = res.data.consent_url
    } catch (err) {
      if (err.response?.status === 409) {
        setError('An assessment for this email address is already in progress. Please check your inbox.')
      } else {
        setError('Something went wrong. Please try again.')
      }
      setLoading(false)
    }
  }

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        {/* Logo placeholder */}
        <div style={{ textAlign:'center', marginBottom:32 }}>
          <div style={{ width:160, height:60, background:'#e8edf5', margin:'0 auto 20px', borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', color:'#888', fontSize:12, border:'2px dashed #ccc' }}>
            [YOUR LOGO]
          </div>
          <h1 style={{ fontSize:24, color:'#003087', fontWeight:700 }}>Free M365 Security Assessment</h1>
          <p style={{ color:'#666', marginTop:8, lineHeight:1.6, fontSize:14 }}>
            We'll audit your Microsoft 365 environment and deliver a comprehensive security report directly to your inbox.
          </p>
        </div>

        {/* What's included */}
        <div style={{ background:'#f8faff', borderRadius:10, padding:'16px 20px', marginBottom:28 }}>
          <p style={{ fontSize:13, fontWeight:600, color:'#003087', marginBottom:8 }}>What's included in your report:</p>
          <ul style={{ fontSize:13, color:'#444', paddingLeft:18, lineHeight:1.8 }}>
            <li>Microsoft Entra ID (Azure AD) audit</li>
            <li>Exchange Online security review</li>
            <li>SharePoint Online assessment</li>
            <li>Microsoft Teams security posture</li>
            <li>Microsoft Purview compliance review</li>
            <li>AI-powered remediation roadmap</li>
          </ul>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom:16 }}>
            <label style={{ display:'block', fontSize:13, fontWeight:600, marginBottom:6, color:'#333' }}>
              Company Name
            </label>
            <input
              style={inputStyle}
              type="text"
              required
              placeholder="Acme Corporation"
              value={company}
              onChange={e => setCompany(e.target.value)}
            />
          </div>

          <div style={{ marginBottom:20 }}>
            <label style={{ display:'block', fontSize:13, fontWeight:600, marginBottom:6, color:'#333' }}>
              Email Address (report delivery)
            </label>
            <input
              style={inputStyle}
              type="email"
              required
              placeholder="admin@yourcompany.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </div>

          {error && (
            <div style={{ background:'#fff5f5', border:'1px solid #ffcccc', borderRadius:6, padding:'10px 14px', marginBottom:16, fontSize:13, color:'#cc0000' }}>
              {error}
            </div>
          )}

          <button type="submit" style={btnStyle(loading)} disabled={loading}>
            {loading ? 'Preparing consent...' : 'Start Free Assessment →'}
          </button>
        </form>

        <div style={{ marginTop:20, padding:'14px 16px', background:'#fffbf0', borderRadius:8, border:'1px solid #ffe0a0' }}>
          <p style={{ fontSize:12, color:'#775500', lineHeight:1.6 }}>
            <strong>Next step:</strong> You'll be redirected to Microsoft to grant read-only access to your M365 environment. A Global Administrator account is required. We never modify your data.
          </p>
        </div>

        <p style={{ fontSize:11, color:'#aaa', textAlign:'center', marginTop:20 }}>
          Your report will be emailed within 30–60 minutes of consent.
        </p>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
cd /root/m365-audit-platform
git add frontend/src/pages/LandingPage.jsx
git commit -m "feat: add landing page with M365 audit intake form and consent flow"
```

---

### Task 18: Thank you page

**Files:**
- Create: `frontend/src/pages/ThankYouPage.jsx`

**Step 1: Write ThankYouPage.jsx**

Create `/root/m365-audit-platform/frontend/src/pages/ThankYouPage.jsx`:

```jsx
export default function ThankYouPage() {
  const params = new URLSearchParams(window.location.search)
  const email = params.get('email') || 'your email address'

  return (
    <div style={{ display:'flex', justifyContent:'center', alignItems:'center', minHeight:'100vh', padding:24 }}>
      <div style={{ background:'white', borderRadius:16, boxShadow:'0 8px 32px rgba(0,0,0,0.12)', padding:'48px 40px', maxWidth:520, width:'100%', textAlign:'center' }}>
        <div style={{ fontSize:64, marginBottom:16 }}>✅</div>
        <h1 style={{ color:'#003087', fontSize:26, marginBottom:12 }}>Consent Received!</h1>
        <p style={{ color:'#444', fontSize:15, lineHeight:1.7, marginBottom:24 }}>
          Thank you. Your M365 Security Assessment is now running. We'll send your comprehensive report to:
        </p>
        <div style={{ background:'#f0f4ff', borderRadius:8, padding:'12px 20px', marginBottom:24, fontSize:15, fontWeight:600, color:'#003087' }}>
          {email}
        </div>
        <p style={{ color:'#666', fontSize:14, lineHeight:1.7 }}>
          The audit typically completes within <strong>30–60 minutes</strong> depending on your tenant size.
          You can safely close this window.
        </p>
        <div style={{ marginTop:32, padding:'16px', background:'#f8faff', borderRadius:8, fontSize:13, color:'#555', lineHeight:1.6 }}>
          <strong>What happens next:</strong><br/>
          Our system is auditing your Entra ID, Exchange, SharePoint, Teams, Purview, and Admin Portal settings.
          An AI-powered analysis will generate your personalized security report with a prioritized remediation roadmap.
        </div>
        <p style={{ marginTop:24, fontSize:12, color:'#aaa' }}>
          Didn't receive the email? Check your spam folder or contact us.
        </p>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
cd /root/m365-audit-platform
git add frontend/src/pages/ThankYouPage.jsx
git commit -m "feat: add thank-you page shown after successful Microsoft consent"
```

---

## Phase 10: Certificate Generation Script

### Task 19: Self-signed certificate helper script

**Files:**
- Create: `scripts/generate_cert.sh`

**Step 1: Write script**

Create `/root/m365-audit-platform/scripts/generate_cert.sh`:

```bash
#!/bin/bash
# Generate a self-signed certificate for Monkey365 App Registration
# Usage: ./scripts/generate_cert.sh [password]
# Outputs: certs/monkey365.pfx and certs/monkey365.cer (public key for Azure upload)

set -e

CERT_DIR="$(dirname "$0")/../certs"
mkdir -p "$CERT_DIR"

PASSWORD="${1:-changeme}"
DAYS=730  # 2 years

echo "[1/4] Generating private key..."
openssl genrsa -out "$CERT_DIR/monkey365.key" 4096

echo "[2/4] Generating self-signed certificate..."
openssl req -new -x509 \
  -key "$CERT_DIR/monkey365.key" \
  -out "$CERT_DIR/monkey365.crt" \
  -days $DAYS \
  -subj "/CN=Monkey365-M365-Audit/O=SecurityAssessment/C=US"

echo "[3/4] Exporting PFX (private key + cert for Monkey365)..."
openssl pkcs12 -export \
  -out "$CERT_DIR/monkey365.pfx" \
  -inkey "$CERT_DIR/monkey365.key" \
  -in "$CERT_DIR/monkey365.crt" \
  -passout "pass:$PASSWORD"

echo "[4/4] Exporting public key CER (upload this to Azure App Registration)..."
openssl x509 -in "$CERT_DIR/monkey365.crt" -out "$CERT_DIR/monkey365.cer" -outform DER

# Secure permissions
chmod 600 "$CERT_DIR/monkey365.key" "$CERT_DIR/monkey365.pfx"
chmod 644 "$CERT_DIR/monkey365.cer"

# Clean up intermediate files
rm "$CERT_DIR/monkey365.key" "$CERT_DIR/monkey365.crt"

echo ""
echo "Done!"
echo "  PFX (for .env CERT_PATH):  $CERT_DIR/monkey365.pfx"
echo "  CER (upload to Azure):     $CERT_DIR/monkey365.cer"
echo "  Password used: $PASSWORD"
echo ""
echo "Next: Upload monkey365.cer to your Azure App Registration > Certificates & secrets > Certificates"
```

**Step 2: Make executable and commit**

```bash
chmod +x /root/m365-audit-platform/scripts/generate_cert.sh
git add scripts/generate_cert.sh
git commit -m "feat: add certificate generation script for Azure App Registration"
```

---

## Phase 11: Integration Tests and Final Wiring

### Task 20: Full pipeline integration test

**Files:**
- Create: `backend/tests/test_integration.py`

**Step 1: Write integration test**

Create `/root/m365-audit-platform/backend/tests/test_integration.py`:

```python
"""
Integration test: verifies full flow with mocked external services.
Does NOT call Microsoft, OpenAI, PowerShell, or SMTP.
"""
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app, follow_redirects=False)


def test_full_flow_start_to_callback():
    # Step 1: Start audit
    start_resp = client.post("/api/start", json={
        "email": "integration@test.com",
        "company": "Integration Test Corp"
    })
    assert start_resp.status_code == 200
    job_id = start_resp.json()["job_id"]
    consent_url = start_resp.json()["consent_url"]
    assert job_id
    assert "adminconsent" in consent_url

    # Step 2: Simulate Microsoft callback with consent
    with patch("app.routers.auth.run_audit_task") as mock_task:
        callback_resp = client.get(
            f"/auth/callback?tenant=cccccccc-0000-0000-0000-000000000003&state={job_id}"
        )
    assert callback_resp.status_code == 302
    assert "thank-you" in callback_resp.headers["location"]
    mock_task.assert_called_once_with(job_id, "cccccccc-0000-0000-0000-000000000003")

    # Step 3: Check job status
    status_resp = client.get(f"/api/status/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "CONSENTED"


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

**Step 2: Run all tests**

```bash
cd /root/m365-audit-platform/backend
pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add backend/tests/test_integration.py
git commit -m "test: add integration test for full OAuth consent → job queue flow"
```

---

## Phase 12: README and Setup Guide

### Task 21: README with setup instructions

**Files:**
- Create: `/root/m365-audit-platform/README.md`

**Step 1: Write README.md**

Create `/root/m365-audit-platform/README.md`:

```markdown
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

Microsoft Graph: User.Read.All, Application.Read.All, Policy.Read.All, Organization.Read.All,
RoleManagement.Read.Directory, GroupMember.Read.All, Directory.Read.All,
PrivilegedEligibilitySchedule.Read.AzureADGroup, PrivilegedAccess.Read.AzureADGroup,
RoleManagementPolicy.Read.AzureADGroup, Group.Read.All, SecurityEvents.Read.All,
IdentityRiskEvent.Read.All, UserAuthenticationMethod.Read.All,
AppCatalog.Read.All, Channel.ReadBasic.All, ChannelMember.Read.All,
ChannelSettings.Read.All, TeamSettings.Read.All

Exchange Online: Exchange.ManageAsApp

SharePoint: Sites.FullControl.All

Grant admin consent in your tenant after adding all permissions.

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values
```

### 4. Deploy

```bash
docker compose up -d --build
```

## Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Run tests
cd backend && pytest tests/ -v
```

## Architecture

See `docs/plans/2026-03-06-m365-audit-platform-design.md` for full design documentation.
```

**Step 2: Commit**

```bash
cd /root/m365-audit-platform
git add README.md
git commit -m "docs: add README with setup instructions and App Registration guide"
```

---

## Execution Checklist (in order)

- [ ] Task 1: Directory structure, .gitignore, .env.example
- [ ] Task 2: Backend requirements.txt + Dockerfiles
- [ ] Task 3: Frontend scaffold (Vite + React)
- [ ] Task 4: Docker Compose + Nginx
- [ ] Task 5: Config + database setup
- [ ] Task 6: Job model
- [ ] Task 7: FastAPI app entry point
- [ ] Task 8: POST /api/start endpoint
- [ ] Task 9: GET /auth/callback endpoint
- [ ] Task 10: Celery app config
- [ ] Task 11: Audit task orchestration
- [ ] Task 12: Monkey365 PS7 service
- [ ] Task 13: OpenAI analyzer
- [ ] Task 14: PDF generator + HTML template
- [ ] Task 15: Email sender
- [ ] Task 16: React app shell + routing
- [ ] Task 17: Landing page
- [ ] Task 18: Thank you page
- [ ] Task 19: Certificate generation script
- [ ] Task 20: Integration tests
- [ ] Task 21: README
