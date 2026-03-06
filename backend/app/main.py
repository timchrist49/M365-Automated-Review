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
