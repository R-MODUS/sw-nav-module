"""REST: network.yaml via rmodus_config services (passwords never returned)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from rmodus_web.webbridge.config import WebConfig


class NetworkSaveBody(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    apply: bool = False


def _require_write_access(request: Request, x_admin_pin: Optional[str]) -> None:
    cfg: WebConfig = request.app.state.web_cfg
    if cfg.testing:
        return
    pin = (x_admin_pin or "").strip()
    if pin and pin == cfg.admin_pin:
        return
    raise HTTPException(status_code=401, detail="vyžadován admin PIN (hlavička X-Admin-Pin)")


def _ros(request: Request):
    node = getattr(request.app.state, "ros_node", None)
    if node is None:
        raise HTTPException(status_code=503, detail="ROS node ještě neběží")
    return node


async def _call(request: Request, method_name: str, *args):
    node = _ros(request)
    method = getattr(node, method_name)
    try:
        return await asyncio.to_thread(method, *args)
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def create_network_router() -> APIRouter:
    router = APIRouter(prefix="/api/network", tags=["network"])

    @router.get("")
    async def get_network(request: Request) -> dict[str, Any]:
        res = await _call(request, "network_get")
        if not res.success:
            raise HTTPException(status_code=400, detail=res.message or "nelze načíst network.yaml")
        try:
            config = json.loads(res.config_json or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"neplatný JSON z rmodus_config: {exc}") from exc
        return {
            "path": res.path,
            "config": config,
            "note": "Hesla se do UI neposílají (password_set). Prázdné heslo při uložení = beze změny.",
        }

    @router.put("")
    async def put_network(
        body: NetworkSaveBody,
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        res = await _call(
            request,
            "network_set",
            json.dumps(body.config, ensure_ascii=False),
            bool(body.apply),
        )
        if not res.success:
            raise HTTPException(status_code=400, detail=res.message or "uložení selhalo")
        return {
            "ok": True,
            "path": res.path,
            "applied": bool(res.applied),
            "message": res.message,
        }

    @router.post("/apply")
    async def apply_network(
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        res = await _call(request, "network_apply")
        if not res.success:
            raise HTTPException(status_code=500, detail=res.message or "apply selhal")
        return {"ok": True, "message": res.message}

    return router
