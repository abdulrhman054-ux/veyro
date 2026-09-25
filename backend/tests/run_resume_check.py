"""Stop a session midway, start the same ticker/date again: the framework must resume from its checkpoint."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["VEYRO_DATA_DIR"] = tempfile.mkdtemp(prefix="veyro-resume-")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-FAKE-not-a-real-key-000")
from tests import fake_llm  # noqa: E402
from veyro import db, runner  # noqa: E402

fake_llm.install()


async def run(stop_after=None):
    loop = asyncio.get_running_loop()
    sid = runner.start_session(loop, "MSFT", "en", demo=False, trade_date="2026-09-02")
    q, backlog = runner.BUSES[sid].subscribe()
    seen = [e for e in backlog]
    while True:
        ev = await asyncio.wait_for(q.get(), timeout=600)
        seen.append(ev)
        if stop_after and sum(1 for e in seen if e["type"] == "agent_message") >= stop_after:
            runner.cancel_session(sid)
        if ev["type"] == "end":
            break
    s = db.get_session(sid)
    return s, [e for e in seen if e["type"] == "resumed"]


async def main():
    s1, _ = await run(stop_after=3)
    print("first:", s1["status"], len(s1["turns"]), "turns")
    s2, resumed = await run()
    print("second:", s2["status"], "resumed flag:", (s2["config"] or {}).get("resumed"), "resumed event:", bool(resumed),
          "turns:", [t["character"] for t in s2["turns"]])

asyncio.run(main())
