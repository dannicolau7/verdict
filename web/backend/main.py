"""Verdict API — FastAPI backend.

Start with:
    cd web/backend
    pip install -r requirements.txt
    pip install -e ../../   # install verdict-eval from repo root
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import compliance, config, eval, runs

app = FastAPI(
    title="Verdict API",
    description="Evaluation infrastructure for AI agents.",
    version="0.3.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router, prefix="/api")
app.include_router(eval.router, prefix="/api")
app.include_router(compliance.router, prefix="/api")
app.include_router(runs.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.3.1"}
