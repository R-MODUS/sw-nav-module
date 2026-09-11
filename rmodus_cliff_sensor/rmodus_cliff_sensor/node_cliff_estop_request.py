"""Publish e-stop request pulses when any cliff range exceeds threshold."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Bool


class CliffEStopRequestNode(Node):
    def __init__(self):
        super().__init__("cliff_estop_request")

        self.declare_parameter("enabled", True)
        self.declare_parameter("request_topic", "/rmodus/e_stop/request")
        self.declare_parameter(
            "cliff_topics",
            ["/cliff/fl", "/cliff/fr", "/cliff/rl", "/cliff/rr"],
        )
        # Cliff detected when measured range is above this (m). Larger = further = hole.
        self.declare_parameter("cliff_range_threshold_m", 0.12)
        self.declare_parameter("retrigger_while_cliff", False)

        if not bool(self.get_parameter("enabled").value):
            self.get_logger().info("cliff_estop_request disabled")
            return

        self.request_topic = str(self.get_parameter("request_topic").value)
        topics = [str(t) for t in self.get_parameter("cliff_topics").value]
        self.threshold = float(self.get_parameter("cliff_range_threshold_m").value)
        self.retrigger = bool(self.get_parameter("retrigger_while_cliff").value)

        self._cliff = {t: False for t in topics}
        self._any_was = False
        self._pub = self.create_publisher(Bool, self.request_topic, 10)

        for topic in topics:
            self.create_subscription(
                Range, topic, lambda msg, t=topic: self._on_range(msg, t), 10
            )

        self.get_logger().info(
            f"Cliff → e-stop request on {self.request_topic} "
            f"(threshold={self.threshold:.3f} m) from {topics}"
        )

    def _on_range(self, msg: Range, topic: str):
        r = float(msg.range)
        # Invalid / out of range: treat conservatively as cliff if above max
        is_cliff = r > self.threshold or r < 0.0
        self._cliff[topic] = is_cliff
        any_cliff = any(self._cliff.values())
        rising = any_cliff and not self._any_was
        hold = any_cliff and self.retrigger
        self._any_was = any_cliff
        if rising or hold:
            out = Bool()
            out.data = True
            self._pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = CliffEStopRequestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
