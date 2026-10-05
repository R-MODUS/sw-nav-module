"""PMW3901 motion counts → /robot/flow/motion as Int16MultiArray [dx, dy]."""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int16MultiArray
from pmw3901 import PMW3901, BG_CS_FRONT_BCM


class FlowHardwareNode(Node):
    def __init__(self):
        super().__init__("flow_hw_node")

        self.declare_parameters(
            namespace="",
            parameters=[
                ("spi_port", 0),
                ("spi_cs", 0),
                ("timer_period", 0.05),
                ("motion_topic", "/robot/flow/motion"),
            ],
        )

        port = int(self.get_parameter("spi_port").value)
        cs = int(self.get_parameter("spi_cs").value)
        period = float(self.get_parameter("timer_period").value)
        topic = str(self.get_parameter("motion_topic").value)

        try:
            spi_cs_pin = cs if cs != 0 else BG_CS_FRONT_BCM
            self.sensor = PMW3901(spi_port=port, spi_cs=spi_cs_pin)
            self.sensor.set_rotation(0)
            self.get_logger().info(f"PMW3901 on SPI{port} CS{spi_cs_pin} → {topic}")
        except Exception as exc:
            self.get_logger().error(f"HW init failed: {exc}")
            raise exc

        self._pub = self.create_publisher(Int16MultiArray, topic, 10)
        self.create_timer(period if period > 0.0 else 0.05, self._publish)

    def _publish(self):
        try:
            dx, dy = self.sensor.get_motion()
        except RuntimeError:
            return
        except Exception as exc:
            self.get_logger().warn(f"flow error: {exc}")
            return
        out = Int16MultiArray()
        out.data = [
            int(max(-32767, min(32767, int(dx)))),
            int(max(-32767, min(32767, int(dy)))),
        ]
        self._pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = FlowHardwareNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
