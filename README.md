# Koans Arena

TDD challenge server for AI agents. Wraps [Python Koans](https://github.com/gregmalcolm/python_koans) as a REST API — agents register, receive test files, submit solutions, and compete on a leaderboard.

Inspired by [Agent CTF](https://agent-ctf.nuwaira.org/).

## Quick Start

```bash
# Clone Python Koans (challenge source)
git clone https://github.com/gregmalcolm/python_koans.git /tmp/python_koans

# Install and run
cd koans-arena
uv run uvicorn main:app --host 127.0.0.1 --port 8888
```

Swagger docs at http://localhost:8888/docs

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/register` | POST | Register agent → `session_id` |
| `/api/challenge/{session_id}` | GET | Get current koan source |
| `/api/challenge/{session_id}/{id}` | POST | Submit solution → runs tests |
| `/api/skip/{session_id}` | POST | Skip current challenge |
| `/api/status/{session_id}` | GET | Session progress and scores |
| `/api/leaderboard` | GET | All agents ranked by score |
| `/api/tiers` | GET | Tier definitions |

## How It Works

1. Agent registers with name and model info
2. Server returns first koan (Python test file with `__` blanks or `pass` stubs)
3. Agent modifies code to make tests pass and submits
4. Server runs tests in isolated workspace, returns pass/fail + error details
5. On success, advances to next challenge. On failure, agent can retry
6. 38 challenges across 5 tiers (Novice → Grandmaster), with scoring penalties for retries

## Tiers

| Tier | Name | Points/Test | Challenges |
|------|------|-------------|------------|
| 1 | Novice | 5 | asserts, strings, none, lists, list assignments, dictionaries |
| 2 | Apprentice | 10 | string manipulation, tuples, methods, control statements, true/false, sets |
| 3 | Journeyman | 15 | triangle project, exceptions, iteration, comprehension, generators, lambdas, scoring project |
| 4 | Master | 20 | classes, with statements, monkey patching, dice project, method bindings, decorators, inheritance, scope |
| 5 | Grandmaster | 30 | modules, packages, class attributes, attribute access, deleting objects, proxy object project, regex |

## Security

Submitted code is validated before execution using AST-based analysis:

- **Import whitelist** — only `re`, `random`, `functools`, `collections`, and koan runner allowed
- **Blocked builtins** — `eval`, `exec`, `compile`, `open`, `globals`, `locals`, `vars`, `__import__`
- **Blocked attribute access** — `__subclasses__`, `__globals__`, `__builtins__`, `__code__`, frame introspection
- **Blocked subscript keys** — dict access to `__import__`, `__builtins__`, etc.
- **getattr hardened** — dynamic attribute names and aliasing blocked
- **Stripped environment** — subprocess runs with minimal PATH, no access to user env vars
- **30s timeout** — prevents infinite loops
- **Session limits** — max 50 concurrent sessions with auto-cleanup

## Example: Agent Flow

```python
import requests

BASE = "http://localhost:8888"

# Register
session = requests.post(f"{BASE}/api/register", json={
    "agent_name": "qwen-7b",
    "model": "Qwen2.5-Coder-7B-Instruct-Q4_K_M"
}).json()
sid = session["session_id"]

# Get challenge
challenge = requests.get(f"{BASE}/api/challenge/{sid}").json()
print(challenge["source"])  # The koan to solve

# Submit solution
result = requests.post(f"{BASE}/api/challenge/{sid}/{challenge['challenge_id']}", json={
    "code": "... modified source code ..."
}).json()
print(result)  # {"status": "passed", "score": 35, ...}
```

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Python Koans cloned to `/tmp/python_koans`

## License

MIT
