import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

class SharpSensorNode(Node):
    def __init__(self):
        super().__init__('cliff_sensors_node')
        
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

        self.v_points = self.declare_parameter(
            'v_points', [0.3, 0.4, 0.8, 1.2, 2.0, 2.5]
        ).get_parameter_value().double_array_value
        self.d_points = self.declare_parameter(
            'd_points', [0.20, 0.15, 0.08, 0.05, 0.03, 0.02]
        ).get_parameter_value().double_array_value

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
            # Piecewise linear interpolation from calibration points.
            if len(self.v_points) >= 2 and len(self.v_points) == len(self.d_points):
                for i in range(len(self.v_points) - 1):
                    v0 = float(self.v_points[i])
                    v1 = float(self.v_points[i + 1])
                    d0 = float(self.d_points[i])
                    d1 = float(self.d_points[i + 1])
                    if (v0 <= voltage <= v1) or (v1 <= voltage <= v0):
                        if abs(v1 - v0) < 1e-9:
                            return d0
                        ratio = (voltage - v0) / (v1 - v0)
                        return d0 + ratio * (d1 - d0)

                if voltage <= min(self.v_points):
                    idx = self.v_points.index(min(self.v_points))
                    return float(self.d_points[idx])
                idx = self.v_points.index(max(self.v_points))
                return float(self.d_points[idx])

            # Fallback approximation if calibration is invalid.
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
