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

        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(self.i2c)
            self.ads.gain = 1
        except Exception as e:
            self.get_logger().error(f"I2C/ADS1115 init failed: {e}")
            return

        self.channels = [
            AnalogIn(self.ads, 0),
            AnalogIn(self.ads, 1),
            AnalogIn(self.ads, 2),
            AnalogIn(self.ads, 3),
        ]

        default_topics = ['/cliff/fl', '/cliff/fr', '/cliff/rl', '/cliff/rr']
        default_frames = [
            'cliff_sensor_fl_beam', 'cliff_sensor_fr_beam',
            'cliff_sensor_rl_beam', 'cliff_sensor_rr_beam',
        ]
        self.declare_parameter('cliff_topics', default_topics)
        self.declare_parameter('cliff_frame_ids', default_frames)
        self.declare_parameter('range_msg_min', 0.02)
        self.declare_parameter('range_msg_max', 0.5)
        self.declare_parameter('field_of_view', 0.05)
        self.declare_parameter('timer_period', 0.1)
        self.v_points = self.declare_parameter('v_points', [0.3, 0.4, 0.8, 1.2, 2.0, 2.5]).get_parameter_value().double_array_value
        self.d_points = self.declare_parameter('d_points', [0.20, 0.15, 0.08, 0.05, 0.03, 0.02]).get_parameter_value().double_array_value

        cliff_topics = list(self.get_parameter('cliff_topics').value)
        cliff_frames = list(self.get_parameter('cliff_frame_ids').value)
        if len(cliff_topics) != 4 or len(cliff_frames) != 4:
            self.get_logger().error('cliff_topics and cliff_frame_ids must each have length 4')
            return

        self._range_min = float(self.get_parameter('range_msg_min').value)
        self._range_max = float(self.get_parameter('range_msg_max').value)
        self._fov = float(self.get_parameter('field_of_view').value)
        period = float(self.get_parameter('timer_period').value)

        self.pubs = [self.create_publisher(Range, cliff_topics[i], 10) for i in range(4)]
        self._cliff_frames = cliff_frames

        self.create_timer(period, self.timer_callback)
        self.get_logger().info(f'Cliff Sharp → topics {cliff_topics}')

    def voltage_to_distance(self, voltage):
        if voltage > 2.5:
            return 0.02
        if voltage < 0.3:
            return 0.20

        try:
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

            distance_cm = 3.5 * pow(voltage, -0.75) + 0.0
            return distance_cm / 100.0
        except Exception:
            return -1.0

    def timer_callback(self):
        if not self.pubs:
            return
        for i in range(4):
            voltage = self.channels[i].voltage
            dist_m = self.voltage_to_distance(voltage)

            msg = Range()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self._cliff_frames[i]
            msg.radiation_type = Range.INFRARED
            msg.field_of_view = self._fov
            msg.min_range = self._range_min
            msg.max_range = self._range_max
            msg.range = float(dist_m)

            self.pubs[i].publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SharpSensorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
