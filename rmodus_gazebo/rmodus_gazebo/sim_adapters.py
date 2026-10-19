"""Small ROS adapters around the Gazebo bridge: odom TF, cliff ranges, flow counts."""

import math

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32MultiArray, Int16MultiArray
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
    """One-ray LaserScan from Gazebo → Float32MultiArray meters on cliff state_topic.

    Index is the profile pin. rmodus_cliff_sensor turns that into sensor_msgs/Range.
    """

    def __init__(self):
        super().__init__("sim_cliff_bridge")
        self._topic = str(self.declare_parameter("state_topic", "/robot/cliffs/range").value)
        names = [str(v) for v in self.declare_parameter("cliff_names", [""]).value]
        pins = [int(v) for v in self.declare_parameter("cliff_pins", [0]).value]
        if not names or names == [""] or len(pins) != len(names):
            self.get_logger().error("cliff name/pin lists must be the same non-empty length")
            return

        self._pins = list(zip(names, pins))
        self._ranges = {name: float("nan") for name in names}
        self._width = max(pins) + 1
        self._pub = self.create_publisher(Float32MultiArray, self._topic, 10)
        for name in names:
            self.create_subscription(
                LaserScan,
                f"/sim/cliff/{name}/scan",
                lambda msg, cliff_name=name: self._on_scan(msg, cliff_name),
                10,
            )
        self.create_timer(0.1, self._publish)
        self.get_logger().info(
            f"Sim cliff raw {self._topic} pins {list(zip(names, pins))} (len {self._width})"
        )

    def _on_scan(self, msg: LaserScan, name: str):
        self._ranges[name] = float(msg.ranges[0]) if msg.ranges else float("nan")

    def _publish(self):
        if not getattr(self, "_pub", None):
            return
        data = [float("nan")] * self._width
        for name, pin in self._pins:
            if 0 <= pin < self._width:
                data[pin] = self._ranges[name]
        out = Float32MultiArray()
        out.data = data
        self._pub.publish(out)


class SimFlowBridge(Node):
    """Planar /odom twist → PMW3901-style [dx, dy] counts on flow motion_topic.

    Counts are pixels over timer_period, in the sensor frame (mount yaw + offset).
    rmodus_flow_sensor applies deadzone, scale and covariance.
    """

    def __init__(self):
        super().__init__("sim_flow_bridge")
        self._topic = str(self.declare_parameter("motion_topic", "/robot/flow/motion").value)
        odom_topic = str(self.declare_parameter("odom_topic", "/odom").value)
        self._yaw = float(self.declare_parameter("mount_yaw", 0.0).value)
        offset = [float(v) for v in self.declare_parameter("mount_offset", [0.0, 0.0, 0.0]).value]
        self._px = offset[0] if offset else 0.0
        self._py = offset[1] if len(offset) > 1 else 0.0
        z_height = float(self.declare_parameter("z_height", 0.025).value)
        fov = math.radians(float(self.declare_parameter("fov_deg", 42.0).value))
        res = float(self.declare_parameter("res_pix", 35).value)
        self._period = float(self.declare_parameter("timer_period", 0.05).value)
        self._cf = 0.0
        if res > 0.0:
            self._cf = (2.0 * z_height * math.tan(fov / 2.0)) / res

        self._vx = 0.0
        self._vy = 0.0
        self._wz = 0.0
        self._pub = self.create_publisher(Int16MultiArray, self._topic, 10)
        self.create_subscription(Odometry, odom_topic, self._on_odom, 10)
        period = self._period if self._period > 0.0 else 0.05
        self.create_timer(period, self._publish)
        self.get_logger().info(f"Sim flow raw {self._topic} from {odom_topic}")

    def _on_odom(self, msg: Odometry):
        self._vx = float(msg.twist.twist.linear.x)
        self._vy = float(msg.twist.twist.linear.y)
        self._wz = float(msg.twist.twist.angular.z)

    def _counts(self, speed: float) -> int:
        if self._cf <= 1e-12 or self._period <= 0.0:
            return 0
        raw = speed * self._period / self._cf
        return int(max(-32767, min(32767, round(raw))))

    def _publish(self):
        if not getattr(self, "_pub", None):
            return
        # Velocity of the mount point in the footprint frame, then into the sensor yaw.
        vx_p = self._vx - self._wz * self._py
        vy_p = self._vy + self._wz * self._px
        cos_yaw = math.cos(self._yaw)
        sin_yaw = math.sin(self._yaw)
        vx_s = vx_p * cos_yaw + vy_p * sin_yaw
        vy_s = -vx_p * sin_yaw + vy_p * cos_yaw
        out = Int16MultiArray()
        out.data = [self._counts(vx_s), self._counts(vy_s)]
        self._pub.publish(out)


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


def main_flow(args=None):
    rclpy.init(args=args)
    node = SimFlowBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
