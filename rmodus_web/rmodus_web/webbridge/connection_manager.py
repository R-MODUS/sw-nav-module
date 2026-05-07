"""Tracks websocket clients, their roles, and user-list broadcasts."""

from typing import Dict, Optional

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.roles: Dict[str, str] = {}

    def get_identifier(self, websocket: WebSocket) -> str:
        client = websocket.client
        if client is None:
            return f"unknown:{id(websocket)}"
        return f"{client.host}:{client.port}"

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        identifier = self.get_identifier(websocket)
        self.active_connections[identifier] = websocket
        self.roles[identifier] = "spectator"
        print(f"New connection from {identifier}. Total clients: {len(self.active_connections)}")
        await self.broadcast_user_list()

    async def disconnect(self, websocket: WebSocket):
        identifier = self.get_identifier(websocket)
        if identifier in self.active_connections:
            del self.active_connections[identifier]
            del self.roles[identifier]
            print(f"Connection from {identifier} closed. Total clients: {len(self.active_connections)}")
            await self.broadcast_user_list()

    def get_role(self, websocket: WebSocket) -> Optional[str]:
        identifier = self.get_identifier(websocket)
        return self.roles.get(identifier)

    async def set_role(self, websocket: WebSocket, role: str):
        identifier = self.get_identifier(websocket)
        if identifier in self.active_connections:
            self.roles[identifier] = role
            await self.send_personal_message({"type": "role_update", "role": role}, websocket)
            await self.broadcast_user_list()

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)

    async def broadcast(self, message: dict):
        connections = list(self.active_connections.values())
        for connection in connections:
            await self.send_personal_message(message, connection)

    async def broadcast_user_list(self):
        user_list = [
            {"id": identifier, "role": self.roles.get(identifier, "spectator")}
            for identifier in self.active_connections.keys()
        ]
        await self.broadcast({"type": "user_list_update", "users": user_list})
