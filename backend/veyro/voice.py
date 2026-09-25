"""The voice layer: rewrites each agent's English conclusion as a short in-character line.

Runs on the session's quick model through TradingAgents' own client factory so every
provider the framework supports works the same way.
"""
from __future__ import annotations

import json
import re
from typing import Any

from tradingagents.llm_clients import create_llm_client

from .config import CHARACTERS, STYLE

MAX_SOURCE = 9000

LANG_RULES = {
    "ar": ("Arabic. Write friendly, casual, Saudi-leaning Arabic the way a warm Saudi colleague talks "
           "(light Najdi/Hijazi flavour, e.g. «مرة»، «شوي»، «يعني»، «ترى»), natural and human, never stiff or "
           "machine-translated. Use Arabic words only; the only Latin text allowed is the ticker symbol. "
           "Write numbers with Western digits exactly as they appear in the source."),
    "en": "English. Warm, playful, plain English a non-expert enjoys reading.",
}


def _text(msg: Any) -> str:
    c = getattr(msg, "content", msg)
    if isinstance(c, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c).strip()
    return str(c).strip()


def clean_line(text: str) -> str:
    """Spoken lines are plain text in a dialogue box: drop markdown, labels and wrapping quotes a model may add."""
    t = text.strip()
    t = re.sub(r"^```\w*\s*|\s*```$", "", t)
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)                 # headings
    t = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), t)
    t = re.sub(r"(?<!\w)\*(\S.*?)\*(?!\w)", r"\1", t)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)               # bullets
    t = re.sub(r"^\s*(?:line|الجملة|السطر)\s*[:：]\s*", "", t, flags=re.I)
    t = re.sub(r"\s*\n\s*", " ", t).strip()
    if len(t) >= 2 and t[0] in "\"'«“" and t[-1] in "\"'»”":
        t = t[1:-1].strip()
    return t


class Voice:
    def __init__(self, provider: str, model: str, callbacks: list | None = None):
        kwargs: dict[str, Any] = {}
        if callbacks:
            kwargs["callbacks"] = callbacks
        base = None
        if provider == "anthropic":
            from .anthropic_relay import base_url
            base = base_url()   # workspace-less keys go through the local relay that adds the workspace header
        self.llm = create_llm_client(provider=provider, model=model, base_url=base, **kwargs).get_llm()

    def _ask(self, system: str, user: str) -> str:
        return _text(self.llm.invoke([("system", system), ("human", user)]))

    def speak(self, character: str, ticker: str, source: str, lang: str, context: str = "") -> str:
        ch = CHARACTERS[character]
        catch = ch["catch_ar"] if lang == "ar" else ch["catch_en"]
        system = (
            f"You write the spoken lines for {character}, {ch['persona']}, in a cosy pixel-art office game "
            f"where animal colleagues research a stock together. {character}'s job: {ch['role']}.\n\n"
            "Rewrite the agent's conclusion below as ONE to THREE short spoken sentences.\n"
            "Hard rules:\n"
            "- Preserve the substance exactly: same direction, same main reasons, same risks and caveats.\n"
            "- Add nothing that is not in the source: no new facts, numbers, dates, names or predictions.\n"
            "- Never soften, hide or drop a risk the source stresses. Dropping minor detail is fine; changing meaning is not.\n"
            "- Numbers only if they appear in the source, copied exactly.\n"
            "- If the source says data was missing or unavailable, say so plainly.\n"
            f"- Language: {LANG_RULES[lang]} Write ONLY in this language.\n"
            f"- Speak exactly like {character}: {STYLE[character][lang]}\n"
            f"- Personality shows in voice and word choice only, never in the facts. End with the catchphrase: {catch}\n"
            "Output only the spoken line, no quotes, no labels, no markdown."
        )
        user = (f"Ticker: {ticker}\n" + (f"Where this line sits in the conversation:\n{context}\n\n" if context else "")
                + f"The agent's conclusion (English):\n{source[:MAX_SOURCE]}")
        return clean_line(self._ask(system, user))

    def verdict(self, ticker: str, rating: str, decision: str, lang: str) -> dict:
        ch = CHARACTERS["Leo"]
        catch = ch["catch_ar"] if lang == "ar" else ch["catch_en"]
        system = (
            f"You are the voice of Leo, {ch['persona']}, announcing the Portfolio Manager's final decision in a cosy "
            "pixel-art office game. Read the decision and return ONLY a JSON object with these keys:\n"
            f'  "line": 1-2 short spoken sentences announcing the call, ending with "{catch}"\n'
            '  "reason": one short line (max ~18 words) giving the main reason stated in the decision\n'
            '  "conviction": how strongly the decision text itself states its conviction: "low", "medium", "high", '
            'or "unstated" if the text does not make it clear. Judge only from the text; do not guess.\n'
            "Rules: preserve the decision exactly (the rating is fixed: "
            f"{rating}); add no facts or numbers that are not in the text; keep risks. "
            f"Language for line and reason: {LANG_RULES[lang]} Write ONLY in this language. "
            f"Leo's way of speaking: {STYLE['Leo'][lang]}"
        )
        raw = self._ask(system, f"Ticker: {ticker}\nRating: {rating}\n\nDecision:\n{decision[:MAX_SOURCE]}")
        m = re.search(r"\{.*\}", raw, re.S)
        data: dict = {}
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = {}
        if not data:
            # Not valid JSON: recover the fields individually rather than showing raw JSON in the dialogue box.
            for k in ("line", "reason", "conviction"):
                mk = re.search(rf'"{k}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
                if mk:
                    data[k] = mk.group(1).encode().decode("unicode_escape") if "\\u" in mk.group(1) else mk.group(1)
        conv = str(data.get("conviction", "unstated")).lower()
        return {
            "line": clean_line(str(data.get("line") or re.sub(r"[{}]", "", raw))),
            "reason": clean_line(str(data.get("reason") or "")),
            "conviction": conv if conv in ("low", "medium", "high") else "unstated",
        }

    def translate_detail(self, text: str) -> str:
        system = (
            "Translate this stock-research note into clear, friendly Modern Standard Arabic that a non-expert "
            "Saudi reader understands easily. Translate faithfully: keep every number, ticker, date and caveat "
            "exactly; add nothing; keep the markdown structure (headings, bullets, tables). Output only the translation."
        )
        return self._ask(system, text)
