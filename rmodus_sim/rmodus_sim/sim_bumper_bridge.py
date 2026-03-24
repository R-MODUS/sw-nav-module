import rclpy
from rclpy.node import Node
from ros_gz_interfaces.msg import Contacts
from rmodus_interface.msg import Bumper

class SimBumperBridge(Node):
    def __init__(self):
        super().__init__('sim_bumper_bridge')
        
        self.declare_parameter('bumper_names', rclpy.Parameter.Type.STRING_ARRAY)
        bumper_names = self.get_parameter('bumper_names').value
        
        self.bumper_states = {}
        self.publishers_ = {}

        if bumper_names is None:
            self.get_logger().warn('Nenalezen žádný název nárazníku v parametrech. Očekávám pole "bumper_names".')
            return

        for name in bumper_names:
            self.publishers_[name] = self.create_publisher(Bumper, f'/bumper/{name}', 10)
            self.bumper_states[name] = False
            # Odebíráme data z bridge (ten už běží díky dynamickému configu v launchi)
            self.create_subscription(
                Contacts,
                f'/bumper/{name}/contact',
                lambda msg, n=name: self.gz_contact_callback(msg, n),
                10
            )

        # Timer pro pravidelný "heartbeat" (10 Hz)
        self.create_timer(0.1, self.publish_all_states)
        self.get_logger().info(f'Sim bumper bridge spuštěn pro: {bumper_names}')

    def gz_contact_callback(self, msg, name):
        # Aktualizace stavu: True pokud je v poli aspoň jeden kontakt
        self.bumper_states[name] = len(msg.contacts) > 0

    def publish_all_states(self):
        for name, state in self.bumper_states.items():
            msg = Bumper()
            msg.contact = state
            # msg.header.stamp = self.get_clock().now().to_msg()
            self.publishers_[name].publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = SimBumperBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()