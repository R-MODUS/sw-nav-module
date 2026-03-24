import rclpy
from rclpy.node import Node
from ros_gz_interfaces.msg import Contacts
from rmodus_interface.msg import Bumper
import time

class SimBumperBridge(Node):
    def __init__(self):
        super().__init__('sim_bumper_bridge')
        
        self.declare_parameter('bumper_names', rclpy.Parameter.Type.STRING_ARRAY)
        bumper_names = self.get_parameter('bumper_names').value
        
        self.last_contact_time = {} # Tady budeme držet čas posledního "True"
        self.publishers_ = {}

        if not bumper_names:
            self.get_logger().warn('Nenalezen žádný název nárazníku.')
            return

        for name in bumper_names:
            self.publishers_[name] = self.create_publisher(Bumper, f'/bumper/{name}', 10)
            self.last_contact_time[name] = 0.0 # Inicializace
            
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
        # Pokud přišla zpráva a obsahuje kontakty, uložíme si aktuální čas simulace
        if len(msg.contacts) > 0:
            # Použijeme čas simulace z ROSu (aby to fungovalo i při pauze v GZ)
            self.last_contact_time[name] = self.get_clock().now().nanoseconds / 1e9

    def publish_all_states(self):
        current_time = self.get_clock().now().nanoseconds / 1e9
        
        # Tolerance, jak dlouho po poslední zprávě považujeme nárazník za sepnutý
        # 0.2s je bezpečná rezerva pro 30Hz update rate v Gazebu
        timeout = 0.2 

        for name, pub in self.publishers_.items():
            msg = Bumper()
            
            # Pokud je čas od posledního kontaktu menší než timeout, je to stále True
            msg.contact = (current_time - self.last_contact_time[name]) < timeout
            
            pub.publish(msg)

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