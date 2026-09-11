import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

from rmodus_uart_output.uart_link import UartLink


class UartOutputNode(Node):
    """Forward /cmd_vel_safe Twist bytes to a USB/UART port — no kinematics."""

    def __init__(self):
        super().__init__("uart_output")

        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("baudrate", 115200)
        self.declare_parameter("cmd_vel_topic", "/cmd_vel_safe")

        port = str(self.get_parameter("port").value)
        baudrate = int(self.get_parameter("baudrate").value)
        topic = str(self.get_parameter("cmd_vel_topic").value)

        self._link = UartLink(port=port, baudrate=baudrate)
        self.create_subscription(Twist, topic, self._on_cmd_vel, 10)
        self.get_logger().info(f"uart_output: {topic} → {port} @{baudrate}")

    def _on_cmd_vel(self, msg: Twist) -> None:
        self._link.send_twist(msg.linear.x, msg.linear.y, msg.angular.z)

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
