import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

from rmodus_uart_output.uart_link import UartLink


class UartOutputNode(Node):
    """Forward /cmd_vel Twist bytes to a USB/UART port — no kinematics."""

    def __init__(self):
        super().__init__("uart_output")

        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("baudrate", 115200)
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("cmd_timeout_sec", 0.5)
        self.declare_parameter("watchdog_rate_hz", 10.0)

        port = str(self.get_parameter("port").value)
        baudrate = int(self.get_parameter("baudrate").value)
        topic = str(self.get_parameter("cmd_vel_topic").value)
        self._timeout = float(self.get_parameter("cmd_timeout_sec").value)
        rate = max(1.0, float(self.get_parameter("watchdog_rate_hz").value))

        self._link = UartLink(port=port, baudrate=baudrate)
        self._last_cmd = 0.0
        self.create_subscription(Twist, topic, self._on_cmd_vel, 10)
        # twist_mux po výpadku zdroje nulu nepošle; bez ní by MCU držel poslední rychlost.
        if self._timeout > 0.0:
            self.create_timer(1.0 / rate, self._on_watchdog)
        self.get_logger().info(
            f"uart_output: {topic} → {port} @{baudrate}, timeout {self._timeout:.2f}s"
        )

    def _on_cmd_vel(self, msg: Twist) -> None:
        self._last_cmd = time.monotonic()
        self._link.send_twist(msg.linear.x, msg.linear.y, msg.angular.z)

    def _on_watchdog(self) -> None:
        if time.monotonic() - self._last_cmd > self._timeout:
            self._link.send_twist(0.0, 0.0, 0.0)

    def destroy_node(self):
        try:
            self._link.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = UartOutputNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
