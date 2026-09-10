"""REST: system actions (restart rmodus.service / reboot host via rmodus_config)."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from rmodus_web.webbridge.config import WebConfig


def _require_write_access(request: Request, x_admin_pin: Optional[str]) -> None:
    cfg: WebConfig = request.app.state.web_cfg
    if cfg.testing:
        return
    pin = (x_admin_pin or "").strip()
    if pin and pin == cfg.admin_pin:
        return
    raise HTTPException(status_code=401, detail="vyžadován admin PIN (hlavička X-Admin-Pin)")


def create_system_router() -> APIRouter:
    router = APIRouter(prefix="/api/system", tags=["system"])

    @router.post("/restart")
    async def restart_rmodus(
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        node = getattr(request.app.state, "ros_node", None)
        if node is None:
            raise HTTPException(status_code=503, detail="ROS node ještě neběží")
        try:
            res = await asyncio.to_thread(node.system_restart_rmodus)
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if not res.success:
            raise HTTPException(status_code=500, detail=res.message or "restart selhal")
        return {
            "ok": True,
            "message": res.message
            or "Restart naplánován — web se krátce odpojí a znovu připojí.",
        }

    @router.post("/reboot")
    async def reboot_host(
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        node = getattr(request.app.state, "ros_node", None)
        if node is None:
            raise HTTPException(status_code=503, detail="ROS node ještě neběží")
        try:
            res = await asyncio.to_thread(node.system_reboot_host)
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if not res.success:
            raise HTTPException(status_code=500, detail=res.message or "reboot selhal")
        return {
            "ok": True,
            "message": res.message
            or "Reboot zařízení naplánován — spojení se přeruší.",
        }

    return router
