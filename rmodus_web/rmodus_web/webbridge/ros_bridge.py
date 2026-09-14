"""ROS2 node that bridges topics and joystick commands with websocket clients."""

import asyncio
import math
import time
from typing import Dict, List, Optional

from geometry_msgs.msg import PoseStamped, Twist, TwistStamped, TwistWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid, Path
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import Imu, LaserScan, Range
from std_msgs.msg import Bool
from std_srvs.srv import Trigger
from tf2_msgs.msg import TFMessage

from rmodus_interface.msg import Bumper, PiStatus
from rmodus_interface.srv import (
    ActivateProfile,
    CreateProfile,
    DeleteProfile,
    GetNetworkConfig,
    GetProfile,
    ListProfiles,
    RenameProfile,
    SaveProfile,
    SetNetworkConfig,
)

from rmodus_web.webbridge.config import WebConfig
from rmodus_web.webbridge.connection_manager import ConnectionManager
from rmodus_web.webbridge.sensor_catalog import SensorDefinition
from rmodus_web.webbridge.tf_utils import quaternion_to_yaw


class WebBridgeNode(Node):
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        manager: ConnectionManager,
        cfg: Optional[WebConfig] = None,
    ):
        super().__init__("web_bridge_node")
        self.loop = loop
        self.manager = manager
        self.cfg = cfg or WebConfig()
        self.root_frame = self.cfg.tf_root_frame
        self.sensor_definitions: Dict[str, SensorDefinition] = {}
        self.latest_sensor_messages: Dict[str, dict] = {}
        self.tf_frames: Dict[str, dict] = {}
        self.sensor_subscriptions: Dict[str, object] = {}
        self.latest_map = None
        self.latest_plan = None
        self.latest_goal = None
        self.latest_e_stop = None
        self.tf_subscription = None
        self.tf_static_subscription = None
        self.tf_last_update_time = 0.0
        self.tf_last_resubscribe_time = 0.0
        self.tf_is_stale = True
        self._last_sensor_catalog_signature = None
        self._profile_service_timeout_sec = 8.0

        self.cmd_use_twist_stamped = bool(self.cfg.cmd_use_twist_stamped)
        self.cmd_frame_id = self.cfg.cmd_frame_id or "base_link"
        cmd_msg_type = TwistStamped if self.cmd_use_twist_stamped else Twist

        self.publisher_goal_pose = self.create_publisher(PoseStamped, self.cfg.goal_pose_topic, 10)
        self.publisher_cmd_vel = self.create_publisher(cmd_msg_type, self.cfg.cmd_vel_topic, 10)
        self.publisher_e_stop_request = self.create_publisher(
            Bool, self.cfg.e_stop_request_topic, 10
        )
        self.publisher_e_stop_reset = self.create_publisher(Bool, self.cfg.e_stop_reset_topic, 10)
        self.sub_status = self.create_subscription(PiStatus, "/system/pi_status", self.status_cb, 10)
        self.sub_e_stop = self.create_subscription(
            Bool, self.cfg.e_stop_state_topic, self.e_stop_callback, 10
        )

        self._cli_list = self.create_client(ListProfiles, "/rmodus/config/list")
        self._cli_get = self.create_client(GetProfile, "/rmodus/config/get")
        self._cli_save = self.create_client(SaveProfile, "/rmodus/config/save")
        self._cli_create = self.create_client(CreateProfile, "/rmodus/config/create")
        self._cli_delete = self.create_client(DeleteProfile, "/rmodus/config/delete")
        self._cli_rename = self.create_client(RenameProfile, "/rmodus/config/rename")
        self._cli_activate = self.create_client(ActivateProfile, "/rmodus/config/activate")
        self._cli_restart = self.create_client(Trigger, "/rmodus/system/restart")
        self._cli_reboot = self.create_client(Trigger, "/rmodus/system/reboot")
        self._cli_net_get = self.create_client(GetNetworkConfig, "/rmodus/network/get")
        self._cli_net_set = self.create_client(SetNetworkConfig, "/rmodus/network/set")
        self._cli_net_apply = self.create_client(Trigger, "/rmodus/network/apply")

        self.get_logger().info(
            f"Cmd output: {'TwistStamped' if self.cmd_use_twist_stamped else 'Twist'}"
            f" on {self.cfg.cmd_vel_topic}"
            + (f" (frame_id={self.cmd_frame_id})" if self.cmd_use_twist_stamped else "")
        )
        self.get_logger().info(
            f"E-stop topics: state={self.cfg.e_stop_state_topic} "
            f"request={self.cfg.e_stop_request_topic} reset={self.cfg.e_stop_reset_topic}"
        )
        self.get_logger().info(f"Web config: {self.cfg.source}")
        self.get_logger().info(
            "Profile/network services: /rmodus/config/* /rmodus/network/{get,set,apply}"
        )

        self._discover_dynamic_topics()
        self._create_tf_subscriptions()

        qos_volatile = QoSProfile(depth=1, durability=DurabilityPolicy.VOLATILE)
        self.sub_map = self.create_subscription(
            OccupancyGrid, self.cfg.map_topic, self.map_callback, qos_volatile
        )
        self.sub_map_updates = self.create_subscription(
            OccupancyGrid, self.cfg.map_updates_topic, self.map_updates_callback, qos_volatile
        )
        self.sub_plan = self.create_subscription(
            Path, self.cfg.plan_topic, self.plan_callback, qos_volatile
        )
        self.sub_goal_pose = self.create_subscription(
            PoseStamped, self.cfg.goal_pose_topic, self.goal_pose_callback, 10
        )

        tf_period = 1.0 / self.cfg.tf_broadcast_rate_hz if self.cfg.tf_broadcast_rate_hz > 0 else 0.2
        discovery_period = (
            1.0 / self.cfg.sensor_discovery_rate_hz if self.cfg.sensor_discovery_rate_hz > 0 else 1.0
        )
        self.create_timer(tf_period, self.publish_tf_snapshot)
        self.create_timer(1.0, self.check_tf_health)
        self.create_timer(discovery_period, self._discover_dynamic_topics)
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

    def _topic_has_publishers(self, topic_name: str) -> bool:
        """True jen když topic někdo skutečně publikuje (ne stačí náš vlastní subscribe)."""
        try:
            return bool(self.get_publishers_info_by_topic(topic_name))
        except Exception:
            return False

    def _sensor_id_from_topic(self, topic_name: str) -> str:
        parts = [part for part in topic_name.strip("/").split("/") if part]
        return "_".join(parts) if parts else "sensor"

    def _sensor_label_from_topic(self, sensor_type: str, topic_name: str) -> str:
        if sensor_type == "lidar" and topic_name == self.cfg.lidar_topic:
            return "Hlavní LiDAR"
        if sensor_type == "imu" and topic_name == self.cfg.imu_topic:
            return "IMU senzor"
        return topic_name.strip("/").replace("/", " · ").replace("_", " ")

    def _discover_dynamic_topics(self):
        active_dynamic_topics = set()
        topic_types_by_name = {name: types for name, types in self.get_topic_names_and_types()}

        for topic_name, topic_types in topic_types_by_name.items():
            if not self._topic_has_publishers(topic_name):
                continue

            if "sensor_msgs/msg/LaserScan" in topic_types:
                sensor = self._sensor_from_topic("lidar", topic_name, "sensor_msgs/LaserScan")
                self._register_sensor(sensor, LaserScan, self.scan_callback)
                active_dynamic_topics.add(topic_name)
                continue

            if "sensor_msgs/msg/Imu" in topic_types:
                sensor = self._sensor_from_topic("imu", topic_name, "sensor_msgs/Imu")
                self._register_sensor(sensor, Imu, self.imu_callback)
                active_dynamic_topics.add(topic_name)
                continue

            if topic_name.startswith(self.cfg.bumper_topic_prefix) and "rmodus_interface/msg/Bumper" in topic_types:
                sensor = self._sensor_from_topic("bumper", topic_name, "rmodus_interface/Bumper")
                self._register_sensor(sensor, Bumper, self.bumper_callback)
                active_dynamic_topics.add(topic_name)
                continue

            if topic_name.startswith(self.cfg.cliff_topic_prefix) and "sensor_msgs/msg/Range" in topic_types:
                sensor = self._sensor_from_topic("cliff", topic_name, "sensor_msgs/Range")
                self._register_sensor(sensor, Range, self.cliff_callback)
                active_dynamic_topics.add(topic_name)
                continue

            if (
                topic_name.startswith(self.cfg.flow_topic_prefix)
                and "geometry_msgs/msg/TwistWithCovarianceStamped" in topic_types
            ):
                sensor = self._sensor_from_topic(
                    "optical_flow", topic_name, "geometry_msgs/TwistWithCovarianceStamped"
                )
                self._register_sensor(sensor, TwistWithCovarianceStamped, self.optical_flow_callback)
                active_dynamic_topics.add(topic_name)

        self._prune_missing_dynamic_topics(active_dynamic_topics)

    def _sensor_from_topic(self, sensor_type: str, topic_name: str, message_type: str) -> SensorDefinition:
        sensor_id = self._sensor_id_from_topic(topic_name)
        label = self._sensor_label_from_topic(sensor_type, topic_name)
        suffix = topic_name.rstrip("/").split("/")[-1]
        frame_suffix = suffix if suffix.endswith("_link") else f"{suffix}_link"
        return SensorDefinition(sensor_type, sensor_id, topic_name, label, frame_suffix, message_type)

    def _register_sensor(self, sensor: SensorDefinition, message_cls, callback):
        if sensor.topic in self.sensor_subscriptions:
            return
        subscription = self.create_subscription(
            message_cls,
            sensor.topic,
            lambda msg, sensor=sensor: callback(msg, sensor),
            qos_profile_sensor_data,
        )
        self.sensor_subscriptions[sensor.topic] = subscription
        self.sensor_definitions[sensor.topic] = sensor
        self._broadcast_sensor_catalog(force=True)

    def _prune_missing_dynamic_topics(self, active_dynamic_topics: set):
        to_remove = []
        for topic_name, sensor in self.sensor_definitions.items():
            if sensor.sensor_type not in ("lidar", "imu", "bumper", "cliff", "optical_flow"):
                continue
            if topic_name in active_dynamic_topics:
                continue
            to_remove.append(topic_name)

        for topic_name in to_remove:
            subscription = self.sensor_subscriptions.pop(topic_name, None)
            if subscription is not None:
                self.destroy_subscription(subscription)
            sensor = self.sensor_definitions.pop(topic_name, None)
            if sensor is None:
                continue
            self.latest_sensor_messages.pop(f"{sensor.sensor_type}:{sensor.sensor_id}", None)

        if to_remove:
            self._broadcast_sensor_catalog(force=True)

    def _sensor_visible_for_ui(self, sensor_dict: dict) -> bool:
        """Katalog odpovídá tomu, co je ve stromu TF — ne všechna ROS témata."""
        if not self.tf_frames:
            return True
        fid = self._normalize_frame_id(sensor_dict.get("frame_id") or "")
        st = sensor_dict.get("sensor_type") or ""
        if fid and fid in self.tf_frames:
            return True
        if st == "lidar":
            return any("lidar" in fr for fr in self.tf_frames)
        if st == "imu":
            return any("imu" in fr for fr in self.tf_frames)
        if st == "optical_flow":
            return any("flow" in fr for fr in self.tf_frames)
        return False

    def _broadcast_sensor_catalog(self, *, force: bool = False):
        catalog = self.get_sensor_catalog()
        signature = tuple((s["sensor_type"], s["sensor_id"], s.get("frame_id")) for s in catalog)
        if not force and signature == self._last_sensor_catalog_signature:
            return
        self._last_sensor_catalog_signature = signature
        self._broadcast_threadsafe({"type": "sensor_catalog", "sensors": catalog})

    def _create_tf_subscriptions(self):
        tf_static_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if self.tf_subscription is not None:
            self.destroy_subscription(self.tf_subscription)
        if self.tf_static_subscription is not None:
            self.destroy_subscription(self.tf_static_subscription)
        self.tf_subscription = self.create_subscription(TFMessage, "/tf", self.tf_callback, 30)
        self.tf_static_subscription = self.create_subscription(
            TFMessage, "/tf_static", lambda msg: self.tf_callback(msg, is_static=True), tf_static_qos
        )
        self.tf_last_resubscribe_time = time.monotonic()
        self.get_logger().info("TF subscriptions (re)created.")

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
        # Map overlay bere jen „hlavní“ LiDAR z web.topics.lidar
        if sensor.topic == self.cfg.lidar_topic:
            self._broadcast_threadsafe({"type": "lidar", **payload})

    def bumper_callback(self, msg: Bumper, sensor: SensorDefinition):
        if msg.header.frame_id:
            self._update_sensor_frame(sensor.topic, msg.header.frame_id)
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

    def optical_flow_callback(self, msg: TwistWithCovarianceStamped, sensor: SensorDefinition):
        if msg.header.frame_id:
            self._update_sensor_frame(sensor.topic, msg.header.frame_id)
        if not self._has_clients():
            return
        twist = msg.twist.twist
        self._remember_sensor_message(
            sensor,
            {
                "vx": float(twist.linear.x),
                "vy": float(twist.linear.y),
                "vz": float(twist.linear.z),
                "wx": float(twist.angular.x),
                "wy": float(twist.angular.y),
                "wz": float(twist.angular.z),
            },
        )

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
        self._broadcast_sensor_catalog(force=True)

    def tf_callback(self, msg: TFMessage, is_static: bool = False):
        now = time.monotonic()
        self.tf_last_update_time = now
        self.tf_is_stale = False
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
        self._broadcast_sensor_catalog()

    def check_tf_health(self):
        now = time.monotonic()
        stale_by_timeout = (now - self.tf_last_update_time) > self.cfg.tf_stale_timeout_sec
        has_tf_data = bool(self.tf_frames)
        current_stale = stale_by_timeout or not has_tf_data
        if current_stale != self.tf_is_stale:
            self.tf_is_stale = current_stale
            if self._has_clients():
                self._broadcast_threadsafe(
                    {
                        "type": "tf_status",
                        "stale": self.tf_is_stale,
                        "last_update_age_sec": max(0.0, now - self.tf_last_update_time),
                        "frame_count": len(self.tf_frames),
                    }
                )
            state_text = "stale" if self.tf_is_stale else "healthy"
            self.get_logger().info(f"TF stream state changed: {state_text}.")

        if self.tf_is_stale and (now - self.tf_last_resubscribe_time) > self.cfg.tf_resubscribe_cooldown_sec:
            self.get_logger().warn("TF stream stale. Recreating /tf and /tf_static subscriptions.")
            self._create_tf_subscriptions()

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

    def e_stop_callback(self, msg: Bool):
        payload = {"type": "e_stop", "active": bool(msg.data)}
        self.latest_e_stop = payload
        if not self._has_clients():
            return
        self._broadcast_threadsafe(payload)

    def publish_e_stop_request(self):
        msg = Bool()
        msg.data = True
        self.publisher_e_stop_request.publish(msg)

    def publish_e_stop_reset(self):
        msg = Bool()
        msg.data = True
        self.publisher_e_stop_reset.publish(msg)

    def publish_joystick_cmd(self, data: dict):
        linear_x = float(data.get("linear_y", 0))
        linear_y = float(data.get("linear_x", 0)) * (-1)
        angular_z = float(data.get("angular_z", 0))

        if self.cmd_use_twist_stamped:
            msg = TwistStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self.cmd_frame_id
            msg.twist.linear.x = linear_x
            msg.twist.linear.y = linear_y
            msg.twist.angular.z = angular_z
        else:
            msg = Twist()
            msg.linear.x = linear_x
            msg.linear.y = linear_y
            msg.angular.z = angular_z

        self.publisher_cmd_vel.publish(msg)

    def get_tf_frames_snapshot(self) -> List[dict]:
        return sorted(self.tf_frames.values(), key=lambda frame: frame["child_frame_id"])

    def get_initial_messages(self) -> List[dict]:
        messages = [{"type": "sensor_catalog", "sensors": self.get_sensor_catalog()}]
        now = time.monotonic()
        last_update_age_sec = max(0.0, now - self.tf_last_update_time) if self.tf_last_update_time > 0 else 0.0
        messages.append(
            {
                "type": "tf_status",
                "stale": self.tf_is_stale or not self.tf_frames,
                "last_update_age_sec": last_update_age_sec,
                "frame_count": len(self.tf_frames),
            }
        )
        if self.tf_frames:
            messages.append({"type": "tf_2d", "root_frame": self.root_frame, "frames": self.get_tf_frames_snapshot()})
        if self.latest_map:
            messages.append(self.latest_map)
        if self.latest_plan:
            messages.append(self.latest_plan)
        if self.latest_goal:
            messages.append(self.latest_goal)
        if self.latest_e_stop:
            messages.append(self.latest_e_stop)
        messages.extend(self.latest_sensor_messages.values())
        return messages

    def get_sensor_catalog(self) -> List[dict]:
        sensors = [sensor.as_dict() for sensor in self.sensor_definitions.values()]
        sensors = [s for s in sensors if self._sensor_visible_for_ui(s)]
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

    def _goal_pose_payload(self, frame_id: str, x: float, y: float, yaw: float) -> dict:
        return {
            "type": "goal_pose",
            "frame_id": self._normalize_frame_id(frame_id) or "map",
            "x": float(x),
            "y": float(y),
            "yaw": float(yaw),
        }

    def goal_pose_callback(self, msg: PoseStamped):
        if not self._has_clients():
            return
        yaw = quaternion_to_yaw(
            msg.pose.orientation.x,
            msg.pose.orientation.y,
            msg.pose.orientation.z,
            msg.pose.orientation.w,
        )
        payload = self._goal_pose_payload(
            msg.header.frame_id,
            msg.pose.position.x,
            msg.pose.position.y,
            yaw,
        )
        self.latest_goal = payload
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
        payload = self._goal_pose_payload(goal_msg.header.frame_id, x, y, yaw)
        self.latest_goal = payload
        self._broadcast_threadsafe(payload)

    def _call_profile_service(self, client, request):
        """Call a /rmodus/config/* service while another thread spins this node."""
        if not client.wait_for_service(timeout_sec=self._profile_service_timeout_sec):
            raise TimeoutError(
                "rmodus_config services nedostupné — běží bringup.config / config_manager?"
            )
        future = client.call_async(request)
        deadline = time.time() + self._profile_service_timeout_sec
        while not future.done():
            if time.time() >= deadline:
                raise TimeoutError("timeout při volání rmodus_config service")
            time.sleep(0.02)
        result = future.result()
        if result is None:
            raise RuntimeError("prázdná odpověď z rmodus_config service")
        return result

    def profiles_list(self):
        return self._call_profile_service(self._cli_list, ListProfiles.Request())

    def profiles_get(self, name: str):
        req = GetProfile.Request()
        req.name = name
        return self._call_profile_service(self._cli_get, req)

    def profiles_save(self, name: str, content: str):
        req = SaveProfile.Request()
        req.name = name
        req.content = content
        return self._call_profile_service(self._cli_save, req)

    def profiles_create(self, name: str, source: str = "", content: str = ""):
        req = CreateProfile.Request()
        req.name = name
        req.source = source or ""
        req.content = content or ""
        return self._call_profile_service(self._cli_create, req)

    def profiles_delete(self, name: str):
        req = DeleteProfile.Request()
        req.name = name
        return self._call_profile_service(self._cli_delete, req)

    def profiles_rename(self, old_name: str, new_name: str):
        req = RenameProfile.Request()
        req.old_name = old_name
        req.new_name = new_name
        return self._call_profile_service(self._cli_rename, req)

    def profiles_activate(self, name: str):
        req = ActivateProfile.Request()
        req.name = name
        return self._call_profile_service(self._cli_activate, req)

    def system_restart_rmodus(self):
        return self._call_profile_service(self._cli_restart, Trigger.Request())

    def system_reboot_host(self):
        return self._call_profile_service(self._cli_reboot, Trigger.Request())

    def network_get(self):
        return self._call_profile_service(self._cli_net_get, GetNetworkConfig.Request())

    def network_set(self, config_json: str, apply: bool = False):
        req = SetNetworkConfig.Request()
        req.config_json = config_json
        req.apply = bool(apply)
        return self._call_profile_service(self._cli_net_set, req)

    def network_apply(self):
        return self._call_profile_service(self._cli_net_apply, Trigger.Request())
