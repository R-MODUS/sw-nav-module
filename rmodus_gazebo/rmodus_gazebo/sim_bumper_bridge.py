"""Gazebo contacts → rmodus_interface/Bumper on the profile topics."""

import rclpy
from rclpy.node import Node
from ros_gz_interfaces.msg import Contacts
from rmodus_interface.msg import Bumper


class SimBumperBridge(Node):
    def __init__(self):
        super().__init__("sim_bumper_bridge")

        names = list(self.declare_parameter("bumper_names", [""]).value)
        topics = list(self.declare_parameter("bumper_topics", [""]).value)
        frames = list(self.declare_parameter("bumper_frames", [""]).value)
        widths = [float(v) for v in self.declare_parameter("bumper_widths", [0.0]).value]
        depths = [float(v) for v in self.declare_parameter("bumper_depths", [0.0]).value]
        heights = [float(v) for v in self.declare_parameter("bumper_heights", [0.0]).value]

        count = len(names)
        if not count or any(len(seq) != count for seq in (topics, frames, widths, depths, heights)):
            self.get_logger().error("bumper name/topic/frame/size lists must be the same length")
            return

        self._timeout = 0.2
        self._last_contact = {name: None for name in names}
        self._pubs = []
        for index, name in enumerate(names):
            self._pubs.append(
                (
                    name,
                    frames[index],
                    widths[index],
                    depths[index],
                    heights[index],
                    self.create_publisher(Bumper, topics[index], 10),
                )
            )
            self.create_subscription(
                Contacts,
                f"/sim/bumper/{name}/contact",
                lambda msg, bumper_name=name: self._on_contact(msg, bumper_name),
                10,
            )

        self.create_timer(0.1, self._publish)
        self.get_logger().info(f"Sim bumper bridge: {list(zip(names, topics))}")

    def _on_contact(self, msg, name):
        if msg.contacts:
            self._last_contact[name] = self.get_clock().now().nanoseconds / 1e9

    def _publish(self):
        if not getattr(self, "_pubs", None):
            return
        now = self.get_clock().now()
        now_sec = now.nanoseconds / 1e9
        stamp = now.to_msg()
        for name, frame, width, depth, height, pub in self._pubs:
            last = self._last_contact[name]
            out = Bumper()
            out.header.stamp = stamp
            out.header.frame_id = frame
            out.contact = last is not None and (now_sec - last) < self._timeout
            out.width = width
            out.depth = depth
            out.height = height
            pub.publish(out)


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
