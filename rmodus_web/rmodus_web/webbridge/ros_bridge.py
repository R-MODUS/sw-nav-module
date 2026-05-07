"""ROS2 node that bridges topics and joystick commands with websocket clients."""

import asyncio
import math
from typing import Dict, List

from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import OccupancyGrid, Path
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import Imu, LaserScan, Range
from tf2_msgs.msg import TFMessage

from rmodus_interface.msg import Bumper, PiStatus

from rmodus_web.webbridge.config import (
    BUMPER_TOPIC_PREFIX,
    CLIFF_TOPIC_PREFIX,
    GOAL_POSE_TOPIC,
    IMU_TOPIC,
    LIDAR_TOPIC,
    MAP_TOPIC,
    MAP_UPDATES_TOPIC,
    PLAN_TOPIC,
    SENSOR_DISCOVERY_RATE_HZ,
    TF_BROADCAST_RATE_HZ,
    TF_ROOT_FRAME,
)
from rmodus_web.webbridge.connection_manager import ConnectionManager
from rmodus_web.webbridge.sensor_catalog import SensorDefinition
from rmodus_web.webbridge.tf_utils import quaternion_to_yaw


class WebBridgeNode(Node):
    def __init__(self, loop: asyncio.AbstractEventLoop, manager: ConnectionManager):
        super().__init__("web_bridge_node")
        self.loop = loop
        self.manager = manager
        self.root_frame = TF_ROOT_FRAME
        self.sensor_definitions: Dict[str, SensorDefinition] = {}
        self.latest_sensor_messages: Dict[str, dict] = {}
        self.tf_frames: Dict[str, dict] = {}
        self.sensor_subscriptions: Dict[str, object] = {}
        self.latest_map = None
        self.latest_plan = None

        self.publisher_goal_pose = self.create_publisher(PoseStamped, GOAL_POSE_TOPIC, 10)
        self.publisher_cmd = self.create_publisher(Twist, "/vector", 10)
        self.publisher_cmd_vel = self.create_publisher(Twist, "/cmd_vel", 10)
        self.sub_status = self.create_subscription(PiStatus, "/system/pi_status", self.status_cb, 10)

        self._create_static_sensor_subscriptions()
        self._discover_dynamic_topics()
        self._create_tf_subscriptions()

        qos_volatile = QoSProfile(depth=1, durability=DurabilityPolicy.VOLATILE)
        self.sub_map = self.create_subscription(OccupancyGrid, MAP_TOPIC, self.map_callback, qos_volatile)
        self.sub_map_updates = self.create_subscription(
            OccupancyGrid, MAP_UPDATES_TOPIC, self.map_updates_callback, qos_volatile
        )
        self.sub_plan = self.create_subscription(Path, PLAN_TOPIC, self.plan_callback, qos_volatile)

        self.create_timer(1.0 / TF_BROADCAST_RATE_HZ, self.publish_tf_snapshot)
        self.create_timer(1.0 / SENSOR_DISCOVERY_RATE_HZ, self._discover_dynamic_topics)
        self.get_logger().info("WebBridgeNode initialized.")

    def _broadcast_threadsafe(self, data: dict):
        if self.manager.active_connections:
            asyncio.run_coroutine_threadsafe(self.manager.broadcast(data), self.loop)

    def _has_clients(self) -> bool:
        return bool(self.manager.active_connections)

    def _remember_sensor_message(self, sensor: SensorDefinition, payload: dict):
        current_sensor = self.sensor_definitions.get(sensor.topic, sensor)
        message = {
            "type": "sensor_data",
            "sensor_type": current_sensor.sensor_type,
            "sensor_id": current_sensor.sensor_id,
            "topic": current_sensor.topic,
            "frame_id": current_sensor.frame_id,
            "payload": payload,
        }
        self.latest_sensor_messages[f"{current_sensor.sensor_type}:{current_sensor.sensor_id}"] = message
        self._broadcast_threadsafe(message)

    def _normalize_frame_id(self, frame_id: str) -> str:
        if not frame_id:
            return ""
        return frame_id.lstrip("/")

    def _create_static_sensor_subscriptions(self):
        self._register_sensor(
            SensorDefinition("lidar", "scan", LIDAR_TOPIC, "Main lidar", "laser", "sensor_msgs/LaserScan"),
            LaserScan,
            self.scan_callback,
        )
        self._register_sensor(
            SensorDefinition("imu", "imu_data", IMU_TOPIC, "IMU", "imu_link", "sensor_msgs/Imu"),
            Imu,
            self.imu_callback,
        )

    def _discover_dynamic_topics(self):
        for topic_name, topic_types in self.get_topic_names_and_types():
            if topic_name.startswith(BUMPER_TOPIC_PREFIX) and "rmodus_interface/msg/Bumper" in topic_types:
                sensor = self._sensor_from_topic("bumper", topic_name, "rmodus_interface/Bumper")
                self._register_sensor(sensor, Bumper, self.bumper_callback)
            if topic_name.startswith(CLIFF_TOPIC_PREFIX) and "sensor_msgs/msg/Range" in topic_types:
                sensor = self._sensor_from_topic("cliff", topic_name, "sensor_msgs/Range")
                self._register_sensor(sensor, Range, self.cliff_callback)

    def _sensor_from_topic(self, sensor_type: str, topic_name: str, message_type: str) -> SensorDefinition:
        suffix = topic_name.rstrip("/").split("/")[-1]
        label = suffix.replace("_", " ").title()
        frame_suffix = suffix if suffix.endswith("_link") else f"{suffix}_link"
        return SensorDefinition(sensor_type, suffix, topic_name, label, frame_suffix, message_type)

    def _register_sensor(self, sensor: SensorDefinition, message_cls, callback):
        if sensor.topic in self.sensor_subscriptions:
            return
        subscription = self.create_subscription(
            message_cls, sensor.topic, lambda msg, sensor=sensor: callback(msg, sensor), 10
        )
        self.sensor_subscriptions[sensor.topic] = subscription
        self.sensor_definitions[sensor.topic] = sensor
        self._broadcast_sensor_catalog()

    def _broadcast_sensor_catalog(self):
        self._broadcast_threadsafe({"type": "sensor_catalog", "sensors": self.get_sensor_catalog()})

    def _create_tf_subscriptions(self):
        tf_static_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(TFMessage, "/tf", self.tf_callback, 30)
        self.create_subscription(
            TFMessage, "/tf_static", lambda msg: self.tf_callback(msg, is_static=True), tf_static_qos
        )

    def scan_callback(self, msg: LaserScan, sensor: SensorDefinition):
        if not self._has_clients():
            return
        clean_ranges = [r if not math.isinf(r) and r > 0 else 0.0 for r in msg.ranges]
        self._update_sensor_frame(sensor.topic, msg.header.frame_id)
        payload = {
            "angle_min": msg.angle_min,
            "angle_increment": msg.angle_increment,
            "max_range": msg.range_max,
            "ranges": clean_ranges,
        }
        self._remember_sensor_message(sensor, payload)
        self._broadcast_threadsafe({"type": "lidar", **payload})

    def bumper_callback(self, msg: Bumper, sensor: SensorDefinition):
        if not self._has_clients():
            return
        self._remember_sensor_message(sensor, {"contact": bool(msg.contact), "width": float(msg.width)})

    def cliff_callback(self, msg: Range, sensor: SensorDefinition):
        if not self._has_clients():
            return
        self._update_sensor_frame(sensor.topic, msg.header.frame_id)
        range_span = max(msg.max_range - msg.min_range, 1e-6)
        payload = {
            "range": float(msg.range),
            "min_range": float(msg.min_range),
            "max_range": float(msg.max_range),
            "field_of_view": float(msg.field_of_view),
            "normalized_range": max(0.0, min(1.0, (msg.range - msg.min_range) / range_span)),
        }
        self._remember_sensor_message(sensor, payload)

    def imu_callback(self, msg: Imu, sensor: SensorDefinition):
        if not self._has_clients():
            return
        self._update_sensor_frame(sensor.topic, msg.header.frame_id)
        payload = {
            "orientation_x": float(msg.orientation.x),
            "orientation_y": float(msg.orientation.y),
            "orientation_z": float(msg.orientation.z),
            "orientation_w": float(msg.orientation.w),
            "yaw": quaternion_to_yaw(
                msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w
            ),
            "angular_velocity_x": float(msg.angular_velocity.x),
            "angular_velocity_y": float(msg.angular_velocity.y),
            "angular_velocity_z": float(msg.angular_velocity.z),
            "linear_acceleration_x": float(msg.linear_acceleration.x),
            "linear_acceleration_y": float(msg.linear_acceleration.y),
            "linear_acceleration_z": float(msg.linear_acceleration.z),
        }
        self._remember_sensor_message(sensor, payload)

    def _update_sensor_frame(self, topic_name: str, frame_id: str):
        normalized_frame = self._normalize_frame_id(frame_id)
        if not normalized_frame:
            return
        sensor = self.sensor_definitions.get(topic_name)
        if not sensor or sensor.frame_id == normalized_frame:
            return
        self.sensor_definitions[topic_name] = SensorDefinition(
            sensor.sensor_type, sensor.sensor_id, sensor.topic, sensor.label, normalized_frame, sensor.message_type
        )
        self._broadcast_sensor_catalog()

    def tf_callback(self, msg: TFMessage, is_static: bool = False):
        if not self._has_clients():
            return
        for transform in msg.transforms:
            child_frame_id = transform.child_frame_id
            if not child_frame_id:
                continue
            normalized_child_frame_id = self._normalize_frame_id(child_frame_id)
            normalized_parent_frame_id = self._normalize_frame_id(transform.header.frame_id)
            if not normalized_child_frame_id:
                continue
            translation = transform.transform.translation
            rotation = transform.transform.rotation
            self.tf_frames[normalized_child_frame_id] = {
                "parent_frame_id": normalized_parent_frame_id,
                "child_frame_id": normalized_child_frame_id,
                "x": float(translation.x),
                "y": float(translation.y),
                "yaw": quaternion_to_yaw(rotation.x, rotation.y, rotation.z, rotation.w),
                "is_static": is_static,
            }

    def publish_tf_snapshot(self):
        if not self._has_clients() or not self.tf_frames:
            return
        self._broadcast_threadsafe(
            {"type": "tf_2d", "root_frame": self.root_frame, "frames": self.get_tf_frames_snapshot()}
        )

    def status_cb(self, msg: PiStatus):
        if not self._has_clients():
            return
        self._broadcast_threadsafe(
            {
                "type": "status",
                "cpu": msg.cpu_usage_percent,
                "ram": msg.ram_usage_percent,
                "temp": msg.cpu_temperature,
            }
        )

    def publish_joystick_cmd(self, data: dict):
        msg = Twist()
        msg.linear.x = float(data.get("linear_y", 0))
        msg.linear.y = float(data.get("linear_x", 0)) * (-1)
        msg.angular.z = float(data.get("angular_z", 0))
        self.publisher_cmd.publish(msg)
        self.publisher_cmd_vel.publish(msg)

    def get_tf_frames_snapshot(self) -> List[dict]:
        return sorted(self.tf_frames.values(), key=lambda frame: frame["child_frame_id"])

    def get_initial_messages(self) -> List[dict]:
        messages = [{"type": "sensor_catalog", "sensors": self.get_sensor_catalog()}]
        if self.tf_frames:
            messages.append({"type": "tf_2d", "root_frame": self.root_frame, "frames": self.get_tf_frames_snapshot()})
        if self.latest_map:
            messages.append(self.latest_map)
        if self.latest_plan:
            messages.append(self.latest_plan)
        messages.extend(self.latest_sensor_messages.values())
        return messages

    def get_sensor_catalog(self) -> List[dict]:
        sensors = [sensor.as_dict() for sensor in self.sensor_definitions.values()]
        return sorted(sensors, key=lambda sensor: (sensor["sensor_type"], sensor["sensor_id"]))

    def map_callback(self, msg: OccupancyGrid):
        if not self._has_clients():
            return
        payload = {
            "type": "map_grid",
            "frame_id": self._normalize_frame_id(msg.header.frame_id),
            "width": msg.info.width,
            "height": msg.info.height,
            "resolution": msg.info.resolution,
            "origin": {"x": float(msg.info.origin.position.x), "y": float(msg.info.origin.position.y)},
            "data": list(msg.data),
        }
        self.latest_map = payload
        self._broadcast_threadsafe(payload)

    def map_updates_callback(self, msg: OccupancyGrid):
        if not self._has_clients():
            return
        payload = {
            "type": "map_updates",
            "frame_id": self._normalize_frame_id(msg.header.frame_id),
            "width": msg.info.width,
            "height": msg.info.height,
            "resolution": msg.info.resolution,
            "origin": {"x": float(msg.info.origin.position.x), "y": float(msg.info.origin.position.y)},
            "data": list(msg.data),
        }
        self._broadcast_threadsafe(payload)

    def plan_callback(self, msg: Path):
        if not self._has_clients():
            return
        path_points = [{"x": float(p.pose.position.x), "y": float(p.pose.position.y)} for p in msg.poses]
        payload = {"type": "nav_path", "frame_id": self._normalize_frame_id(msg.header.frame_id), "path": path_points}
        self.latest_plan = payload
        self._broadcast_threadsafe(payload)

    def publish_goal_pose(self, x: float, y: float, yaw: float):
        goal_msg = PoseStamped()
        goal_msg.header.frame_id = "map"
        goal_msg.pose.position.x = x
        goal_msg.pose.position.y = y
        half_yaw = yaw / 2.0
        goal_msg.pose.orientation.z = math.sin(half_yaw)
        goal_msg.pose.orientation.w = math.cos(half_yaw)
        self.publisher_goal_pose.publish(goal_msg)
