"""Run one full session through the real TradingAgents graph with the fake LLM and print events."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["VEYRO_DATA_DIR"] = tempfile.mkdtemp(prefix="veyro-test-")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-FAKE-not-a-real-key-000")

from tests import fake_llm  # noqa: E402
from veyro import db, runner  # noqa: E402

fake_llm.install()


async def main():
    loop = asyncio.get_running_loop()
    date = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--date=")), None)
    sid = runner.start_session(loop, sys.argv[1] if len(sys.argv) > 1 else "NVDA", "ar", demo="--demo" in sys.argv, trade_date=date)
    q, backlog = runner.BUSES[sid].subscribe()
    for ev in backlog:
        show(ev)
    while True:
        ev = await asyncio.wait_for(q.get(), timeout=600)
        show(ev)
        if ev["type"] == "end":
            break
    s = db.get_session(sid)
    print("DB status:", s["status"], "rating:", s["rating"], "turns:", [(t["character"], t["node"]) for t in s["turns"]])
    print("price_at_verdict:", s["price_at_verdict"], "spy:", s["spy_at_verdict"], "cost:", s["cost_usd"])
    print("config:", {k: s["config"].get(k) for k in ("trade_date", "past_date", "resumed", "export_dir")})


def show(ev):
    e = dict(ev)
    e.pop("ts", None)
    if e["type"] == "market":
        e["data"] = f"{len(e['data']['closes'])} closes" if e.get("data") else None
    print(json.dumps(e, ensure_ascii=False)[:220])


asyncio.run(main())
