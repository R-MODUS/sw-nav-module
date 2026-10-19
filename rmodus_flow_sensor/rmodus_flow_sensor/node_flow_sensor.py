"""Map PMW3901 pixel counts onto TwistWithCovarianceStamped."""

import rclpy
from rclpy.node import Node
import numpy as np
from geometry_msgs.msg import TwistWithCovarianceStamped
from std_msgs.msg import Int16MultiArray


class OpticalFlowTwistPublisher(Node):
    def __init__(self):
        super().__init__("optical_flow_node")

        self.declare_parameters(
            namespace="",
            parameters=[
                ("motion_topic", "/robot/flow/motion"),
                ("deadzone", 3),
                ("timer_period", 0.05),
                ("topic", "/visual_flow/data"),
                ("frame_id", "flow_sensor_link"),
                ("z_height", 0.025),
                ("fov_deg", 42.0),
                ("res_pix", 35),
            ],
        )

        self.deadzone = int(self.get_parameter("deadzone").value)
        self.timer_period = float(self.get_parameter("timer_period").value)
        self.sensor_frame = str(self.get_parameter("frame_id").value)
        topic = str(self.get_parameter("topic").value)
        motion_topic = str(self.get_parameter("motion_topic").value)
        self.z_height = float(self.get_parameter("z_height").value)
        self.fov_rad = np.radians(float(self.get_parameter("fov_deg").value))
        self.res_pix = float(self.get_parameter("res_pix").value)

        self.publisher_ = self.create_publisher(TwistWithCovarianceStamped, topic, 10)
        self.create_subscription(Int16MultiArray, motion_topic, self._on_motion, 10)
        self.get_logger().info(f"Flow bridge {motion_topic} → {topic}")

    def _on_motion(self, msg: Int16MultiArray):
        if len(msg.data) < 2 or self.timer_period <= 0.0 or self.res_pix <= 0.0:
            return
        dx = int(msg.data[0])
        dy = int(msg.data[1])
        raw_x = float(dx) if abs(dx) >= self.deadzone else 0.0
        raw_y = float(dy) if abs(dy) >= self.deadzone else 0.0
        cf = (2.0 * self.z_height * np.tan(self.fov_rad / 2.0)) / self.res_pix
        vx = (raw_x * cf) / self.timer_period
        vy = (raw_y * cf) / self.timer_period

        out = TwistWithCovarianceStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = self.sensor_frame
        out.twist.twist.linear.x = float(vx)
        out.twist.twist.linear.y = float(vy)
        covariance = [0.0] * 36
        covariance[0] = 0.01
        covariance[7] = 0.01
        covariance[35] = 100.0
        out.twist.covariance = covariance
        self.publisher_.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = OpticalFlowTwistPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
