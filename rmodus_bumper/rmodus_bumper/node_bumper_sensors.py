import rclpy
from rclpy.node import Node
import board
import busio
from adafruit_mcp230xx.mcp23017 import MCP23017
import digitalio

from rmodus_interface.msg import Bumper


class BumperNode(Node):
    """Read corner contacts (MCP23017) and publish face Bumper topics."""

    def __init__(self):
        super().__init__("bumper_node")

        self.declare_parameter("publish_rate_hz", 50.0)
        self.declare_parameter("mcp_address", "0x20")
        self.declare_parameter(
            "bumper_topics",
            ["/bumper/front", "/bumper/rear", "/bumper/left", "/bumper/right"],
        )
        self.declare_parameter("bumper_widths", [0.45, 0.45, 0.4, 0.4])
        self.declare_parameter("bumper_depths", [0.03, 0.03, 0.03, 0.03])
        self.declare_parameter("bumper_heights", [0.06, 0.06, 0.06, 0.06])
        self.declare_parameter(
            "bumper_frame_ids",
            [
                "bumper_front_contact",
                "bumper_rear_contact",
                "bumper_left_contact",
                "bumper_right_contact",
            ],
        )
        self.declare_parameter("corner_pin_indices", [0, 1, 2, 3])

        rate = max(1.0, float(self.get_parameter("publish_rate_hz").value))
        topics = list(self.get_parameter("bumper_topics").value)
        self._widths = list(self.get_parameter("bumper_widths").value)
        self._depths = list(self.get_parameter("bumper_depths").value)
        self._heights = list(self.get_parameter("bumper_heights").value)
        self._frame_ids = list(self.get_parameter("bumper_frame_ids").value)
        pins_idx = [int(x) for x in self.get_parameter("corner_pin_indices").value]
        mcp_address = str(self.get_parameter("mcp_address").value)

        if len(topics) != 4 or len(pins_idx) != 4:
            self.get_logger().error("bumper_topics and corner_pin_indices must have length 4")
            return

        for name, seq in (
            ("bumper_widths", self._widths),
            ("bumper_depths", self._depths),
            ("bumper_heights", self._heights),
            ("bumper_frame_ids", self._frame_ids),
        ):
            if len(seq) != 4:
                self.get_logger().error(f"{name} must have length 4")
                return

        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.mcp = MCP23017(self.i2c, address=int(mcp_address, 16))
        except Exception as e:
            self.get_logger().error(f"MCP23017 init failed: {e}")
            return

        self._pins = []
        for idx in pins_idx:
            pin = self.mcp.get_pin(idx)
            pin.direction = digitalio.Direction.INPUT
            pin.pull = digitalio.Pull.UP
            self._pins.append(pin)

        self._face_pin_groups = (
            (0, 1),
            (2, 3),
            (0, 2),
            (1, 3),
        )

        self._pubs = [self.create_publisher(Bumper, topics[i], 10) for i in range(4)]
        self.create_timer(1.0 / rate, self.timer_callback)
        self.get_logger().info(f"Bumper HW → {topics} ({rate:.0f} Hz)")

    def timer_callback(self):
        if not self._pins:
            return
        corner_contact = [not p.value for p in self._pins]
        stamp = self.get_clock().now().to_msg()

        for face_i, group in enumerate(self._face_pin_groups):
            contact = any(corner_contact[j] for j in group)
            msg = Bumper()
            msg.header.stamp = stamp
            msg.header.frame_id = self._frame_ids[face_i]
            msg.contact = contact
            msg.width = float(self._widths[face_i])
            msg.depth = float(self._depths[face_i])
            msg.height = float(self._heights[face_i])
            self._pubs[face_i].publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = BumperNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
