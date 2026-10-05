"""Repeat the Gazebo Teleop card onto the mux input.

The gz-gui Teleop widget publishes one Twist per click. twist_mux forgets a
source 0.5 s after its last message, and a held zero on the teleop input would
block Nav. This node latches the last command, repeats it while it is non-zero,
and after a stop publishes zeros only long enough for the robot to halt.
"""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


def _is_zero(msg: Twist) -> bool:
    return (
        abs(msg.linear.x) < 1e-4
        and abs(msg.linear.y) < 1e-4
        and abs(msg.linear.z) < 1e-4
        and abs(msg.angular.x) < 1e-4
        and abs(msg.angular.y) < 1e-4
        and abs(msg.angular.z) < 1e-4
    )


class SimTeleopRepeat(Node):
    def __init__(self):
        super().__init__("sim_teleop_repeat")
        src = str(self.declare_parameter("input_topic", "/sim_gui/cmd_vel").value)
        dst = str(self.declare_parameter("output_topic", "/teleop/cmd_vel").value)
        rate = float(self.declare_parameter("rate", 20.0).value)
        self._release_sec = float(self.declare_parameter("release_sec", 0.6).value)
        if rate <= 0.0:
            rate = 20.0

        self._cmd = Twist()
        self._holding = False
        self._zero_since = None
        self._pub = self.create_publisher(Twist, dst, 10)
        self.create_subscription(Twist, src, self._on_cmd, 10)
        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(f"Sim teleop {src} → {dst} at {rate:.0f} Hz")

    def _on_cmd(self, msg: Twist):
        self._cmd = msg
        self._holding = True
        if _is_zero(msg):
            if self._zero_since is None:
                self._zero_since = self.get_clock().now()
        else:
            self._zero_since = None

    def _tick(self):
        if not self._holding:
            return
        if self._zero_since is not None:
            elapsed = (self.get_clock().now() - self._zero_since).nanoseconds * 1e-9
            if elapsed >= self._release_sec:
                self._holding = False
                self._zero_since = None
                return
        self._pub.publish(self._cmd)


def main(args=None):
    rclpy.init(args=args)
    node = SimTeleopRepeat()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
