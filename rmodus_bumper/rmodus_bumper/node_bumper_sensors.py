"""Map ESP bumper index array onto one rmodus_interface/Bumper topic per item."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import UInt8MultiArray

from rmodus_interface.msg import Bumper


class BumperNode(Node):
    """Subscribe to /robot/bumpers/state and publish /bumper/<name>."""

    def __init__(self):
        super().__init__("bumper_sensors_node")

        self.declare_parameter("state_topic", "/robot/bumpers/state")
        self.declare_parameter("bumper_indices", [0])
        self.declare_parameter("bumper_topics", ["/bumper/front"])
        self.declare_parameter("bumper_frame_ids", ["bumper_front_contact"])
        self.declare_parameter("bumper_widths", [0.30])
        self.declare_parameter("bumper_depths", [0.02])
        self.declare_parameter("bumper_heights", [0.05])

        state_topic = str(self.get_parameter("state_topic").value)
        self._indices = [int(v) for v in self.get_parameter("bumper_indices").value]
        topics = [str(v) for v in self.get_parameter("bumper_topics").value]
        self._frames = [str(v) for v in self.get_parameter("bumper_frame_ids").value]
        self._widths = [float(v) for v in self.get_parameter("bumper_widths").value]
        self._depths = [float(v) for v in self.get_parameter("bumper_depths").value]
        self._heights = [float(v) for v in self.get_parameter("bumper_heights").value]

        count = len(self._indices)
        if not count or any(
            len(seq) != count
            for seq in (topics, self._frames, self._widths, self._depths, self._heights)
        ):
            self.get_logger().error("bumper index/topic/frame/size lists must be the same length")
            self._pubs = []
            return

        self._pubs = [self.create_publisher(Bumper, topics[i], 10) for i in range(count)]
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.create_subscription(UInt8MultiArray, state_topic, self._on_state, qos)
        self.get_logger().info(
            f"Bumper bridge {state_topic} index {self._indices} → {topics}"
        )

    def _on_state(self, msg: UInt8MultiArray):
        if not self._pubs:
            return
        stamp = self.get_clock().now().to_msg()
        values = list(msg.data)
        for i, index in enumerate(self._indices):
            if index < 0 or index >= len(values):
                continue
            out = Bumper()
            out.header.stamp = stamp
            out.header.frame_id = self._frames[i]
            out.contact = bool(int(values[index]))
            out.width = self._widths[i]
            out.depth = self._depths[i]
            out.height = self._heights[i]
            self._pubs[i].publish(out)


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
