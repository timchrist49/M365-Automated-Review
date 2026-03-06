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
