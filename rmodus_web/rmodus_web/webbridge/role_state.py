"""Stores current operator/admin websocket references and disconnect cleanup logic."""

from dataclasses import dataclass
from typing import Optional

from fastapi import WebSocket


@dataclass
class RoleState:
    current_operator: Optional[WebSocket] = None
    current_admin: Optional[WebSocket] = None

    def release_on_disconnect(self, websocket: WebSocket):
        if websocket == self.current_operator:
            self.current_operator = None
        if websocket == self.current_admin:
            self.current_admin = None
            self.current_operator = None
