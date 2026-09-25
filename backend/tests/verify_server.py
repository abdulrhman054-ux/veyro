"""TEST-ONLY server for browser verification: isolated data dir, fake LLM, mock clock, live blocked.
Never used by start.bat. Output from the fake model is labelled [TEST]/[اختبار]."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("VEYRO_DATA_DIR", str(ROOT / "verification" / "data"))
os.environ["VEYRO_BLOCK_LIVE"] = "1"
os.environ["VEYRO_MOCK_CLOCK_OPEN"] = os.environ.get("VEYRO_MOCK_CLOCK_OPEN", "1")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-TESTKEY-must-never-appear-0000")
sys.path.insert(0, str(ROOT / "backend"))

import keyring  # noqa: E402
from keyring.backend import KeyringBackend  # noqa: E402


class MemKeyring(KeyringBackend):
    priority = 1
    store: dict = {}
    def get_password(self, s, u): return self.store.get((s, u))
    def set_password(self, s, u, p): self.store[(s, u)] = p
    def delete_password(self, s, u): self.store.pop((s, u), None)


keyring.set_keyring(MemKeyring())  # the verification run never touches the real Windows vault

from tests import fake_llm  # noqa: E402

fake_llm.install()

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("veyro.app:app", host="127.0.0.1", port=int(os.environ.get("VEYRO_PORT", "8766")), log_level="info")
