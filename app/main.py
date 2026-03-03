"""
Find Your University — FastAPI application entry point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.limiter import limiter
from app.api import auth, match, universities, applications, consultants, documents

settings = get_settings()

# ─── APScheduler for weekly College Scorecard sync ───────────────────────────
scheduler = AsyncIOScheduler()


async def _sync_scorecard():
    """Scheduled task: re-sync US College Scorecard data weekly."""
    try:
        import importlib
        sync_mod = importlib.import_module("scripts.import_us_scorecard")
        await sync_mod.run_sync(limit=1000)
        print("[scheduler] Scorecard sync completed")
    except Exception as exc:
        print(f"[scheduler] Scorecard sync failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    parts = settings.SCORECARD_SYNC_CRON.split()
    scheduler.add_job(
        _sync_scorecard,
        CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4]
        ),
        id="scorecard_sync",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[startup] APScheduler started (scorecard sync: {settings.SCORECARD_SYNC_CRON})")
    yield
    # Shutdown
    scheduler.shutdown(wait=False)


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Find Your University API",
    description="Education matchmaking platform for Bangladeshi students",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiter middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(match.router)
app.include_router(universities.router)
app.include_router(applications.router)
app.include_router(consultants.router)
app.include_router(documents.router)


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": "1.0.0", "env": settings.APP_ENV}


# ─── Global error handler ─────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )
