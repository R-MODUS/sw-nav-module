import rclpy
from rclpy.node import Node

from rmodus_interface.msg import PiStatus

from .utils.display import Display
from .utils.wifi import get_ip_address

class DisplayNode(Node):
    def __init__(self):
        super().__init__('display')
        
        self.status_data = None
        self.current_mode = "STATUS"
        
        self.sub = self.create_subscription(PiStatus, 'system/pi_status', self.status_cb, 10)
        
        self.create_timer(5.0, self.toggle_mode)
        self.create_timer(0.1, self.render_loop)
        
        width = self.declare_parameter('width', 128).get_parameter_value().integer_value
        height = self.declare_parameter('height', 32).get_parameter_value().integer_value
        orientation = self.declare_parameter('orientation', 0).get_parameter_value().integer_value
        brightness = self.declare_parameter('brightness', 100).get_parameter_value().integer_value

        self.disp = Display(width, height, orientation=orientation)
        self.disp.set_brightness(brightness)
        
    def status_cb(self, msg):
        self.status_data = msg

    def toggle_mode(self):
        self.current_mode = "IP" if self.current_mode == "STATUS" else "STATUS"

    def render_loop(self):
        self.disp.clear()
        
        if self.current_mode == "STATUS":
            if self.status_data:
                self.disp.status_table(
                    self.status_data.cpu_usage_percent, 
                    self.status_data.ram_usage_percent, 
                    self.status_data.cpu_temperature
                )
            else:
                self.disp.add_text(5, 5, "No data")
                
        else:
            ip = get_ip_address()
            self.disp.add_text(5, 5, f"IP: {ip}")
            
        self.disp.update()

def main(args=None):
    rclpy.init(args=args)
    node = DisplayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.disp.power_off()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()