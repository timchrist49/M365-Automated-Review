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

    # Email (sent via Microsoft Graph API — no SMTP credentials needed)
    EMAIL_FROM: str = ""          # e.g. m365-audit@encripti.com
    EMAIL_FROM_NAME: str = "Security Assessment Team"

    # Admin — receives failure alerts and a CC copy of every client report
    # Change this to your own address; clients will never see this address
    ADMIN_EMAIL: str = "info@encripti.com"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Database
    DATABASE_URL: str = "postgresql://m365audit:changeme@postgres:5432/m365audit"

    # Security — no default; must be set in .env (generate with: openssl rand -hex 32)
    SECRET_KEY: str
    # Comma-separated list of allowed CORS origins, e.g. "https://app.example.com"
    ALLOWED_ORIGINS: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
