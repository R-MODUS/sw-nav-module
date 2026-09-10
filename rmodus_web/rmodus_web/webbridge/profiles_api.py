"""REST API for profiles — proxies to rmodus_config ROS services."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from rmodus_web.webbridge.config import WebConfig


class ProfileCreateBody(BaseModel):
    name: str = Field(..., min_length=1)
    source: Optional[str] = None
    content: Optional[str] = None


class ProfileSaveBody(BaseModel):
    content: str


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


def _fail_if_needed(success: bool, message: str) -> None:
    if success:
        return
    text = (message or "rmodus_config chyba").strip()
    lower = text.lower()
    if "neexistuje" in lower or "not found" in lower or "chybí" in lower:
        raise HTTPException(status_code=404, detail=text)
    if "už existuje" in lower:
        raise HTTPException(status_code=409, detail=text)
    if "neplatn" in lower or "nelze smazat" in lower:
        raise HTTPException(status_code=400, detail=text)
    raise HTTPException(status_code=400, detail=text)


def create_profiles_router() -> APIRouter:
    router = APIRouter(prefix="/api/profiles", tags=["profiles"])

    @router.get("")
    async def list_all(request: Request) -> dict[str, Any]:
        cfg: WebConfig = request.app.state.web_cfg
        res = await _call(request, "profiles_list")
        _fail_if_needed(res.success, res.message)
        active = res.active or None
        profiles = [
            {
                "name": name,
                "active": name == active,
                "path": f"{res.profiles_dir}/{name}.yaml",
            }
            for name in list(res.names)
        ]
        return {
            "configs_root": res.configs_root or cfg.configs_root,
            "profiles_dir": res.profiles_dir,
            "active": active,
            "profiles": profiles,
            "note": "Aktivace mění ukazatel active; bringup se načte po restartu služby.",
            "testing": cfg.testing,
        }

    @router.get("/{name}")
    async def get_one(name: str, request: Request) -> dict[str, Any]:
        res = await _call(request, "profiles_get", name)
        _fail_if_needed(res.success, res.message)
        return {
            "name": res.name,
            "active": bool(res.active),
            "path": res.path,
            "content": res.content,
        }

    @router.put("/{name}")
    async def save_one(
        name: str,
        body: ProfileSaveBody,
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        res = await _call(request, "profiles_save", name, body.content)
        _fail_if_needed(res.success, res.message)
        return {"ok": True, "name": res.name, "path": res.path}

    @router.post("")
    async def create_one(
        body: ProfileCreateBody,
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        res = await _call(
            request,
            "profiles_create",
            body.name,
            body.source or "",
            body.content or "",
        )
        _fail_if_needed(res.success, res.message)
        return {"ok": True, "name": res.name, "path": res.path}

    @router.delete("/{name}")
    async def delete_one(
        name: str,
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        res = await _call(request, "profiles_delete", name)
        _fail_if_needed(res.success, res.message)
        return {"ok": True, "name": res.name}

    @router.post("/{name}/activate")
    async def activate_one(
        name: str,
        request: Request,
        x_admin_pin: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        _require_write_access(request, x_admin_pin)
        res = await _call(request, "profiles_activate", name)
        _fail_if_needed(res.success, res.message)
        return {
            "ok": True,
            "active": res.active,
            "path": res.path,
            "restart_required": True,
            "message": res.message
            or "Profil je aktivní na disku. Restartuj rmodus.service, aby se načetl.",
        }

    return router
