"""Publish e-stop request pulses when any bumper reports contact."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

from rmodus_interface.msg import Bumper


class BumperEStopRequestNode(Node):
    def __init__(self):
        super().__init__("bumper_estop_request")

        self.declare_parameter("enabled", True)
        self.declare_parameter("request_topic", "/rmodus/e_stop/request")
        self.declare_parameter(
            "bumper_topics",
            ["/bumper/front", "/bumper/rear", "/bumper/left", "/bumper/right"],
        )
        self.declare_parameter("retrigger_while_contact", False)

        if not bool(self.get_parameter("enabled").value):
            self.get_logger().info("bumper_estop_request disabled")
            return

        self.request_topic = str(self.get_parameter("request_topic").value)
        topics = [str(t) for t in self.get_parameter("bumper_topics").value]
        self.retrigger = bool(self.get_parameter("retrigger_while_contact").value)

        self._contact = {t: False for t in topics}
        self._any_was = False
        self._pub = self.create_publisher(Bool, self.request_topic, 10)

        for topic in topics:
            self.create_subscription(
                Bumper, topic, lambda msg, t=topic: self._on_bumper(msg, t), 10
            )

        self.get_logger().info(
            f"Bumper → e-stop request on {self.request_topic} from {topics}"
        )

    def _on_bumper(self, msg: Bumper, topic: str):
        self._contact[topic] = bool(msg.contact)
        any_contact = any(self._contact.values())
        rising = any_contact and not self._any_was
        hold = any_contact and self.retrigger
        self._any_was = any_contact
        if rising or hold:
            out = Bool()
            out.data = True
            self._pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = BumperEStopRequestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
