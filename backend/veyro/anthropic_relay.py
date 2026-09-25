"""Local relay for Anthropic keys that are not scoped to a workspace.

Such keys must send an ``anthropic-workspace-id`` header on every request. TradingAgents builds its
own Claude clients, so instead of changing the framework we point its documented ``backend_url``
setting at this relay (on 127.0.0.1 only), which adds the header and forwards to api.anthropic.com.
Nothing is logged; the API key passes straight through in the request headers.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from . import db

UPSTREAM = "https://api.anthropic.com"
router = APIRouter()
_HOP = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}


def workspace_id() -> str | None:
    return db.get_setting("anthropic_workspace_id") or None


def base_url() -> str | None:
    """The backend_url to give Claude clients: the relay when a workspace ID is set, else None (direct)."""
    if not workspace_id():
        return None
    return f"http://127.0.0.1:{os.environ.get('VEYRO_PORT', '8765')}/anthropic-relay"


@router.api_route("/anthropic-relay/{path:path}", methods=["GET", "POST"], include_in_schema=False)
async def relay(path: str, request: Request):
    if request.client is None or request.client.host not in ("127.0.0.1", "::1", "localhost"):
        return Response(status_code=403)
    if not path.startswith("v1/"):
        return Response(status_code=404)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    ws = workspace_id()
    if ws:
        headers["anthropic-workspace-id"] = ws
    body = await request.body()
    client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=20))
    req = client.build_request(request.method, f"{UPSTREAM}/{path}", params=request.query_params, headers=headers, content=body)
    try:
        resp = await client.send(req, stream=True)
    except httpx.HTTPError:
        await client.aclose()   # network down / connect timeout: don't leak the client
        return Response(status_code=502)
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _HOP | {"content-encoding"}}

    async def gen():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(gen(), status_code=resp.status_code, headers=out_headers)
