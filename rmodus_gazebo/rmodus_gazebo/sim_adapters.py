"""Small ROS adapters around the Gazebo bridge: odom TF and cliff Range."""

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan, Range
from tf2_ros import TransformBroadcaster


class SimOdomTf(Node):
    """Publish odom → base_footprint from Gazebo odometry (same job as the HW drive node)."""

    def __init__(self):
        super().__init__("sim_odom_tf")
        topic = str(self.declare_parameter("odom_topic", "/odom").value)
        self._tf = TransformBroadcaster(self)
        self.create_subscription(Odometry, topic, self._on_odom, 10)
        self.get_logger().info(f"Sim odom TF from {topic}")

    def _on_odom(self, msg: Odometry):
        out = TransformStamped()
        out.header = msg.header
        if not out.header.frame_id:
            out.header.frame_id = "odom"
        child = msg.child_frame_id or "base_footprint"
        out.child_frame_id = child
        out.transform.translation.x = msg.pose.pose.position.x
        out.transform.translation.y = msg.pose.pose.position.y
        out.transform.translation.z = msg.pose.pose.position.z
        out.transform.rotation = msg.pose.pose.orientation
        self._tf.sendTransform(out)


class SimCliffBridge(Node):
    """One-ray LaserScan from Gazebo → sensor_msgs/Range on the profile topic."""

    def __init__(self):
        super().__init__("sim_cliff_bridge")
        names = list(self.declare_parameter("cliff_names", [""]).value)
        topics = list(self.declare_parameter("cliff_topics", [""]).value)
        frames = list(self.declare_parameter("cliff_frames", [""]).value)
        if not names or any(len(seq) != len(names) for seq in (topics, frames)):
            self.get_logger().error("cliff name/topic/frame lists must be the same length")
            return

        self._pubs = []
        for index, name in enumerate(names):
            pub = self.create_publisher(Range, topics[index], 10)
            self._pubs.append((frames[index], pub))
            self.create_subscription(
                LaserScan,
                f"/sim/cliff/{name}/scan",
                lambda msg, slot=index: self._on_scan(msg, slot),
                10,
            )
        self.get_logger().info(f"Sim cliff bridge: {list(zip(names, topics))}")

    def _on_scan(self, msg: LaserScan, slot: int):
        frame, pub = self._pubs[slot]
        out = Range()
        out.header = msg.header
        if frame:
            out.header.frame_id = frame
        out.radiation_type = Range.INFRARED
        out.field_of_view = 0.02
        out.min_range = float(msg.range_min)
        out.max_range = float(msg.range_max)
        reading = float(msg.ranges[0]) if msg.ranges else float("nan")
        out.range = reading
        pub.publish(out)


def main_odom(args=None):
    rclpy.init(args=args)
    node = SimOdomTf()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main_cliff(args=None):
    rclpy.init(args=args)
    node = SimCliffBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
