"""Gazebo contacts → std_msgs/UInt8MultiArray on bumpers.state_topic.

rmodus_bumper maps that array (index = pin) onto rmodus_interface/Bumper.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from ros_gz_interfaces.msg import Contacts
from std_msgs.msg import UInt8MultiArray


class SimBumperBridge(Node):
    def __init__(self):
        super().__init__("sim_bumper_bridge")

        self._topic = str(self.declare_parameter("state_topic", "/robot/bumpers/state").value)
        names = [str(v) for v in self.declare_parameter("bumper_names", [""]).value]
        pins = [int(v) for v in self.declare_parameter("bumper_pins", [0]).value]
        if not names or names == [""] or len(pins) != len(names):
            self.get_logger().error("bumper name/pin lists must be the same non-empty length")
            return

        self._timeout = 0.2
        self._last_contact = {name: None for name in names}
        self._pins = list(zip(names, pins))
        self._width = max(8, max(pins) + 1)
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self._pub = self.create_publisher(UInt8MultiArray, self._topic, qos)
        for name in names:
            self.create_subscription(
                Contacts,
                f"/sim/bumper/{name}/contact",
                lambda msg, bumper_name=name: self._on_contact(msg, bumper_name),
                10,
            )

        self.create_timer(0.1, self._publish)
        self.get_logger().info(
            f"Sim bumper raw {self._topic} pins {list(zip(names, pins))} (len {self._width})"
        )

    def _on_contact(self, msg, name):
        if msg.contacts:
            self._last_contact[name] = self.get_clock().now().nanoseconds / 1e9

    def _publish(self):
        if not getattr(self, "_pub", None):
            return
        now_sec = self.get_clock().now().nanoseconds / 1e9
        data = [0] * self._width
        for name, pin in self._pins:
            last = self._last_contact[name]
            if last is None or (now_sec - last) >= self._timeout:
                continue
            if 0 <= pin < self._width:
                data[pin] = 1
        out = UInt8MultiArray()
        out.data = data
        self._pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = SimBumperBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
