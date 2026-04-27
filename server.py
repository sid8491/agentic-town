"""
server.py — Minimal FastAPI app for Gurgaon Town Life.

Exposes:
  GET  /api/health          — liveness check
  GET  /api/llm             — current LLM provider + model
  POST /api/llm/{provider}  — switch active LLM provider at runtime

Will grow in Epic 6 with world-state endpoints, event streams, etc.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from engine.llm import llm_config

app = FastAPI(title="Gurgaon Town Life")

# CORS — allow all origins for local network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_primary": llm_config.get_primary()}


@app.post("/api/llm/{provider}")
def set_llm_provider(provider: str) -> dict:
    """
    Switch the active LLM provider.

    Returns {"provider": "<name>", "model": "<litellm-model-string>"} on success.
    Returns HTTP 400 with {"error": "..."} if the provider name is invalid.
    """
    try:
        llm_config.set_primary(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    return {"provider": llm_config.get_primary(), "model": llm_config.get_model()}


@app.get("/api/llm")
def get_llm_provider() -> dict:
    return {"provider": llm_config.get_primary(), "model": llm_config.get_model()}
