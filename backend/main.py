# load_dotenv MUST be first — before any local imports that initialize API clients
from dotenv import load_dotenv
load_dotenv()

"""
Aegis - Agentic LLM Gateway & Production Firewall
Main FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json

from app.api.routes import router
from app.db import init_db
from app.seed_data import seed_if_empty

app = FastAPI(
    title="Aegis - Agentic LLM Gateway",
    description="Intelligent LLM routing with causal hallucination detection",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - allow frontend access
_default_origins = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # Alternative dev port
]
_env_origins = os.getenv("ALLOWED_ORIGINS", "")
if _env_origins:
    try:
        allowed_origins = json.loads(_env_origins)
    except json.JSONDecodeError:
        # Support plain URL or comma-separated: "https://foo.vercel.app,http://localhost:5173"
        allowed_origins = [o.strip() for o in _env_origins.split(",") if o.strip()]
else:
    allowed_origins = _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database and seed demo data on first run."""
    await init_db()
    await seed_if_empty()


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "message": "Aegis API is running",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health():
    """Health check endpoint for deployment"""
    return {"status": "healthy", "service": "aegis-backend"}


# Include API routes
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
