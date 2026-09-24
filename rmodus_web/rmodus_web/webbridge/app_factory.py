"""Builds the FastAPI app, websocket endpoint, and ROS lifecycle wiring."""

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from typing import Optional

import rclpy
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from rmodus_web.webbridge.config import INDEX_HTML, STATIC_DIR, WebConfig
from rmodus_web.webbridge.connection_manager import ConnectionManager
from rmodus_web.webbridge.message_dispatcher import MessageDispatcher
from rmodus_web.webbridge.network_api import create_network_router
from rmodus_web.webbridge.profiles_api import create_profiles_router
from rmodus_web.webbridge.role_state import RoleState
from rmodus_web.webbridge.ros_bridge import WebBridgeNode
from rmodus_web.webbridge.system_api import create_system_router


def create_app(cfg: Optional[WebConfig] = None) -> FastAPI:
    cfg = cfg or WebConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        print("Server startup: Initializing ROS... ⏳")
        manager = ConnectionManager()
        role_state = RoleState()

        if not rclpy.ok():
            rclpy.init()
        loop = asyncio.get_running_loop()
        ros_node = WebBridgeNode(loop, manager, cfg)

        ros_thread = threading.Thread(target=rclpy.spin, args=(ros_node,), daemon=True)
        ros_thread.start()

        app.state.manager = manager
        app.state.role_state = role_state
        app.state.ros_node = ros_node
        app.state.web_cfg = cfg
        app.state.dispatcher = MessageDispatcher(
            manager=manager,
            role_state=role_state,
            operator_pin=cfg.operator_pin,
            admin_pin=cfg.admin_pin,
            testing_mode=cfg.testing,
        )

        print("Server startup: ROS node running in background thread. ✅")
        try:
            yield
        finally:
            print("Server shutdown: Cleaning up ROS... ⏳")
            ros_node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
            print("Server shutdown: ROS resources released. ✅")

    app = FastAPI(lifespan=lifespan)
    app.state.web_cfg = cfg

    @app.middleware("http")
    async def disable_asset_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/static"):
            response.headers["Cache-Control"] = "no-store"
        return response
    app.include_router(create_profiles_router())
    app.include_router(create_network_router())
    app.include_router(create_system_router())
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def get_index():
        html = INDEX_HTML.read_text(encoding="utf-8")
        ui_config = json.dumps(
            {
                "nav_tabs": cfg.web_ui_nav_tabs,
                "persist_local": cfg.web_ui_persist_local,
                "configs_root": cfg.configs_root,
                "testing": cfg.testing,
                "sensor_layout": cfg.sensor_layout,
                "robot_model": cfg.robot_model,
            }
        )
        inject = f'<script>window.__RMODUS_UI_CONFIG__ = {ui_config};</script>\n    '
        marker = '<script src="static/js/app.js"></script>'
        if marker not in html:
            return FileResponse(INDEX_HTML)
        html = html.replace(marker, inject + marker, 1)
        return HTMLResponse(html)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        manager: ConnectionManager = websocket.app.state.manager
        role_state: RoleState = websocket.app.state.role_state
        dispatcher: MessageDispatcher = websocket.app.state.dispatcher
        ros_node: Optional[WebBridgeNode] = websocket.app.state.ros_node

        await manager.connect(websocket)
        await dispatcher.apply_testing_role(websocket)
        if ros_node:
            for message in ros_node.get_initial_messages():
                await manager.send_personal_message(message, websocket)
        try:
            while True:
                data = await websocket.receive_json()
                await dispatcher.dispatch(websocket, data, ros_node)
        except WebSocketDisconnect:
            role_state.release_on_disconnect(websocket)
        finally:
            await manager.disconnect(websocket)

    return app


def run_server(app: FastAPI, cfg: Optional[WebConfig] = None):
    cfg = cfg or WebConfig()
    config = uvicorn.Config(app, host=cfg.host, port=cfg.port, log_level=cfg.log_level)
    server = uvicorn.Server(config)
    server.run()
