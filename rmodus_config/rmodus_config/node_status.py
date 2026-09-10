"""Latched publisher of active profile path (for web/display later)."""
from __future__ import annotations

from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

from rmodus_config.store import ConfigPaths, load_paths_file, read_active_name, resolve_active_profile


def _load_paths(node: Node) -> ConfigPaths:
    share = Path(get_package_share_directory("rmodus_config")) / "config" / "paths.yaml"
    root = node.declare_parameter("configs_root", "").get_parameter_value().string_value
    paths_yaml = node.declare_parameter("paths_yaml", str(share)).get_parameter_value().string_value
    if paths_yaml and Path(paths_yaml).is_file():
        paths = load_paths_file(Path(paths_yaml))
    else:
        paths = ConfigPaths.from_root()
    if root.strip():
        return ConfigPaths.from_root(Path(root.strip()))
    return paths


class ConfigStatusNode(Node):
    def __init__(self) -> None:
        super().__init__("rmodus_config_status")
        self._paths = _load_paths(self)
        qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
        )
        self._pub_name = self.create_publisher(String, "/rmodus/config/active_name", qos)
        self._pub_path = self.create_publisher(String, "/rmodus/config/active_path", qos)
        self.create_service(Trigger, "/rmodus/config/reload", self._on_reload)
        self._publish()
        self.get_logger().info(
            f"configs_root={self._paths.root} active_file={self._paths.active_file}"
        )

    def _publish(self) -> None:
        name = read_active_name(self._paths) or ""
        msg_n = String()
        msg_n.data = name
        self._pub_name.publish(msg_n)
        msg_p = String()
        try:
            msg_p.data = str(resolve_active_profile(self._paths))
        except FileNotFoundError:
            msg_p.data = ""
        self._pub_path.publish(msg_p)

    def _on_reload(self, _req, res):
        try:
            self._publish()
            res.success = True
            res.message = read_active_name(self._paths) or ""
        except Exception as exc:  # noqa: BLE001
            res.success = False
            res.message = str(exc)
        return res


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ConfigStatusNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
