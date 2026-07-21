from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import tenants, initiatives, signals, assets, roadmaps, briefs, audit, auth, contact

# Creates tables on startup if they don't exist yet. Fine for SQLite/dev.
# For Postgres in production, switch to a real migration tool (Alembic)
# instead of relying on create_all.
Base.metadata.create_all(bind=engine)

settings = get_settings()

app = FastAPI(
    title="AutoStrat Loom API",
    description="Backend for the five Loom agents: Prioritize, Discover, Align, Sustain, Brief.",
    version="0.1.0",
)

# Lets the front end (served from a browser, likely a different origin than
# this API) actually call it. cors_origins defaults to "*" for local dev —
# set CORS_ORIGINS in .env to your real front-end domain(s) before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(contact.router)
app.include_router(tenants.router)
app.include_router(initiatives.router)
app.include_router(signals.router)
app.include_router(assets.router)
app.include_router(roadmaps.router)
app.include_router(briefs.router)
app.include_router(audit.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
