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

from rmodus_web.webbridge.config import (
    ADMIN_PIN,
    HOST,
    INDEX_HTML,
    LOG_LEVEL,
    OPERATOR_PIN,
    PORT,
    STATIC_DIR,
    TESTING,
    WEB_UI_NAV_TABS,
)
from rmodus_web.webbridge.connection_manager import ConnectionManager
from rmodus_web.webbridge.message_dispatcher import MessageDispatcher
from rmodus_web.webbridge.role_state import RoleState
from rmodus_web.webbridge.ros_bridge import WebBridgeNode


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Server startup: Initializing ROS... ⏳")
    manager = ConnectionManager()
    role_state = RoleState()

    rclpy.init()
    loop = asyncio.get_running_loop()
    ros_node = WebBridgeNode(loop, manager)

    ros_thread = threading.Thread(target=rclpy.spin, args=(ros_node,), daemon=True)
    ros_thread.start()

    app.state.manager = manager
    app.state.role_state = role_state
    app.state.ros_node = ros_node
    app.state.dispatcher = MessageDispatcher(
        manager=manager,
        role_state=role_state,
        operator_pin=OPERATOR_PIN,
        admin_pin=ADMIN_PIN,
        testing_mode=TESTING,
    )

    print("Server startup: ROS node running in background thread. ✅")
    try:
        yield
    finally:
        print("Server shutdown: Cleaning up ROS... ⏳")
        ros_node.destroy_node()
        rclpy.shutdown()
        print("Server shutdown: ROS resources released. ✅")


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def get_index():
        html = INDEX_HTML.read_text(encoding="utf-8")
        ui_config = json.dumps({"nav_tabs": WEB_UI_NAV_TABS})
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


def run_server(app: FastAPI):
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level=LOG_LEVEL)
    server = uvicorn.Server(config)
    server.run()
