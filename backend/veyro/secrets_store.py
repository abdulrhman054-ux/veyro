"""API keys: Windows Credential Manager via `keyring`, never returned to the frontend.

Lookup order for LLM keys: keyring (entered in the app) -> environment / .env (development).
Broker keys are keyring-only; see execution/ (live keys are never read from .env).
"""
from __future__ import annotations

import logging
import os
import re
import threading

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from .config import KEYRING_SERVICE, PROVIDERS

log = logging.getLogger("veyro.secrets")
_lock = threading.Lock()
_known: set[str] = set()  # every secret value seen this process, for scrubbing


def _remember(value: str | None) -> str | None:
    if value and len(value) >= 8:
        _known.add(value)
    return value


def get_secret(name: str) -> str | None:
    try:
        return _remember(keyring.get_password(KEYRING_SERVICE, name))
    except KeyringError:
        log.warning("keyring unavailable while reading a secret")
        return None


def set_secret(name: str, value: str) -> None:
    with _lock:
        keyring.set_password(KEYRING_SERVICE, name, value)
        _remember(value)


def delete_secret(name: str) -> None:
    with _lock:
        try:
            keyring.delete_password(KEYRING_SERVICE, name)
        except PasswordDeleteError:
            pass


def llm_key(provider: str) -> tuple[str | None, str]:
    """(key, source) where source is 'app', 'env' or 'none'."""
    k = get_secret(f"llm:{provider}")
    if k:
        return k, "app"
    env = PROVIDERS[provider]["env"]
    if env is None:
        return "local", "local"          # e.g. Ollama: no key needed
    v = os.environ.get(env)
    if v:
        return _remember(v), "env"
    return None, "none"


def mask(value: str | None) -> str | None:
    if not value:
        return None
    head = value[:3] if not value.startswith("sk-") else "sk-"
    return f"{head}…{value[-4:]}"


_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|x-api-key|apca-api-(?:key-id|secret-key))([\"'=:\s]+)([A-Za-z0-9_\-\.]{8,})"),
    re.compile(r"\bPK[A-Z0-9]{14,}\b"),   # Alpaca key ids
]


def scrub(text: str) -> str:
    """Remove anything that looks like a secret from text bound for logs/UI."""
    if not text:
        return text
    for k in list(_known):
        text = text.replace(k, "***")
    text = _PATTERNS[0].sub("sk-***", text)
    text = _PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    text = _PATTERNS[2].sub("PK***", text)
    return text


class ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        clean = scrub(msg)
        if clean != msg:
            record.msg, record.args = clean, ()
        return True
