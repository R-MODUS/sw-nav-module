import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from rclpy.task import Future
from std_msgs.msg import String

import asyncio
import json
import math
import uvicorn
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Dict, Optional

# A "dummy" message class if the real one isn't available, to avoid crashing.
# In a real scenario, ensure your ROS2 environment provides this message type.
try:
    from my.msg import PiStatus
except ImportError:
    class PiStatus:
        cpu_usage_percent = 10.0
        ram_usage_percent = 0.0
        cpu_temperature = 0.0
    print("Warning: Could not import PiStatus message. Using a dummy class.")


# --- KONFIGURACE OPRÁVNĚNÍ ---
TESTING = True
OPERATOR_PIN = "1234"
ADMIN_PIN = "4321"

# --- STAVOVÉ PROMĚNNÉ SYSTÉMU ---
current_operator: Optional[WebSocket] = None
current_admin: Optional[WebSocket] = None

# --- KONFIGURACE CEST ---
HERE = Path(__file__).resolve().parent
WEBSOCKET_DIR = HERE / "websocket"
STATIC_DIR = WEBSOCKET_DIR / "static"
INDEX_HTML = WEBSOCKET_DIR / "index.html"


# Globální instance nodu a manažeru
ros_node: Optional['WebBridgeNode'] = None
manager = None

# --- LIFESPAN MANAGER (STARTUP/SHUTDOWN) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ros_node, manager
    
    # --- STARTUP ---
    print("Server startup: Initializing ROS... ⏳")
    manager = ConnectionManager()
    
    # Initialize ROS
    rclpy.init()
    
    # Get the currently running asyncio loop
    loop = asyncio.get_running_loop()
    
    # Create the ROS node with the correct loop
    ros_node = WebBridgeNode(loop)
    
    # Start rclpy.spin in a separate thread
    ros_thread = threading.Thread(target=rclpy.spin, args=(ros_node,), daemon=True)
    ros_thread.start()
    
    print("Server startup: ROS node running in background thread. ✅")
    
    yield  # Uvicorn runs the app here
    
    # --- SHUTDOWN ---
    print("Server shutdown: Cleaning up ROS... ⏳")
    if ros_node:
        ros_node.destroy_node()
    rclpy.shutdown()
    print("Server shutdown: ROS resources released. ✅")


# --- FASTAPI APLIKACE ---
app = FastAPI(lifespan=lifespan)

# Připojení statických souborů (CSS, JS, PDF)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Globální úložiště pro aktivní WebSocket klienty
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.roles: Dict[str, str] = {}

    def get_identifier(self, websocket: WebSocket) -> str:
        return f"{websocket.client.host}:{websocket.client.port}"

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
            # This can happen if the client disconnects abruptly.
            await self.disconnect(websocket)

    async def broadcast(self, message: dict):
        # Create a list of connections to iterate over, to avoid issues if the dict changes size.
        connections = list(self.active_connections.values())
        for connection in connections:
            await self.send_personal_message(message, connection)

    async def broadcast_user_list(self):
        user_list = [
            {"id": identifier, "role": self.roles.get(identifier, "spectator")}
            for identifier in self.active_connections.keys()
        ]
        await self.broadcast({"type": "user_list_update", "users": user_list})


# --- ROS2 NODE ---
class WebBridgeNode(Node):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__('web_bridge_node')
        self.loop = loop
        self.publisher_cmd = self.create_publisher(Twist, '/vector', 10)
        self.publisher_cmd_vel = self.create_publisher(Twist, '/cmd_vel', 10)
        #self.subscription_odom = self.create_subscription(Odometry, '/odom', self.odom_callback, 10)
        self.sub_scan = self.create_subscription(LaserScan, '/scan', self.scan_callback, 10)
        self.sub_status = self.create_subscription(PiStatus, '/system/pi_status', self.status_cb, 10)
        self.get_logger().info("WebBridgeNode initialized.")

    def odom_callback(self, msg):
        pos = msg.pose.pose.position
        data = {"type": "odom", "x": pos.x, "y": pos.y}
        if manager and manager.active_connections:
             asyncio.run_coroutine_threadsafe(manager.broadcast(data), self.loop)

    def scan_callback(self, msg):
        if manager and manager.active_connections:
            clean_ranges = [r if not math.isinf(r) and r > 0 else 0.0 for r in msg.ranges]
            data = {
                "type": "lidar",
                "angle_min": msg.angle_min,
                "angle_increment": msg.angle_increment,
                "ranges": clean_ranges
            }
            asyncio.run_coroutine_threadsafe(manager.broadcast(data), self.loop)

    def status_cb(self, msg):
        data = {
            "type": "status",
            "cpu": msg.cpu_usage_percent,
            "ram": msg.ram_usage_percent,
            "temp": msg.cpu_temperature
        }
        if manager and manager.active_connections:
            asyncio.run_coroutine_threadsafe(manager.broadcast(data), self.loop)

    def publish_joystick_cmd(self, data):
        msg = Twist()
        msg.linear.x = float(data.get('linear_y', 0))
        msg.linear.y = float(data.get('linear_x', 0)) * (-1)
        msg.angular.z = float(data.get('angular_z', 0))
        self.publisher_cmd.publish(msg)
        self.publisher_cmd_vel.publish(msg)

# --- HTTP ENDPOINTY ---
@app.get("/")
async def get_index():
    return FileResponse(INDEX_HTML)

# --- WEBSOCKET ENDPOINT ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_operator, current_admin
    await manager.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if TESTING and current_admin is None:
                if current_operator and current_operator != current_admin:
                    await manager.set_role(current_operator, "spectator")
            current_admin = websocket
            current_operator = websocket
            await manager.set_role(websocket, "admin")

            if msg_type == "request_operator":
                if data.get("pin") == OPERATOR_PIN:
                    operator_id = manager.get_identifier(current_operator) if current_operator else None
                    if not operator_id or operator_id not in manager.active_connections:
                        current_operator = websocket
                        await manager.set_role(websocket, "operator")
                    else:
                        await manager.send_personal_message({"type": "error", "message": "Operator role is already taken."}, websocket)
                else:
                    await manager.send_personal_message({"type": "error", "message": "Invalid PIN for Operator."}, websocket)

            elif msg_type == "request_admin":
                if data.get("pin") == ADMIN_PIN:
                    if current_operator and current_operator != current_admin:
                         await manager.set_role(current_operator, "spectator")
                    current_admin = websocket
                    current_operator = websocket
                    await manager.set_role(websocket, "admin")
                else:
                    await manager.send_personal_message({"type": "error", "message": "Invalid PIN for Admin."}, websocket)

            elif msg_type == "kick_operator":
                if websocket == current_admin:
                    if current_operator and current_operator != current_admin:
                        await manager.set_role(current_operator, "spectator")
                        current_operator = None 
                    current_operator = current_admin
                    await manager.broadcast_user_list()
            
            elif msg_type == "cmd_joy":
                if websocket == current_operator:
                    if ros_node:
                        ros_node.publish_joystick_cmd(data)
                else:
                    await manager.send_personal_message({"type": "info", "message": "You are not the operator."}, websocket)

    except WebSocketDisconnect:
        if websocket == current_operator:
            current_operator = None
        if websocket == current_admin:
            current_admin = None
            current_operator = None
            
    finally:
        await manager.disconnect(websocket)


# --- HLAVNÍ SPUŠTĚNÍ ---
def run(args=None):
    # Spustíme FastAPI/Uvicorn server
    # ROS se nyní spouští a ukončuje díky lifespan manažeru
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    run()
