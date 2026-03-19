import rclpy
from rclpy.node import Node

from rmodus_interface.msg import PiStatus

import psutil
import subprocess

class SystemMonitorNode(Node):
    def __init__(self):
        super().__init__('system_monitor_node')
        self.publisher_ = self.create_publisher(PiStatus, 'system/pi_status', 10)
        self.timer = self.create_timer(1.0, self.timer_callback)

        self.get_logger().info('System Monitor Node running...')

    def get_cpu_temp(self):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = int(f.read()) / 1000.0
                return temp
        except FileNotFoundError:
            return 0.0

    def timer_callback(self):
        msg = PiStatus()
        
        # Sběr dat pomocí psutil
        msg.cpu_usage_percent = psutil.cpu_percent()
        msg.ram_usage_percent = psutil.virtual_memory().percent
        msg.cpu_temperature = self.get_cpu_temp()
        
        self.publisher_.publish(msg)
        self.get_logger().info(f'CPU: {msg.cpu_usage_percent:.1f}% | RAM: {msg.ram_usage_percent:.1f}% | Temp: {msg.cpu_temperature:.1f}°C')

def main(args=None):
    rclpy.init(args=args)
    node = SystemMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()