"""ADS1115 voltages → /robot/cliffs/range (meters, index = channel)."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray

import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


class CliffHardwareNode(Node):
    def __init__(self):
        super().__init__("cliff_hw_node")

        self.declare_parameter("state_topic", "/robot/cliffs/range")
        self.declare_parameter("address", "0x48")
        self.declare_parameter("timer_period", 0.1)
        self.v_points = self.declare_parameter(
            "v_points", [0.3, 0.4, 0.8, 1.2, 2.0, 2.5]
        ).get_parameter_value().double_array_value
        self.d_points = self.declare_parameter(
            "d_points", [0.20, 0.15, 0.08, 0.05, 0.03, 0.02]
        ).get_parameter_value().double_array_value

        self._topic = str(self.get_parameter("state_topic").value)
        try:
            address = int(str(self.get_parameter("address").value), 16)
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c, address=address)
            ads.gain = 1
        except Exception as exc:
            self.get_logger().error(f"I2C/ADS1115 init failed: {exc}")
            return

        self.channels = [AnalogIn(ads, channel) for channel in range(4)]
        period = float(self.get_parameter("timer_period").value)
        self._pub = self.create_publisher(Float32MultiArray, self._topic, 10)
        self.create_timer(period, self._publish)
        self.get_logger().info(f"Cliff ADS1115 → {self._topic} channels 0..3")

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

            distance_cm = 3.5 * pow(voltage, -0.75)
            return distance_cm / 100.0
        except Exception:
            return -1.0

    def _publish(self):
        if not getattr(self, "_pub", None):
            return
        out = Float32MultiArray()
        out.data = [float(self.voltage_to_distance(channel.voltage)) for channel in self.channels]
        self._pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = CliffHardwareNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
