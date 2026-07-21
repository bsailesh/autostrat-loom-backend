from fastapi import FastAPI

from app.database import Base, engine
from app.routers import tenants, initiatives, signals, assets, roadmaps, briefs, audit

# Creates tables on startup if they don't exist yet. Fine for SQLite/dev.
# For Postgres in production, switch to a real migration tool (Alembic)
# instead of relying on create_all.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AutoStrat Loom API",
    description="Backend for the five Loom agents: Prioritize, Discover, Align, Sustain, Brief.",
    version="0.1.0",
)

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
