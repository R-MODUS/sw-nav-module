"""Central configuration values and filesystem paths for the websocket service."""

from pathlib import Path

TESTING = True
OPERATOR_PIN = "1234"
ADMIN_PIN = "4321"
HOST = "0.0.0.0"
PORT = 8080
LOG_LEVEL = "info"
TF_ROOT_FRAME = "base_link"
TF_BROADCAST_RATE_HZ = 5.0
SENSOR_DISCOVERY_RATE_HZ = 1.0

HERE = Path(__file__).resolve().parent.parent
WEBSOCKET_DIR = HERE / "websocket"
STATIC_DIR = WEBSOCKET_DIR / "static"
INDEX_HTML = WEBSOCKET_DIR / "index.html"

LIDAR_TOPIC = "/scan"
IMU_TOPIC = "/imu/data"
BUMPER_TOPIC_PREFIX = "/bumper/"
CLIFF_TOPIC_PREFIX = "/cliff/"

# Navigation topics
MAP_TOPIC = "/map"
MAP_UPDATES_TOPIC = "/map_updates"
PLAN_TOPIC = "/received_global_plan"
GOAL_POSE_TOPIC = "/goal_pose"
