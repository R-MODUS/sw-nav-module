import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from ros_gz_interfaces.msg import Contacts
from rmodus_interface.msg import Bumper

class SimBumperBridge(Node):
    def __init__(self):
        super().__init__('sim_bumper_bridge')
        
        # Seznam nárazníků k monitorování
        self.bumpers = ['front', 'rear', 'left', 'right']
        self.publishers_ = {}
        
        for name in self.bumpers:
            # Publisher pro čistá data (pro logiku robota)
            self.publishers_[name] = self.create_publisher(
                Bumper, f'/bumper/{name}', 10)
            
            # Subscriber pro surová data z Gazeba
            self.create_subscription(
                Contacts, 
                f'/bumper/{name}/contact', 
                lambda msg, n=name: self.process_contact(msg, n), 
                10)

    def process_contact(self, msg, name):
        out_msg = Bumper()
        # Pokud pole kontaktů není prázdné, nárazník je sepnutý
        out_msg.contact = len(msg.contacts) > 0
        self.publishers_[name].publish(out_msg)

def main(args=None):
    rclpy.init(args=args)
    rclpy.spin(SimBumperBridge())
    rclpy.shutdown()