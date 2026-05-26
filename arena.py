import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

from sandbox import check_code

KOANS_SOURCE = Path("/tmp/python_koans")

CHALLENGE_ORDER = [
    "about_asserts",
    "about_strings",
    "about_none",
    "about_lists",
    "about_list_assignments",
    "about_dictionaries",
    "about_string_manipulation",
    "about_tuples",
    "about_methods",
    "about_control_statements",
    "about_true_and_false",
    "about_sets",
    "about_triangle_project",
    "about_exceptions",
    "about_triangle_project2",
    "about_iteration",
    "about_comprehension",
    "about_generators",
    "about_lambdas",
    "about_scoring_project",
    "about_classes",
    "about_with_statements",
    "about_monkey_patching",
    "about_dice_project",
    "about_method_bindings",
    "about_decorating_with_functions",
    "about_decorating_with_classes",
    "about_inheritance",
    "about_multiple_inheritance",
    "about_scope",
    "about_modules",
    "about_packages",
    "about_class_attributes",
    "about_attribute_access",
    "about_deleting_objects",
    "about_proxy_object_project",
    "about_extra_credit",
    "about_regex",
]

TIERS = {
    1: {"name": "Novice", "challenges": CHALLENGE_ORDER[:6], "points_per_test": 5},
    2: {"name": "Apprentice", "challenges": CHALLENGE_ORDER[6:12], "points_per_test": 10},
    3: {"name": "Journeyman", "challenges": CHALLENGE_ORDER[12:20], "points_per_test": 15},
    4: {"name": "Master", "challenges": CHALLENGE_ORDER[20:30], "points_per_test": 20},
    5: {"name": "Grandmaster", "challenges": CHALLENGE_ORDER[30:], "points_per_test": 30},
}


def tier_for_challenge(challenge_id: str) -> tuple[int, dict]:
    for tier_num, tier in TIERS.items():
        if challenge_id in tier["challenges"]:
            return tier_num, tier
    return 0, {"name": "Unknown", "points_per_test": 5}


@dataclass
class ChallengeResult:
    challenge_id: str
    attempts: int = 0
    passed: int = 0
    total: int = 0
    score: int = 0
    completed: bool = False
    failures: list = field(default_factory=list)
    elapsed_seconds: float = 0


@dataclass
class Session:
    session_id: str
    agent_name: str
    model: str
    started_at: float
    current_index: int = 0
    results: dict = field(default_factory=dict)
    total_score: int = 0
    workspace: str = ""

    def current_challenge(self) -> str | None:
        if self.current_index >= len(CHALLENGE_ORDER):
            return None
        return CHALLENGE_ORDER[self.current_index]


class Arena:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, Session] = {}
        self._load_sessions()

    def _sessions_file(self) -> Path:
        return self.data_dir / "sessions.json"

    def _load_sessions(self):
        f = self._sessions_file()
        if f.exists():
            raw = json.loads(f.read_text())
            for sid, data in raw.items():
                results = {}
                for cid, r in data.pop("results", {}).items():
                    results[cid] = ChallengeResult(**r)
                self.sessions[sid] = Session(**data, results=results)

    def _save_sessions(self):
        raw = {}
        for sid, s in self.sessions.items():
            d = asdict(s)
            raw[sid] = d
        self._sessions_file().write_text(json.dumps(raw, indent=2))

    MAX_SESSIONS = 50

    def _cleanup_old_sessions(self):
        if len(self.sessions) < self.MAX_SESSIONS:
            return
        by_time = sorted(self.sessions.values(), key=lambda s: s.started_at)
        while len(self.sessions) >= self.MAX_SESSIONS:
            oldest = by_time.pop(0)
            workspace = Path(oldest.workspace)
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
            del self.sessions[oldest.session_id]

    def register(self, agent_name: str, model: str) -> Session:
        self._cleanup_old_sessions()
        sid = uuid.uuid4().hex[:12]
        workspace = tempfile.mkdtemp(prefix=f"koans-{sid}-")
        shutil.copytree(KOANS_SOURCE / "koans", Path(workspace) / "koans")
        shutil.copytree(KOANS_SOURCE / "runner", Path(workspace) / "runner")
        for extra in ["libs", "example_file.txt"]:
            src = KOANS_SOURCE / extra
            if src.exists():
                if src.is_dir():
                    shutil.copytree(src, Path(workspace) / extra)
                else:
                    shutil.copy2(src, Path(workspace) / extra)

        session = Session(
            session_id=sid,
            agent_name=agent_name,
            model=model,
            started_at=time.time(),
            workspace=workspace,
        )
        self.sessions[sid] = session
        self._save_sessions()
        return session

    def get_challenge(self, session_id: str) -> dict:
        s = self.sessions[session_id]
        cid = s.current_challenge()
        if cid is None:
            return {"status": "completed", "message": "All challenges done!"}

        koan_path = Path(s.workspace) / "koans" / f"{cid}.py"
        source = koan_path.read_text()
        tier_num, tier = tier_for_challenge(cid)

        return {
            "challenge_id": cid,
            "index": s.current_index,
            "total_challenges": len(CHALLENGE_ORDER),
            "tier": tier_num,
            "tier_name": tier["name"],
            "points_per_test": tier["points_per_test"],
            "source": source,
            "instructions": (
                "Modify the source code to make all tests pass. "
                "Replace __ with correct values, change False to True where needed, "
                "and implement any functions/classes marked with 'WRITE CODE HERE' or 'pass'. "
                "Submit the complete modified file content."
            ),
        }

    def submit(self, session_id: str, challenge_id: str, code: str, max_retries: int = 3) -> dict:
        s = self.sessions[session_id]
        current = s.current_challenge()
        if current != challenge_id:
            return {"error": f"Expected challenge '{current}', got '{challenge_id}'"}

        if challenge_id not in s.results:
            s.results[challenge_id] = ChallengeResult(challenge_id=challenge_id)
        result = s.results[challenge_id]
        result.attempts += 1

        violations = check_code(code)
        if violations:
            result.attempts -= 1
            return {"status": "blocked", "violations": violations}

        koan_path = Path(s.workspace) / "koans" / f"{challenge_id}.py"
        koan_path.write_text(code)

        start = time.time()
        passed, total, failures = self._run_tests(s.workspace, challenge_id)
        result.elapsed_seconds += time.time() - start
        result.passed = passed
        result.total = total
        result.failures = failures

        tier_num, tier = tier_for_challenge(challenge_id)

        if passed == total and total > 0:
            retry_penalty = max(0, (result.attempts - 1) * 2)
            result.score = max(1, (passed * tier["points_per_test"]) - retry_penalty)
            result.completed = True
            s.total_score = sum(r.score for r in s.results.values())
            s.current_index += 1
            self._save_sessions()
            return {
                "status": "passed",
                "passed": passed,
                "total": total,
                "score": result.score,
                "attempts": result.attempts,
                "total_score": s.total_score,
                "next": s.current_challenge(),
            }

        retries_left = max_retries - result.attempts
        self._save_sessions()
        return {
            "status": "failed",
            "passed": passed,
            "total": total,
            "failures": failures,
            "attempts": result.attempts,
            "retries_left": max(0, retries_left),
            "hint": "Fix the failing tests and resubmit." if retries_left > 0 else "Max retries reached. You can still resubmit or skip.",
        }

    def skip(self, session_id: str) -> dict:
        s = self.sessions[session_id]
        cid = s.current_challenge()
        if cid is None:
            return {"status": "completed"}
        if cid not in s.results:
            s.results[cid] = ChallengeResult(challenge_id=cid)
        s.results[cid].score = 0
        s.current_index += 1
        self._save_sessions()
        return {"skipped": cid, "next": s.current_challenge()}

    def status(self, session_id: str) -> dict:
        s = self.sessions[session_id]
        elapsed = time.time() - s.started_at
        completed = sum(1 for r in s.results.values() if r.completed)
        return {
            "session_id": s.session_id,
            "agent_name": s.agent_name,
            "model": s.model,
            "current_challenge": s.current_challenge(),
            "current_index": s.current_index,
            "total_challenges": len(CHALLENGE_ORDER),
            "completed": completed,
            "total_score": s.total_score,
            "elapsed_seconds": round(elapsed, 1),
            "results": {cid: asdict(r) for cid, r in s.results.items()},
        }

    def leaderboard(self) -> list[dict]:
        entries = []
        for s in self.sessions.values():
            completed = sum(1 for r in s.results.values() if r.completed)
            elapsed = time.time() - s.started_at
            entries.append({
                "agent_name": s.agent_name,
                "model": s.model,
                "total_score": s.total_score,
                "completed": completed,
                "total_challenges": len(CHALLENGE_ORDER),
                "elapsed_seconds": round(elapsed, 1),
            })
        entries.sort(key=lambda e: (-e["total_score"], e["elapsed_seconds"]))
        return entries

    def _run_tests(self, workspace: str, challenge_id: str) -> tuple[int, int, list[str]]:
        test_script = f"""
import sys, os, unittest, json
sys.path.insert(0, {workspace!r})
from koans.{challenge_id} import *

loader = unittest.TestLoader()
suite = loader.loadTestsFromModule(sys.modules[f'koans.{challenge_id}'])
runner = unittest.TextTestRunner(stream=open(os.devnull, 'w'), verbosity=0)
result = runner.run(suite)

failures = []
for test, traceback in result.failures + result.errors:
    failures.append(f"{{test}}: {{traceback.splitlines()[-1]}}")

total = result.testsRun
passed = total - len(result.failures) - len(result.errors)

print(json.dumps({{"passed": passed, "total": total, "failures": failures}}))
"""
        try:
            proc = subprocess.run(
                ["python3", "-c", test_script],
                capture_output=True, text=True, timeout=30,
                cwd=workspace,
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": workspace,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            output = proc.stdout.strip()
            if output:
                data = json.loads(output)
                return data["passed"], data["total"], data["failures"]
            stderr = proc.stderr.strip()
            return 0, 0, [f"Runtime error: {stderr[:500]}"]
        except subprocess.TimeoutExpired:
            return 0, 0, ["Test execution timed out (30s)"]
        except Exception as e:
            return 0, 0, [f"Test runner error: {str(e)}"]
