import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import TransformStamped
import tf2_ros

import math
import time
import numpy as np
import threading

from .utils.lidar import Lidar
from .utils.pwm_control import PWMControl

class LidarScanPublisher(Node):
    def __init__(self):
        super().__init__('lidar_scan_publisher')

        # Deklarace
        self.declare_parameter('frame_id', 'lidar')
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('frequency', 10_000)
        self.declare_parameter('motor_pin', 19)
        self.declare_parameter('target_rpm', 300)
        self.declare_parameter('range_max', 5.0)
        self.declare_parameter('range_min', 0.05)
        self.declare_parameter('angle_min', 0.0)
        self.declare_parameter('angle_max', 2 * np.pi)
    
        # Získání hodnot
        self.frame_id = self.get_parameter('frame_id').value
        port = self.get_parameter('port').value
        frequency = self.get_parameter('frequency').value
        motor_pin = self.get_parameter('motor_pin').value

        self.target_rpm = self.get_parameter('target_rpm').value
        self.range_max = self.get_parameter('range_max').value
        self.range_min = self.get_parameter('range_min').value
        self.angle_min = self.get_parameter('angle_min').value
        self.angle_max = self.get_parameter('angle_max').value

        # ROS2 Funkce
        self.publisher_ = self.create_publisher(LaserScan, 'scan', qos_profile_sensor_data)

        # moje Funkce
        self.lidar = Lidar(port=port)
        self.motor = PWMControl(pin=motor_pin, frequency=frequency)
        self.motor.set_speed(1)

        self.last_scan = None
        threading.Thread(target=self.lidar_loop, daemon=True).start()
        self.timer = self.create_timer(0.2, self.publish_scan)

        self.get_logger().info("LidarScanPublisher started...")

    def lidar_loop(self):
        while rclpy.ok():
            try:
                # startZero=True umí navždy čekat na úhel 0 při špatných datech; False je robustnější
                ranges, intensities, rpm, scan_time = self.lidar.get_scan(startZero=False, max_seconds=30.0)
                self.last_scan = (ranges, intensities, rpm, scan_time)
                self.get_logger().info(f'{round(1/scan_time, 2)} Hz, RPM: {rpm}')
            except TimeoutError as e:
                self.get_logger().error(str(e))
                time.sleep(1.0)
            except Exception as e:
                self.get_logger().error(f'LiDAR vlákno: {type(e).__name__}: {e}')
                time.sleep(1.0)

    def publish_scan(self):
        if not self.last_scan:
            self.get_logger().warn('Empty self.last_scan')
            return
        ranges, intensities, rpm, scan_time = self.last_scan
        scan_msg = LaserScan()
        scan_msg.header.stamp = self.get_clock().now().to_msg()
        scan_msg.header.frame_id = self.frame_id
        scan_msg.angle_min = self.angle_min
        scan_msg.angle_max = self.angle_max
        scan_msg.angle_increment = np.deg2rad(1.0)
        scan_msg.scan_time = scan_time
        scan_msg.time_increment = scan_time / 360.0
        scan_msg.range_min = self.range_min
        scan_msg.range_max = self.range_max
        scan_msg.ranges = [float(x) for x in ranges]
        scan_msg.intensities = [float(x) for x in intensities]
        self.publisher_.publish(scan_msg)

def main(args=None):
    rclpy.init(args=args)
    node = LidarScanPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
