import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
import board
import busio
from adafruit_mcp230xx.mcp23017 import MCP23017
import digitalio

class BumperNode(Node):
    def __init__(self):
        super().__init__('bumper_node')

        # I2C inicializace
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            # Vychozi adresa MCP23017 je 0x20
            self.mcp = MCP23017(self.i2c, address=0x20)
        except Exception as e:
            self.get_logger().error(f"MCP23017 init failed: {e}")
            return

        # Nastaveni 4 pinu (naplage piny 0, 1, 2, 3 na portu A)
        self.pins = []
        self.topic_names = ['bumper/front_left', 'bumper/front_right', 'bumper/rear_left', 'bumper/rear_right']
        self.pubs = []

        for i in range(4):
            pin = self.mcp.get_pin(i)
            pin.direction = digitalio.Direction.INPUT
            pin.pull = digitalio.Pull.UP # Aktivace vnitrniho pull-up
            self.pins.append(pin)
            self.pubs.append(self.create_publisher(Bool, self.topic_names[i], 10))

        # Rychla smycka pro bumpery (např. 50 Hz pro okamzitou reakci)
        self.timer = self.create_timer(0.02, self.timer_callback)

    def timer_callback(self):
        for i in range(4):
            msg = Bool()
            # Pokud je pull-up, stisknuty bumper (GND) vrati False. 
            # Negujeme to, aby True znamenalo "naraz".
            msg.data = not self.pins[i].value
            self.pubs[i].publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = BumperNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()