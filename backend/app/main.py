from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import audit, auth

app = FastAPI(title="M365 Security Audit Platform", version="1.0.0")

_allowed_origins = (
    [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if settings.ALLOWED_ORIGINS
    else [settings.APP_BASE_URL]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def startup():
    init_db()


app.include_router(audit.router, prefix="/api")
app.include_router(auth.router, prefix="/auth")


@app.get("/health")
def health():
    return {"status": "ok"}
