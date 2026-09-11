import threading
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan

from neato_lidar.utils.lidar import Lidar
from neato_lidar.utils.pwm_control import PWMControl


class NeatoLidarNode(Node):
    """Publish Neato LDS scans as sensor_msgs/LaserScan."""

    def __init__(self):
        super().__init__("neato_lidar")

        self.declare_parameter("frame_id", "lidar_beam")
        self.declare_parameter("topic", "/scan")
        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("frequency", 10_000)
        self.declare_parameter("motor_pin", 19)
        self.declare_parameter("target_rpm", 300)
        self.declare_parameter("range_max", 5.0)
        self.declare_parameter("range_min", 0.05)
        self.declare_parameter("angle_min", 0.0)
        self.declare_parameter("angle_max", float(2 * np.pi))

        self.frame_id = str(self.get_parameter("frame_id").value)
        topic = str(self.get_parameter("topic").value)
        port = str(self.get_parameter("port").value)
        frequency = int(self.get_parameter("frequency").value)
        motor_pin = int(self.get_parameter("motor_pin").value)

        self.target_rpm = self.get_parameter("target_rpm").value
        self.range_max = float(self.get_parameter("range_max").value)
        self.range_min = float(self.get_parameter("range_min").value)
        self.angle_min = float(self.get_parameter("angle_min").value)
        self.angle_max = float(self.get_parameter("angle_max").value)

        # Nav2 / RViz typically expect RELIABLE on /scan
        scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.publisher_ = self.create_publisher(LaserScan, topic, scan_qos)

        self.lidar = Lidar(port=port)
        self.motor = PWMControl(pin=motor_pin, frequency=frequency)
        self.motor.set_speed(1.0)

        self.last_scan = None
        threading.Thread(target=self._lidar_loop, daemon=True).start()
        self.create_timer(0.2, self._publish_scan)
        self.get_logger().info(f"neato_lidar: {port} → {topic} (frame={self.frame_id})")

    def _lidar_loop(self):
        while rclpy.ok():
            try:
                ranges, intensities, rpm, scan_time = self.lidar.get_scan(
                    startZero=False, max_seconds=30.0
                )
                self.last_scan = (ranges, intensities, rpm, scan_time)
                self.get_logger().info(f"{round(1 / scan_time, 2)} Hz, RPM: {rpm}")
            except TimeoutError as e:
                self.get_logger().error(str(e))
                time.sleep(1.0)
            except Exception as e:
                self.get_logger().error(f"LiDAR thread: {type(e).__name__}: {e}")
                time.sleep(1.0)

    def _publish_scan(self):
        if not self.last_scan:
            return
        ranges, intensities, rpm, scan_time = self.last_scan
        scan_msg = LaserScan()
        scan_msg.header.stamp = self.get_clock().now().to_msg()
        scan_msg.header.frame_id = self.frame_id
        scan_msg.angle_min = self.angle_min
        scan_msg.angle_max = self.angle_max
        scan_msg.angle_increment = np.deg2rad(1.0)
        scan_msg.scan_time = float(scan_time)
        scan_msg.time_increment = float(scan_time) / 360.0
        scan_msg.range_min = self.range_min
        scan_msg.range_max = self.range_max
        scan_msg.ranges = [float(x) for x in ranges]
        scan_msg.intensities = [float(x) for x in intensities]
        self.publisher_.publish(scan_msg)

    def destroy_node(self):
        try:
            self.motor.stop()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = NeatoLidarNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
