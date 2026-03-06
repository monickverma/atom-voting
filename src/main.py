"""
Atom Voting — application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import router as auth_router
from src.api.routes import router as voting_router
from src.api.websockets import router as ws_router

app = FastAPI(
    title="Atom Voting",
    description="A transparent, open-source cryptographic voting API.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voting_router)
app.include_router(auth_router)
app.include_router(ws_router)


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    """Health check endpoint for load balancers and CI."""
    return {"status": "ok", "version": "1.0.0"}
