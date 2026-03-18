import asyncio
import json
import random
import logging
from pathlib import Path
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# --- Konfigurace ---
logging.basicConfig(level=logging.INFO)
HERE = Path(__file__).parent
STATIC_DIR = HERE / "static"
PORT = 8080
OPERATOR_PIN = "1234"
ADMIN_PIN = "007007"

# --- FastAPI Aplikace ---
app = FastAPI()

# --- Správce stavu ---
class StateManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.roles: Dict[str, str] = {}
        # Počáteční seznam "falešných" uživatelů
        self.user_list: Dict[str, str] = {
            "192.168.1.10:54321": "spectator",
            "192.168.1.15:12345": "spectator",
        }
        self.current_operator_id: Optional[str] = None
        self.current_admin_id: Optional[str] = None

    def get_id(self, websocket: WebSocket) -> str:
        return f"{websocket.client.host}:{websocket.client.port}"

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        client_id = self.get_id(websocket)
        self.connections[client_id] = websocket
        self.user_list[client_id] = "spectator"
        self.roles[client_id] = "spectator"
        logging.info(f"Klient {client_id} připojen jako 'spectator'.")
        await self.send_personal(client_id, {"type": "role_update", "role": "spectator"})
        await self.broadcast_user_list()

    async def disconnect(self, client_id: str):
        if client_id in self.connections:
            del self.connections[client_id]
        if client_id in self.user_list:
            del self.user_list[client_id]
        if client_id in self.roles:
            del self.roles[client_id]

        if client_id == self.current_operator_id:
            self.current_operator_id = None
            logging.info("Operátor se odpojil, role je volná.")
        if client_id == self.current_admin_id:
            self.current_admin_id = None
            self.current_operator_id = None
            logging.info("Admin se odpojil.")
        
        logging.info(f"Klient {client_id} odpojen.")
        await self.broadcast_user_list()

    async def set_role(self, client_id: str, role: str):
        if client_id not in self.connections:
            return
        self.roles[client_id] = role
        self.user_list[client_id] = role
        logging.info(f"Role pro {client_id} nastavena na '{role}'.")
        await self.send_personal(client_id, {"type": "role_update", "role": role})
        await self.broadcast_user_list()

    async def broadcast_user_list(self):
        if not self.connections: return
        users = [{"id": uid, "role": r} for uid, r in self.user_list.items()]
        logging.info(f"Odesílám seznam uživatelů: {users}")
        await self.broadcast({"type": "user_list_update", "users": users})

    async def send_personal(self, client_id: str, message: dict):
        websocket = self.connections.get(client_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logging.warning(f"Nepodařilo se odeslat zprávu klientovi {client_id}: {e}. Odpojuji.")
                await self.disconnect(client_id)
    
    async def broadcast(self, message: dict):
        # Iterujeme přes kopii klíčů, protože disconnect může měnit slovník
        for client_id in list(self.connections.keys()):
            await self.send_personal(client_id, message)

manager = StateManager()

# --- Endpoints ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def get_index():
    return FileResponse(HERE / "index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = manager.get_id(websocket)
    try:
        await manager.connect(websocket)
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            logging.info(f"Přijata zpráva typu '{msg_type}' od {client_id}")

            if msg_type == "request_operator":
                if data.get("pin") == OPERATOR_PIN:
                    if manager.current_operator_id is None or manager.current_operator_id not in manager.connections:
                        manager.current_operator_id = client_id
                        await manager.set_role(client_id, "operator")
                    else:
                        await manager.send_personal(client_id, {"type": "error", "message": "Role operátora je již obsazena."})
                else:
                    await manager.send_personal(client_id, {"type": "error", "message": "Neplatný PIN."})
            
            elif msg_type == "request_admin":
                if data.get("pin") == ADMIN_PIN:
                    if manager.current_operator_id and manager.current_operator_id != manager.current_admin_id:
                        await manager.set_role(manager.current_operator_id, "spectator")
                    
                    manager.current_admin_id = client_id
                    manager.current_operator_id = client_id
                    await manager.set_role(client_id, "admin")
                else:
                    await manager.send_personal(client_id, {"type": "error", "message": "Neplatný PIN."})

            elif msg_type == "kick_operator":
                if manager.roles.get(client_id) == "admin":
                    if manager.current_operator_id and manager.current_operator_id != manager.current_admin_id:
                        logging.info(f"Admin {client_id} vyhazuje operátora {manager.current_operator_id}")
                        await manager.set_role(manager.current_operator_id, "spectator")
                        manager.current_operator_id = manager.current_admin_id
                else:
                    await manager.send_personal(client_id, {"type": "info", "message": "Nemáte oprávnění."})
            
            elif msg_type == "cmd_joy":
                role = manager.roles.get(client_id)
                if role in ["operator", "admin"]:
                    logging.info(f"✅ Joystick příkaz od '{role}' ({client_id}) přijat.")
                else:
                    logging.warning(f"❌ Joystick příkaz od '{role}' ({client_id}) zamítnut.")
                    await manager.send_personal(client_id, {"type": "info", "message": "Nemáte oprávnění k řízení."})

    except WebSocketDisconnect:
        logging.info(f"WebSocketDisconnect pro klienta {client_id}.")
        await manager.disconnect(client_id)
    except Exception as e:
        logging.error(f"Došlo k chybě ve WebSocketu pro {client_id}: {e}", exc_info=True)
        await manager.disconnect(client_id)

@app.on_event("startup")
async def startup_event():
    logging.info(f"Testovací server se spouští na http://localhost:{PORT}")
    
    async def broadcast_status_data():
        while True:
            try:
                if manager.connections:
                    status_data = {
                        "type": "status",
                        "cpu": random.randint(10, 50), 
                        "ram": random.randint(40, 70), 
                        "temp": round(random.uniform(40.0, 55.0), 1),
                    }
                    await manager.broadcast(status_data)
                await asyncio.sleep(2)
            except Exception as e:
                logging.error(f"Chyba v broadcast_status_data: {e}", exc_info=True)

    asyncio.create_task(broadcast_status_data())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

