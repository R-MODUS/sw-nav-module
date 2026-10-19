"""Map a range array onto one sensor_msgs/Range topic per cliff."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Float32MultiArray


class SharpSensorNode(Node):
    """Subscribe to /robot/cliffs/range and publish /cliff/<name>."""

    def __init__(self):
        super().__init__("cliff_sensors_node")

        default_topics = ["/cliff/fl", "/cliff/fr", "/cliff/rl", "/cliff/rr"]
        default_frames = [
            "cliff_sensor_fl_beam",
            "cliff_sensor_fr_beam",
            "cliff_sensor_rl_beam",
            "cliff_sensor_rr_beam",
        ]
        self.declare_parameter("state_topic", "/robot/cliffs/range")
        self.declare_parameter("cliff_indices", [0, 1, 2, 3])
        self.declare_parameter("cliff_topics", default_topics)
        self.declare_parameter("cliff_frame_ids", default_frames)
        self.declare_parameter("range_msg_min", 0.02)
        self.declare_parameter("range_msg_max", 0.5)
        self.declare_parameter("field_of_view", 0.05)

        state_topic = str(self.get_parameter("state_topic").value)
        self._indices = [int(v) for v in self.get_parameter("cliff_indices").value]
        topics = [str(v) for v in self.get_parameter("cliff_topics").value]
        self._frames = [str(v) for v in self.get_parameter("cliff_frame_ids").value]
        count = len(self._indices)
        if not count or any(len(seq) != count for seq in (topics, self._frames)):
            self.get_logger().error("cliff index/topic/frame lists must be the same length")
            self._pubs = []
            return

        self._range_min = float(self.get_parameter("range_msg_min").value)
        self._range_max = float(self.get_parameter("range_msg_max").value)
        self._fov = float(self.get_parameter("field_of_view").value)
        self._pubs = [self.create_publisher(Range, topics[i], 10) for i in range(count)]
        self.create_subscription(Float32MultiArray, state_topic, self._on_ranges, 10)
        self.get_logger().info(f"Cliff bridge {state_topic} index {self._indices} → {topics}")

    def _on_ranges(self, msg: Float32MultiArray):
        if not self._pubs:
            return
        stamp = self.get_clock().now().to_msg()
        values = list(msg.data)
        for i, index in enumerate(self._indices):
            if index < 0 or index >= len(values):
                continue
            out = Range()
            out.header.stamp = stamp
            out.header.frame_id = self._frames[i]
            out.radiation_type = Range.INFRARED
            out.field_of_view = self._fov
            out.min_range = self._range_min
            out.max_range = self._range_max
            out.range = float(values[index])
            self._pubs[i].publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = SharpSensorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
