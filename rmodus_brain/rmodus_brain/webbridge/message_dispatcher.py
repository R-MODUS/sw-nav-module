"""Routes incoming websocket messages to dedicated async handlers."""

from typing import Awaitable, Callable, Dict, Optional

from fastapi import WebSocket

from rmodus_brain.webbridge.connection_manager import ConnectionManager
from rmodus_brain.webbridge.role_state import RoleState
from rmodus_brain.webbridge.ros_bridge import WebBridgeNode

Handler = Callable[[WebSocket, dict, Optional[WebBridgeNode]], Awaitable[None]]


class MessageDispatcher:
    def __init__(
        self,
        manager: ConnectionManager,
        role_state: RoleState,
        operator_pin: str,
        admin_pin: str,
        testing_mode: bool,
    ):
        self.manager = manager
        self.role_state = role_state
        self.operator_pin = operator_pin
        self.admin_pin = admin_pin
        self.testing_mode = testing_mode
        self.handlers: Dict[str, Handler] = {
            "request_operator": self.handle_request_operator,
            "request_admin": self.handle_request_admin,
            "kick_operator": self.handle_kick_operator,
            "cmd_joy": self.handle_cmd_joy,
            "set_goal_pose": self.handle_set_goal_pose,
        }

    async def dispatch(self, websocket: WebSocket, data: dict, ros_node: Optional[WebBridgeNode]):
        await self._handle_testing_autologin(websocket)
        msg_type = data.get("type")
        handler = self.handlers.get(msg_type)
        if handler:
            await handler(websocket, data, ros_node)

    async def _handle_testing_autologin(self, websocket: WebSocket):
        if not self.testing_mode:
            return
        if self.role_state.current_admin is not None:
            return
        if self.role_state.current_operator and self.role_state.current_operator != self.role_state.current_admin:
            await self.manager.set_role(self.role_state.current_operator, "spectator")
        self.role_state.current_admin = websocket
        self.role_state.current_operator = websocket
        await self.manager.set_role(websocket, "admin")

    async def handle_request_operator(self, websocket: WebSocket, data: dict, _ros_node: Optional[WebBridgeNode]):
        if data.get("pin") != self.operator_pin:
            await self.manager.send_personal_message(
                {"type": "error", "message": "Invalid PIN for Operator."}, websocket
            )
            return

        current_operator = self.role_state.current_operator
        operator_id = self.manager.get_identifier(current_operator) if current_operator else None
        if not operator_id or operator_id not in self.manager.active_connections:
            self.role_state.current_operator = websocket
            await self.manager.set_role(websocket, "operator")
        else:
            await self.manager.send_personal_message(
                {"type": "error", "message": "Operator role is already taken."}, websocket
            )

    async def handle_request_admin(self, websocket: WebSocket, data: dict, _ros_node: Optional[WebBridgeNode]):
        if data.get("pin") != self.admin_pin:
            await self.manager.send_personal_message(
                {"type": "error", "message": "Invalid PIN for Admin."}, websocket
            )
            return

        current_operator = self.role_state.current_operator
        current_admin = self.role_state.current_admin
        if current_operator and current_operator != current_admin:
            await self.manager.set_role(current_operator, "spectator")

        self.role_state.current_admin = websocket
        self.role_state.current_operator = websocket
        await self.manager.set_role(websocket, "admin")

    async def handle_kick_operator(self, websocket: WebSocket, data: dict, _ros_node: Optional[WebBridgeNode]):
        del data
        if websocket != self.role_state.current_admin:
            return

        current_operator = self.role_state.current_operator
        current_admin = self.role_state.current_admin
        if current_operator and current_operator != current_admin:
            await self.manager.set_role(current_operator, "spectator")
            self.role_state.current_operator = None

        self.role_state.current_operator = current_admin
        await self.manager.broadcast_user_list()

    async def handle_cmd_joy(self, websocket: WebSocket, data: dict, ros_node: Optional[WebBridgeNode]):
        if websocket != self.role_state.current_operator:
            await self.manager.send_personal_message(
                {"type": "info", "message": "You are not the operator."}, websocket
            )
            return

        if ros_node:
            ros_node.publish_joystick_cmd(data)

    async def handle_set_goal_pose(self, websocket: WebSocket, data: dict, ros_node: Optional[WebBridgeNode]):
        if websocket != self.role_state.current_operator:
            await self.manager.send_personal_message(
                {"type": "info", "message": "You are not the operator."}, websocket
            )
            return

        if ros_node:
            x = data.get("x", 0.0)
            y = data.get("y", 0.0)
            yaw = data.get("yaw", 0.0)
            ros_node.publish_goal_pose(float(x), float(y), float(yaw))
