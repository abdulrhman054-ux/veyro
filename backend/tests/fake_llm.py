"""Test-only fake chat model so the real TradingAgents graph can run without an API key.

Injected by patching the framework's client factory in tests; the framework itself
is never modified. Every output is plainly labelled [TEST] / [اختبار].
FAKE_RATING env var picks the Portfolio Manager's rating (default Hold).
"""
from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeChat(BaseChatModel):
    model_name: str = "fake-model"

    @property
    def _llm_type(self) -> str:
        return "veyro-fake"

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any):
        raise NotImplementedError

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        prompt = " ".join(str(getattr(m, "content", m)) for m in messages)
        rating = os.environ.get("FAKE_RATING", "Hold")
        arabic = "Language: Arabic" in prompt or "Language for line and reason: Arabic" in prompt
        if "Pick the ONE character" in prompt:
            text = ('{"character": "Bruno", "answer": "[اختبار] برونو يجاوب من ملاحظات الجلسة. غرر…"}' if "Language: Arabic" in prompt
                    else '{"character": "Bruno", "answer": "[TEST] Bruno answers from the session notes. grr…"}')
        elif "You are Albie" in prompt:
            text = "[اختبار] ألبي يربط الأخبار العالمية بالسهم. ريشتي تطير بالأخبار!" if "Language: Arabic" in prompt else "[TEST] Albie links world news to the stock. feathers full of news!"
        elif "JSON object" in prompt:
            text = ('{"line": "[اختبار] ليو يعلن القرار من المحاكي. زئير!", "reason": "[اختبار] سبب تجريبي", "conviction": "medium"}'
                    if arabic else
                    '{"line": "[TEST] Leo announces the fake decision. roar!", "reason": "[TEST] fake reason", "conviction": "medium"}')
        elif "spoken lines" in prompt:
            who = re.search(r"spoken lines for (\w+)", prompt)
            name = who.group(1) if who else "?"
            text = f"[اختبار] {name} يتكلم من المحاكي." if arabic else f"[TEST] {name} speaking from the fake model."
        elif "Translate this stock-research note" in prompt:
            text = "[اختبار] ترجمة تجريبية للتقرير."
        elif "As the Portfolio Manager" in prompt:
            text = f"**Rating**: {rating}\n\n**Executive Summary**: [TEST] fake output.\n\n**Investment Thesis**: [TEST] fake."
        else:
            text = "[TEST] Fake analysis output for pipeline verification. FINAL TRANSACTION PROPOSAL: **HOLD**"
        msg = AIMessage(content=text, usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                        response_metadata={"model_name": self.model_name})
        return ChatResult(generations=[ChatGeneration(message=msg)])


class FakeClient:
    def __init__(self, *a, **k):
        self.cb = k.get("callbacks")

    def get_llm(self):
        return FakeChat(callbacks=self.cb) if self.cb else FakeChat()


def install(monkeypatch=None):
    import tradingagents.graph.trading_graph as tg
    import veyro.voice as vv
    if monkeypatch:
        monkeypatch.setattr(tg, "create_llm_client", FakeClient)
        monkeypatch.setattr(vv, "create_llm_client", FakeClient)
    else:
        tg.create_llm_client = FakeClient
        vv.create_llm_client = FakeClient
