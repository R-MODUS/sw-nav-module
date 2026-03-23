import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

class SharpSensorNode(Node):
    def __init__(self):
        super().__init__('sharp_sensors_node')
        
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
        # Osetreni limitnich stavu podle grafu
        if voltage > 2.5: # Maximum v grafu je cca 2.45V
            return 0.02
        if voltage < 0.3: # Minimum pro 20cm
            return 0.20
        
        # Aproximace krivky pro Sharp 2-20cm (GP2Y0A41SK0F)
        # Vzorec upraveny podle bodu v grafu: 2V -> cca 2cm, 0.4V -> 15cm
	# 2 to 15 cm
        try:
            # d = a * (V ^ b) - c
            distance_cm = 3.5 * pow(voltage, -0.75) + 0.0
            return distance_cm / 100.0 # Prevod na metry pro ROS 2
        except:
            return -1.0

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
