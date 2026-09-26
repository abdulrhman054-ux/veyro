"""Static configuration: paths, characters, providers, models and pricing."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("VEYRO_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "veyro.db"
STATIC_DIR = ROOT / "frontend" / "dist"
TA_HOME = DATA_DIR / "tradingagents"  # framework logs/cache/memory live under our data dir

KEYRING_SERVICE = "Veyro"

# ---------------------------------------------------------------- characters
# Framework graph node -> character. Every framework agent maps to exactly one
# character; the risk debaters share Tank's voice, the three decision nodes share Leo's.
NODE_CHARACTER = {
    "Market Analyst": "Ollie",
    "Sentiment Analyst": "Buzz",
    "News Analyst": "Pip",
    "Fundamentals Analyst": "Benny",
    "Bull Researcher": "Bolt",
    "Bear Researcher": "Bruno",
    "Research Manager": "Leo",
    "Trader": "Leo",
    "Aggressive Analyst": "Tank",
    "Conservative Analyst": "Tank",
    "Neutral Analyst": "Tank",
    "Portfolio Manager": "Leo",
    "tools_market": "Ollie",
    "tools_news": "Pip",
    "tools_fundamentals": "Benny",
}
RISK_NODES = ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst")

CHARACTERS = {
    "Ollie": {"animal": "owl", "role": "Technical / Market Analyst", "catch_en": "hoot!", "catch_ar": "هوو هوو!",
              "persona": "a wise, calm owl with blue glasses who loves charts and patience"},
    "Pip": {"animal": "scarlet macaw", "role": "News Analyst for this stock (company and sector news)", "catch_en": "squawk!", "catch_ar": "سكوااك!",
            "persona": "an excitable parrot who reads every headline and loves breaking news"},
    "Buzz": {"animal": "bee", "role": "Social / Sentiment Analyst", "catch_en": "bzzz!", "catch_ar": "بززز!",
             "persona": "a bubbly, fast-talking bee who hears everything the crowd is buzzing about"},
    "Benny": {"animal": "beaver", "role": "Fundamentals Analyst", "catch_en": "chomp!", "catch_ar": "قرمش!",
              "persona": "a diligent beaver accountant who builds conclusions log by log from the numbers"},
    "Bolt": {"animal": "bull", "role": "Bull Researcher", "catch_en": "moo-ve!", "catch_ar": "مووو!",
             "persona": "an energetic, optimistic bull who argues the upside case"},
    "Bruno": {"animal": "brown bear", "role": "Bear Researcher", "catch_en": "grr…", "catch_ar": "غرر…",
              "persona": "a grumpy but fair bear who argues the downside case"},
    "Tank": {"animal": "turtle", "role": "Risk Team (aggressive, conservative and neutral risk analysts)",
             "catch_en": "slow and steady.", "catch_ar": "على مهلك… بثبات.",
             "persona": "a careful turtle in a hard hat who summarises the risk team's debate"},
    "Leo": {"animal": "lion", "role": "Decision maker (Research Manager, Trader and Portfolio Manager)",
            "catch_en": "roar!", "catch_ar": "زئير!",
            "persona": "a warm, confident lion chairman who weighs everyone and announces decisions"},
}

# How each character talks, per language. Used by the voice layer so every line
# (live speech, verdict, lines re-voiced after a language switch) stays in character.
STYLE = {
    "Ollie": {
        "ar": "هادئ وحكيم ويتكلم بتأنٍّ مثل معلّم طيب. يحب يقول «خلوني أوضح لكم» و«بهدوء»، ويشبّه الأشياء بالنظر من فوق الغصن.",
        "en": "Calm, wise, unhurried, like a kind teacher. Likes 'let me walk you through it' and 'from up on my branch' imagery.",
    },
    "Pip": {
        "ar": "متحمس وسريع ويكرر الكلمة مرتين من الحماس مثل «خبر خبر!» أو «اسمعوا اسمعوا!»، جمل قصيرة وتعجب كثير.",
        "en": "Excitable and fast, repeats words from excitement ('Breaking news, breaking news!', 'Listen, listen!'), short punchy sentences.",
    },
    "Buzz": {
        "ar": "مرح وخفيف دم ويتكلم عن «الكل يسولف» و«الجو العام»، يمط الزاي أحياناً مثل «زززين»، حيوي ويحب الناس.",
        "en": "Bubbly and playful, talks about what 'everyone's buzzing about', stretches z-sounds ('sooo buzzzy'), people-loving.",
    },
    "Benny": {
        "ar": "دقيق ومرتّب مثل محاسب، يقول «خلوني أحسبها حبة حبة» ويشبّه التحليل ببناء السد جذع جذع.",
        "en": "Meticulous and tidy like an accountant, says 'let me tally this up' and compares analysis to building a dam log by log.",
    },
    "Bolt": {
        "ar": "حماسي وواثق ويشجع الفريق «يلا يا شباب!» «ننطلق!»، طاقته عالية ويحب الاندفاع للأمام.",
        "en": "Energetic and confident, rallies the team ('Come on, team!', 'Let's charge!'), high-energy, always pushing forward.",
    },
    "Bruno": {
        "ar": "متشكك وخشن شوي بس عادل، يقول «هدّوا اللعب» و«لا تستعجلون»، جمله قصيرة وثقيلة ويتذمر بلطف.",
        "en": "Skeptical and a bit gruff but fair, says 'hold your horses' and 'not so fast', short heavy sentences, grumbles kindly.",
    },
    "Tank": {
        "ar": "بطيء ومطمئن ويحب السلامة أول، يقول «خطوة خطوة» و«على مهلنا»، يتكلم كأنه يلبس خوذة السلامة.",
        "en": "Slow, reassuring, safety-first, says 'one step at a time' and 'easy does it', talks like someone wearing a safety helmet.",
    },
    "Leo": {
        "ar": "رئيس المجلس، دافئ وواثق وحاسم، يبدأ بـ«يا جماعة، سمعتكم كلكم» ويتكلم بهيبة لطيفة.",
        "en": "The council chair: warm, regal and decisive, opens with 'Friends, I've heard you all' and speaks with gentle authority.",
    },
}

# ---------------------------------------------------------------- batch sizes
# How many stocks one watchlist / scan / morning report may analyse. Each stock is a full paid
# session run one after another, so the UI always shows the cost estimate multiplied by the count.
MAX_BATCH = 50
MAX_SCREEN = 25

# ---------------------------------------------------------------- providers & models
PROVIDERS = {
    # Every current Claude model is offered for both roles, so the owner can run any of them.
    # The Settings screen can also load the exact list the saved key has access to (GET /v1/models).
    "anthropic": {"label": "Claude", "env": "ANTHROPIC_API_KEY",
                  "quick": ["claude-sonnet-5", "claude-haiku-4-5", "claude-opus-5-5", "claude-fable-5-1", "claude-opus-5",
                            "claude-fable-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6"],
                  "deep": ["claude-opus-5-5", "claude-fable-5-1", "claude-opus-5", "claude-sonnet-5", "claude-fable-5",
                           "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
                  "default_quick": "claude-sonnet-5", "default_deep": "claude-opus-5-5"},
    "openai": {"label": "OpenAI", "env": "OPENAI_API_KEY",
               "quick": ["gpt-6-luna", "gpt-5.6-luna", "gpt-5.6-terra"],
               "deep": ["gpt-6-sol", "gpt-6-astra", "gpt-5.6"],
               "default_quick": "gpt-6-luna", "default_deep": "gpt-6-sol"},
    "deepseek": {"label": "DeepSeek", "env": "DEEPSEEK_API_KEY",
                 "quick": ["deepseek-flash"],
                 "deep": ["deepseek-v4-pro", "deepseek-flash"],
                 "default_quick": "deepseek-flash", "default_deep": "deepseek-v4-pro"},
}

# Extra framework providers offered under Advanced settings (model lists read from the framework catalog).
EXTRA_PROVIDERS = {
    "google": {"label": "Google Gemini", "env": "GOOGLE_API_KEY"},
    "xai": {"label": "xAI Grok", "env": "XAI_API_KEY"},
    "mistral": {"label": "Mistral", "env": "MISTRAL_API_KEY", "base": "https://api.mistral.ai/v1"},
    "qwen": {"label": "Qwen (Alibaba)", "env": "DASHSCOPE_API_KEY", "base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"},
    "glm": {"label": "GLM (Zhipu)", "env": "ZHIPU_API_KEY", "base": "https://api.z.ai/api/paas/v4/"},
    "kimi": {"label": "Kimi (Moonshot)", "env": "MOONSHOT_API_KEY", "base": "https://api.moonshot.ai/v1"},
    "minimax": {"label": "MiniMax", "env": "MINIMAX_API_KEY", "base": "https://api.minimax.io/v1"},
    "openrouter": {"label": "OpenRouter (many models)", "env": "OPENROUTER_API_KEY", "base": "https://openrouter.ai/api/v1"},
    "groq": {"label": "Groq", "env": "GROQ_API_KEY", "base": "https://api.groq.com/openai/v1"},
    "ollama": {"label": "Ollama (local, free)", "env": None},
}

# OpenAI-compatible endpoints used to list the models an account can use (Settings → "load my models").
LIST_BASE = {"openai": "https://api.openai.com/v1", "deepseek": "https://api.deepseek.com", "xai": "https://api.x.ai/v1",
             **{k: v["base"] for k, v in EXTRA_PROVIDERS.items() if v.get("base")}}

# The model we suggest per provider and why (shown in Settings with a "use recommended" button).
# Claude: Sonnet 5 runs the many analyst/debate/voice calls at a good price; Opus 5.5 makes the final
# decisions with frontier reasoning at a lower price than Fable 5.1. Others: the framework's own first choice.
RECOMMEND = {
    "anthropic": {"quick": "claude-sonnet-5", "deep": "claude-opus-5-5",
                  "why_ar": "Sonnet 5 للمحللين والنقاش (أفضل توازن سرعة وجودة وسعر)، وOpus 5.5 لقرار ليو (تفكير عميق بسعر أقل من Fable). للأرخص: Haiku 4.5 سريع. لأعلى جودة: Fable 5.1 عميق (أغلى بكثير).",
                  "why_en": "Sonnet 5 for analysts and debate (best balance of speed, quality and price) and Opus 5.5 for Leo's decision (deep reasoning, cheaper than Fable). Cheapest: Haiku 4.5 as quick. Maximum quality: Fable 5.1 as deep (much pricier)."},
}


def _catalog_models():
    try:
        from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
    except Exception:  # noqa: BLE001
        return
    for pid, meta in {**PROVIDERS, **EXTRA_PROVIDERS}.items():
        opts = MODEL_OPTIONS.get(pid)
        if not opts:
            continue
        quick = [v for _, v in opts.get("quick", []) if v != "custom"]
        deep = [v for _, v in opts.get("deep", []) if v != "custom"]
        if pid in EXTRA_PROVIDERS:
            # Some providers (OpenRouter, Groq) have no fixed list: the owner loads their models or types an ID.
            PROVIDERS[pid] = {**meta, "quick": quick, "deep": deep, "default_quick": quick[0] if quick else None,
                              "default_deep": deep[0] if deep else None, "extra": True}
        else:
            # keep our curated order, add anything else the framework lists
            PROVIDERS[pid]["quick"] = list(dict.fromkeys(PROVIDERS[pid]["quick"] + quick))
            PROVIDERS[pid]["deep"] = list(dict.fromkeys(PROVIDERS[pid]["deep"] + deep))


_catalog_models()
for _pid, _meta in EXTRA_PROVIDERS.items():   # providers missing from this framework version's catalog
    PROVIDERS.setdefault(_pid, {**_meta, "quick": [], "deep": [], "default_quick": None, "default_deep": None, "extra": True})
for _pid, _p in PROVIDERS.items():
    RECOMMEND.setdefault(_pid, {"quick": _p["default_quick"], "deep": _p["default_deep"],
                                "why_ar": "اختيار إطار TradingAgents الافتراضي لهذا المزوّد.",
                                "why_en": "TradingAgents' own default choice for this provider."})

# USD per 1M tokens (input, output). Anthropic first-party list prices, verified
# 2026-09 from the Claude API reference. Other providers: no verified price -> the
# UI shows token counts and says the price is unknown instead of guessing.
PRICING = {
    "claude-fable-5-1": (10.00, 50.00),
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Rough token envelope for one default session (4 analysts, 1 debate round, 1 risk round),
# used only for the pre-session estimate range. (low, high) per bucket.
ESTIMATE_TOKENS = {
    "quick_in": (110_000, 320_000),
    "quick_out": (12_000, 36_000),
    "deep_in": (25_000, 70_000),
    "deep_out": (3_000, 12_000),
    "voice_in": (20_000, 45_000),   # voice layer runs on the quick model
    "voice_out": (2_000, 5_000),
}
