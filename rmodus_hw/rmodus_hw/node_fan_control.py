import rclpy
from rclpy.node import Node

from my.msg import PiStatus

import numpy as np

from .utils.pwm_control import PWMControl

class FanControlNode(Node):
    def __init__(self):
        super().__init__('fan_control_node')
        
        self.sub = self.create_subscription(PiStatus, 'system/pi_status', self.status_cb, 10)
        
        
        fan_pin = self.declare_parameter('fan_pin', 13).get_parameter_value().integer_value
        frequency = self.declare_parameter('frequency', 10).get_parameter_value().integer_value
        self.min_to_run = self.declare_parameter('min_to_run', 0.25).get_parameter_value().double_value
        self.user_power = self.declare_parameter('user_power', [0.0, 0.5, 1.0]).get_parameter_value().double_array_value

        self.fan = PWMControl(pin=fan_pin, frequency=frequency)
        
        self.temps = np.linspace(0, 100, len(self.user_power))
        for i in range(len(self.user_power)):
            if i < len(self.user_power) - 1:
                if self.user_power[i] == 0 and self.user_power[i+1] > 0:
                    self.user_power[i] = self.min_to_run

    def status_cb(self, msg):
        status_data = msg

        self.fan
        current_temp = status_data.cpu_temperature
        
        speed = np.interp(current_temp, self.temps, self.user_power)
        if 0 < speed <= self.min_to_run:
            speed = 0

        self.fan.set_speed(speed)
        self.get_logger().info(f"Temp: {current_temp}°C -> Speed: {speed*100:.1f}%")

def main(args=None):
    rclpy.init(args=args)
    node = FanControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.disp.power_off()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
