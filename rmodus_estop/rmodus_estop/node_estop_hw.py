"""Physical e-stop box → GPIO → request pulse + HW active level."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool


class EStopHwNode(Node):
    """
    Read GPIO e-stop button and feed the central estop logic.

    - Rising edge → Bool(true) on request_topic (latches stop).
    - Level → Bool on hw_active_topic (true while pressed; blocks reset / keeps stop).
    """

    def __init__(self):
        super().__init__("rmodus_estop_hw")

        self.declare_parameter("enabled", True)
        self.declare_parameter("poll_rate_hz", 50.0)
        self.declare_parameter("pin", 16)
        self.declare_parameter("pull_up", True)
        self.declare_parameter("active_high", False)
        self.declare_parameter("request_topic", "/rmodus/e_stop/request")
        self.declare_parameter("hw_active_topic", "/rmodus/e_stop/hw_active")

        if not bool(self.get_parameter("enabled").value):
            self.get_logger().info("rmodus_estop_hw disabled")
            return

        rate = max(1.0, float(self.get_parameter("poll_rate_hz").value))
        pin = int(self.get_parameter("pin").value)
        pull_up = bool(self.get_parameter("pull_up").value)
        self.active_high = bool(self.get_parameter("active_high").value)
        request_topic = str(self.get_parameter("request_topic").value)
        hw_active_topic = str(self.get_parameter("hw_active_topic").value)

        self._button = None
        try:
            from gpiozero import Button

            self._button = Button(pin, pull_up=pull_up)
        except Exception as exc:
            self.get_logger().error(f"GPIO e-stop init failed: {exc}")
            return

        self._was_pressed = False
        self._request_pub = self.create_publisher(Bool, request_topic, 10)
        self._active_pub = self.create_publisher(Bool, hw_active_topic, 10)
        self.create_timer(1.0 / rate, self._on_timer)
        self.get_logger().info(
            f"GPIO e-stop pin={pin} → request={request_topic}, "
            f"hw_active={hw_active_topic}"
        )

    def _pressed(self) -> bool:
        if self._button is None:
            return False
        pressed = bool(self._button.is_pressed)
        # Optional invert when wiring differs from gpiozero pull-up default
        return (not pressed) if self.active_high else pressed

    def _on_timer(self):
        if self._button is None:
            return
        pressed = self._pressed()
        if pressed and not self._was_pressed:
            pulse = Bool()
            pulse.data = True
            self._request_pub.publish(pulse)
        self._was_pressed = pressed

        level = Bool()
        level.data = pressed
        self._active_pub.publish(level)


def main(args=None):
    rclpy.init(args=args)
    node = EStopHwNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
