from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pydantic
from pathlib import Path

from arena import Arena

app = FastAPI(title="Koans Arena", description="TDD challenge server for AI agents")
arena = Arena(data_dir=Path(__file__).parent / "data")


class RegisterRequest(BaseModel):
    agent_name: str = pydantic.Field(max_length=100)
    model: str = pydantic.Field(default="unknown", max_length=100)


class SubmitRequest(BaseModel):
    code: str = pydantic.Field(max_length=100_000)


@app.post("/api/register")
def register(req: RegisterRequest):
    session = arena.register(req.agent_name, req.model)
    return {
        "session_id": session.session_id,
        "total_challenges": len(arena.sessions[session.session_id].results) or 38,
        "message": f"Welcome {req.agent_name}! Use GET /api/challenge/{{session_id}} to start.",
    }


@app.get("/api/challenge/{session_id}")
def get_challenge(session_id: str):
    if session_id not in arena.sessions:
        raise HTTPException(404, "Session not found")
    return arena.get_challenge(session_id)


@app.post("/api/challenge/{session_id}/{challenge_id}")
def submit(session_id: str, challenge_id: str, req: SubmitRequest):
    if session_id not in arena.sessions:
        raise HTTPException(404, "Session not found")
    result = arena.submit(session_id, challenge_id, req.code)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/skip/{session_id}")
def skip(session_id: str):
    if session_id not in arena.sessions:
        raise HTTPException(404, "Session not found")
    return arena.skip(session_id)


@app.get("/api/status/{session_id}")
def status(session_id: str):
    if session_id not in arena.sessions:
        raise HTTPException(404, "Session not found")
    return arena.status(session_id)


@app.get("/api/leaderboard")
def leaderboard():
    return arena.leaderboard()


@app.get("/api/tiers")
def tiers():
    from arena import TIERS
    return TIERS


def run():
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8888)
