import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
from scipy.interpolate import CubicSpline
import numpy as np
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

class SharpSensorNode(Node):
    def __init__(self):
        super().__init__('sharp_sensors_node')


        self.declare_parameter('v_points', [0.4, 2.5])
        self.declare_parameter('d_points', [0.20, 0.02])
        self.v_points = self.get_parameter('v_points').value
        self.d_points = self.get_parameter('d_points').value

        if len(self.v_points) != len(self.d_points): # pyright: ignore[reportArgumentType]
            self.get_logger().error("v_points a d_points musí mít stejnou délku!")

        try:
            self.spline = CubicSpline(self.v_points, self.d_points, bc_type='natural')
        except Exception as e:
            self.get_logger().error(f"Chyba při tvorbě splajnu: {e}")
            self.spline = None
        
        # Inicializace I2C a ADS1115
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(self.i2c)
            self.ads.gain = 1
        except Exception as e:
            self.get_logger().error(f"I2C/ADS1115 init failed: {e}")
            return

        # DEFINICE KANÁLŮ POMOCÍ INDEXŮ (0-3)
        # Toto obejde problém s chybějícími atributy P0, P1...
        self.channels = [
            AnalogIn(self.ads, 0),
            AnalogIn(self.ads, 1),
            AnalogIn(self.ads, 2),
            AnalogIn(self.ads, 3)
        ]

        # Zbytek kódu zůstává stejný...
        self.pubs = []
        for i in range(4):
            topic = f'range/sensor_{i}'
            self.pubs.append(self.create_publisher(Range, topic, 10))

        self.timer = self.create_timer(0.1, self.timer_callback)

    def voltage_to_distance(self, voltage):
        if self.spline is None:
            return -1.0
            
        dist_m = float(self.spline(voltage))
        return np.clip(dist_m, min(self.d_points), max(self.d_points)) # pyright: ignore[reportArgumentType]

    def timer_callback(self):
        for i in range(4):
            voltage = self.channels[i].voltage
            dist_m = self.voltage_to_distance(voltage)

            msg = Range()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = f'sensor_{i}_link'
            msg.radiation_type = Range.INFRARED
            msg.field_of_view = 0.05 # cca 3 stupne
            msg.min_range = 0.02
            msg.max_range = 0.20
            msg.range = dist_m

            self.pubs[i].publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = SharpSensorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
