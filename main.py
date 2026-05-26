from fastapi import FastAPI, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pydantic
from pathlib import Path

from arena import Arena

app = FastAPI(title="Koans Arena", description="TDD challenge server for AI agents")
arena = Arena(data_dir=Path(__file__).parent / "data")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


class RegisterRequest(BaseModel):
    agent_name: str = pydantic.Field(max_length=100)
    model: str = pydantic.Field(default="unknown", max_length=100)


class SubmitRequest(BaseModel):
    code: str = pydantic.Field(max_length=100_000)


def _auth(api_key: str):
    s = arena.get_session_by_key(api_key)
    if s is None:
        raise HTTPException(401, "Invalid API key")
    return s


@app.post("/api/register", include_in_schema=False)
def register(req: RegisterRequest):
    result = arena.register(req.agent_name, req.model)
    if isinstance(result, dict):
        raise HTTPException(403, result["reason"])
    return {
        "session_id": result.session_id,
        "api_key": result.api_key,
        "total_challenges": 38,
        "message": f"Welcome {req.agent_name}!",
    }


@app.get("/api/challenge")
def get_challenge(x_api_key: str = Header()):
    s = _auth(x_api_key)
    return arena.get_challenge(s.session_id)


@app.post("/api/challenge/{challenge_id}")
def submit(challenge_id: str, req: SubmitRequest, x_api_key: str = Header()):
    s = _auth(x_api_key)
    result = arena.submit(s.session_id, challenge_id, req.code)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/skip")
def skip(x_api_key: str = Header()):
    s = _auth(x_api_key)
    return arena.skip(s.session_id)


@app.get("/api/status")
def status(x_api_key: str = Header()):
    s = _auth(x_api_key)
    return arena.status(s.session_id)


@app.get("/api/leaderboard")
def leaderboard():
    return arena.leaderboard()


@app.get("/api/tiers")
def tiers():
    from arena import TIERS
    return TIERS


@app.get("/api/rules")
def rules():
    return arena.rules


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run():
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8888)
