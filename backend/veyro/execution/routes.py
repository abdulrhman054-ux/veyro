"""HTTP routes for optional execution. Every mutating route requires a same-origin request
from the Veyro page itself (blocks other local pages / sites from driving the API)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import service as S
from .broker import BrokerError

router = APIRouter(prefix="/api/exec")
_PORT = os.environ.get("VEYRO_PORT", "8765")
ALLOWED_ORIGINS = {f"http://127.0.0.1:{_PORT}", f"http://localhost:{_PORT}", "http://127.0.0.1:5173", "http://localhost:5173"}


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        raise HTTPException(403, "origin")


def err(e: S.ExecError) -> JSONResponse:
    # An expected business-rule refusal (a limit, a closed market, a locked mode) is a normal
    # answer, not a transport failure: 200 with ok=false, so the browser console stays clean.
    return JSONResponse({"ok": False, "code": e.code, "character": e.character, "data": e.data}, status_code=200)


def wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except S.ExecError as e:
        return err(e)
    except BrokerError as e:
        # The broker (or the Mock's price feed) couldn't answer: an expected, explainable refusal, not a crash.
        return JSONResponse({"ok": False, "code": getattr(e, "code", None) or "broker", "character": "Tank", "data": {}}, status_code=200)


@router.get("/status")
def status():
    return S.status()


class ModeIn(BaseModel):
    mode: str
    phrase: str | None = None


@router.post("/mode", dependencies=[Depends(same_origin)])
def set_mode(body: ModeIn):
    return wrap(S.set_mode, body.mode, body.phrase)


class KeysIn(BaseModel):
    mode: str
    key_id: str = Field(max_length=100)
    secret: str = Field(max_length=200)


@router.post("/keys", dependencies=[Depends(same_origin)])
def save_keys(body: KeysIn):
    return wrap(S.save_keys, body.mode, body.key_id, body.secret)


@router.delete("/keys/{mode}", dependencies=[Depends(same_origin)])
def delete_keys(mode: str):
    if mode not in ("paper", "live"):
        raise HTTPException(400, "bad_mode")
    return wrap(S.delete_keys, mode)


class LimitsIn(BaseModel):
    mode: str
    max_order_usd: float
    max_symbol_exposure_usd: float
    daily_loss_limit_usd: float
    max_orders_per_day: int


@router.post("/limits", dependencies=[Depends(same_origin)])
def set_limits(body: LimitsIn):
    d = body.model_dump()
    return wrap(S.set_limits, d.pop("mode"), d)


class TicketIn(BaseModel):
    symbol: str
    side: str
    order_type: str
    amount_usd: float | None = None
    qty: float | None = None
    limit_price: float | None = None
    session_id: str | None = None


@router.post("/tickets", dependencies=[Depends(same_origin)])
def propose(body: TicketIn):
    return wrap(S.propose, **body.model_dump())


class ConfirmIn(BaseModel):
    token: str
    confirm: bool  # must be literally true: an explicit user confirmation


@router.post("/tickets/{ticket_id}/confirm", dependencies=[Depends(same_origin)])
def confirm(ticket_id: str, body: ConfirmIn):
    if body.confirm is not True:
        raise HTTPException(400, "not_confirmed")
    return wrap(S.confirm, ticket_id, body.token)


@router.get("/orders")
def orders():
    return wrap(S.sync)


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(same_origin)])
def cancel(order_id: str):
    return wrap(S.cancel, order_id)


@router.post("/kill", dependencies=[Depends(same_origin)])
def kill():
    return wrap(S.kill)


class PhraseIn(BaseModel):
    phrase: str


@router.post("/liquidate", dependencies=[Depends(same_origin)])
def liquidate(body: PhraseIn):
    return wrap(S.liquidate, body.phrase)


@router.get("/portfolio")
def portfolio():
    return S.portfolio()


@router.get("/audit")
def audit():
    return {"rows": S.audit_rows()}


@router.get("/audit.csv")
def audit_csv():
    return Response(S.audit_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="veyro-orders-audit.csv"'})


@router.get("/acted")
def acted():
    return S.acted_sessions()
