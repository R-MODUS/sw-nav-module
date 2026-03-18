import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

from .utils.UART import UART

class Motors(Node):
    def __init__(self):
        super().__init__('vector_maker')
        self.subscription = self.create_subscription(
        Twist, '/vector', self.callback_vector, 1
        )

        uart = self.declare_parameter('port', '/dev/serial0').get_parameter_value().string_value
        self.max_speed = self.declare_parameter('max_speed', 300).get_parameter_value().integer_value

        self.uart = UART(port=uart)

    def callback_vector(self, twist: Twist):
        # x -> + dopredu, - dozadu
        # y -> + doprava, - doleva
        # z -> + CCW, - CW

        speed = {
            'FL': twist.linear.x - twist.linear.y - twist.angular.z,
            'FR': twist.linear.x + twist.linear.y + twist.angular.z,
            'RL': twist.linear.x + twist.linear.y - twist.angular.z,
            'RR': twist.linear.x - twist.linear.y + twist.angular.z,
        }

        # Normalizace na MAX_MOTOR_SPEED
        max_val = max(abs(v) for v in speed.values())
        if max_val > 1:
            for k in speed:
                speed[k] /= max_val

        for k in speed:
            speed[k] *= self.max_speed

        final_speeds = []
        directions = []
        for k in ['FL', 'FR', 'RL', 'RR']:
            raw_speed = round(speed[k])
            direction = 0 if raw_speed >= 0 else 1   # 0 = dopředu, 1 = dozadu
            abs_speed = abs(raw_speed)               # převedeno na 0-255
            final_speeds.append(abs_speed)
            directions.append(direction)

        msg = final_speeds + directions
        self.uart.send_packet(msg)
        self.get_logger().info(str(msg))

def main(args=None):
    rclpy.init(args=args)
    node = Motors()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    rclpy.shutdown()

if __name__ == '__main__':
    main()
