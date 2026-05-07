import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

from rmodus_interface.msg import Bumper


class BumperSafetyStopNode(Node):
    def __init__(self):
        super().__init__('bumper_safety_stop')

        self.declare_parameter('enabled', True)
        self.declare_parameter('hold_time_sec', 5.0)
        self.declare_parameter('publish_rate_hz', 50.0)
        self.declare_parameter('sensor_discovery_rate_hz', 1.0)
        self.declare_parameter('bumper_topic_prefix', '/bumper/')
        self.declare_parameter('retrigger_while_contact', False)
        self.declare_parameter('cmd_vel_input_topic', '/cmd_vel')
        self.declare_parameter('cmd_vel_output_topic', '/cmd_vel_safe')
        self.declare_parameter('vector_input_topic', '/vector')
        self.declare_parameter('vector_output_topic', '/vector_safe')
        self.declare_parameter('bumper_topics', ['/bumper/front', '/bumper/rear', '/bumper/left', '/bumper/right'])

        self.enabled = bool(self.get_parameter('enabled').value)
        self.hold_time_sec = max(0.0, float(self.get_parameter('hold_time_sec').value))
        self.publish_rate_hz = max(1.0, float(self.get_parameter('publish_rate_hz').value))
        self.sensor_discovery_rate_hz = max(0.1, float(self.get_parameter('sensor_discovery_rate_hz').value))
        self.bumper_topic_prefix = str(self.get_parameter('bumper_topic_prefix').value)
        self.retrigger_while_contact = bool(self.get_parameter('retrigger_while_contact').value)
        self.cmd_vel_input_topic = str(self.get_parameter('cmd_vel_input_topic').value)
        self.cmd_vel_output_topic = str(self.get_parameter('cmd_vel_output_topic').value)
        self.vector_input_topic = str(self.get_parameter('vector_input_topic').value)
        self.vector_output_topic = str(self.get_parameter('vector_output_topic').value)
        self.initial_bumper_topics = list(self.get_parameter('bumper_topics').value)

        self._hold_until_sec = 0.0
        self._sensor_subscriptions = []
        self._subscribed_bumper_topics = set()
        self._last_contact_by_topic = {}
        self._zero_twist = Twist()
        self._last_cmd_vel = Twist()
        self._last_vector = Twist()

        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_output_topic, 10)
        self.vector_pub = self.create_publisher(Twist, self.vector_output_topic, 10)
        self.cmd_vel_sub = self.create_subscription(Twist, self.cmd_vel_input_topic, self._cmd_vel_callback, 10)
        self.vector_sub = self.create_subscription(Twist, self.vector_input_topic, self._vector_callback, 10)

        for topic in self.initial_bumper_topics:
            self._register_bumper_topic(topic)

        self._discover_dynamic_topics()
        self.create_timer(1.0 / self.sensor_discovery_rate_hz, self._discover_dynamic_topics)
        self.create_timer(1.0 / self.publish_rate_hz, self._publish_stop_if_active)
        self.get_logger().info(
            'Bumper safety gate active: '
            f'{self.cmd_vel_input_topic}->{self.cmd_vel_output_topic}, '
            f'{self.vector_input_topic}->{self.vector_output_topic}, '
            f'hold={self.hold_time_sec}s at {self.publish_rate_hz} Hz, '
            f'retrigger_while_contact={self.retrigger_while_contact}'
        )

    def _register_bumper_topic(self, topic_name):
        if topic_name in self._subscribed_bumper_topics:
            return
        self._sensor_subscriptions.append(
            self.create_subscription(
                Bumper,
                topic_name,
                lambda msg, t=topic_name: self._bumper_callback(msg, t),
                10,
            )
        )
        self._subscribed_bumper_topics.add(topic_name)
        self._last_contact_by_topic[topic_name] = False
        self.get_logger().info(f'Subscribed bumper topic: {topic_name}')

    def _discover_dynamic_topics(self):
        for topic_name, topic_types in self.get_topic_names_and_types():
            if topic_name.startswith(self.bumper_topic_prefix) and 'rmodus_interface/msg/Bumper' in topic_types:
                self._register_bumper_topic(topic_name)

    def _bumper_callback(self, msg, topic_name):
        previous_contact = bool(self._last_contact_by_topic.get(topic_name, False))
        current_contact = bool(msg.contact)
        self._last_contact_by_topic[topic_name] = current_contact

        if not self.enabled or not current_contact:
            return

        if not self.retrigger_while_contact and previous_contact:
            return

        now_sec = self.get_clock().now().nanoseconds / 1e9
        self._hold_until_sec = max(self._hold_until_sec, now_sec + self.hold_time_sec)
        self.get_logger().warn(f'Bumper contact on {topic_name}, forcing stop for {self.hold_time_sec:.2f}s')

    def _stop_active(self):
        if not self.enabled:
            return False
        now_sec = self.get_clock().now().nanoseconds / 1e9
        return now_sec < self._hold_until_sec

    def _cmd_vel_callback(self, msg):
        self._last_cmd_vel = msg
        if self._stop_active():
            self.cmd_vel_pub.publish(self._zero_twist)
            return
        self.cmd_vel_pub.publish(msg)

    def _vector_callback(self, msg):
        self._last_vector = msg
        if self._stop_active():
            self.vector_pub.publish(self._zero_twist)
            return
        self.vector_pub.publish(msg)

    def _publish_stop_if_active(self):
        if self._stop_active():
            self.cmd_vel_pub.publish(self._zero_twist)
            self.vector_pub.publish(self._zero_twist)


def main(args=None):
    rclpy.init(args=args)
    node = BumperSafetyStopNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
