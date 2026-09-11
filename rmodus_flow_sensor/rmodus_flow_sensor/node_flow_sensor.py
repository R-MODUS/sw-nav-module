import rclpy
from rclpy.node import Node
import numpy as np
from geometry_msgs.msg import TwistWithCovarianceStamped
from pmw3901 import PMW3901, BG_CS_FRONT_BCM


class OpticalFlowTwistPublisher(Node):
    def __init__(self):
        super().__init__("optical_flow_node")

        self.declare_parameters(
            namespace="",
            parameters=[
                ("spi_port", 0),
                ("spi_cs", 0),
                ("deadzone", 3),
                ("timer_period", 0.05),
                ("topic", "/visual_flow/data"),
                ("frame_id", "flow_sensor_link"),
                ("z_height", 0.025),
                ("fov_deg", 42.0),
                ("res_pix", 35),
            ],
        )

        port = self.get_parameter("spi_port").value
        cs = self.get_parameter("spi_cs").value
        self.deadzone = self.get_parameter("deadzone").value
        self.timer_period = self.get_parameter("timer_period").value
        self.sensor_frame = self.get_parameter("frame_id").value
        topic = str(self.get_parameter("topic").value)
        self.z_height = self.get_parameter("z_height").value
        self.fov_rad = np.radians(self.get_parameter("fov_deg").value)
        self.res_pix = self.get_parameter("res_pix").value

        try:
            spi_cs_pin = cs if cs != 0 else BG_CS_FRONT_BCM
            self.sensor = PMW3901(spi_port=port, spi_cs=spi_cs_pin)
            self.sensor.set_rotation(0)
            self.get_logger().info(f"PMW3901 on SPI{port} CS{spi_cs_pin}")
        except Exception as e:
            self.get_logger().error(f"HW init failed: {e}")
            raise e

        self.publisher_ = self.create_publisher(TwistWithCovarianceStamped, topic, 10)
        self.timer = self.create_timer(self.timer_period, self.timer_callback)

    def timer_callback(self):
        try:
            dx, dy = self.sensor.get_motion()
            raw_x = float(dx) if abs(dx) >= self.deadzone else 0.0
            raw_y = float(dy) if abs(dy) >= self.deadzone else 0.0
            cf = (2.0 * self.z_height * np.tan(self.fov_rad / 2.0)) / self.res_pix
            vx = (raw_x * cf) / self.timer_period
            vy = (raw_y * cf) / self.timer_period

            msg = TwistWithCovarianceStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self.sensor_frame
            msg.twist.twist.linear.x = vx
            msg.twist.twist.linear.y = vy
            covariance = [0.0] * 36
            covariance[0] = 0.01
            covariance[7] = 0.01
            covariance[35] = 100.0
            msg.twist.covariance = covariance
            self.publisher_.publish(msg)
        except RuntimeError:
            pass
        except Exception as e:
            self.get_logger().warn(f"flow error: {e}")


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
