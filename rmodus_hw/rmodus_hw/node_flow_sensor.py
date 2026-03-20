import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Point
from pmw3901 import PMW3901

class VisualFlowPublisher(Node):
    def __init__(self):
        super().__init__('flow_sensor_node')
        
        # Definice parametrů
        self.declare_parameter('spi_port', 0)
        self.declare_parameter('spi_cs', 0)
        self.declare_parameter('deadzone', 3)  # Ignoruj pohyb menší než 3 pixely
        self.declare_parameter('timer_period', 0.05)  # 20Hz pro hladší data

        # Načtení parametrů
        port = self.get_parameter('spi_port').get_parameter_value().integer_value
        cs = self.get_parameter('spi_cs').get_parameter_value().integer_value
        self.deadzone = self.get_parameter('deadzone').get_parameter_value().integer_value
        timer_period = self.get_parameter('timer_period').get_parameter_value().double_value

        try:
            # Inicializace senzoru podle tvého help() výpisu
            self.sensor = PMW3901(spi_port=port, spi_cs=cs)
            self.sensor.set_rotation(0)
            self.get_logger().info(f'Senzor PMW3901 inicializovan na SPI{port} s CS{cs}')
            self.get_logger().info(f'Nastaven deadzone filtr na: {self.deadzone} px')
        except Exception as e:
            self.get_logger().error(f'Chyba inicializace HW: {e}')
            raise e

        self.publisher_ = self.create_publisher(Point, 'visual_flow', 10)
        self.timer = self.create_timer(timer_period, self.timer_callback)

    def timer_callback(self):
        try:
            # Přečtení surových dat (změna v pixelech)
            dx, dy = self.sensor.get_motion()
            
            # Aplikace Deadzone filtru
            # Pokud je absolutní hodnota menší než práh, pošli 0.0
            filtered_x = float(dx) if abs(dx) >= self.deadzone else 0.0
            filtered_y = float(dy) if abs(dy) >= self.deadzone else 0.0
            
            # Publikace zprávy
            msg = Point()
            msg.x = filtered_x
            msg.y = filtered_y
            msg.z = 0.0

            self.get_logger().info(f'[dx: {filtered_x}, dy: {filtered_y}]')            
            self.publisher_.publish(msg)
            
        except RuntimeError:
            # Občasné chyby čtení (vytížení sběrnice) ignorujeme
            pass
        except Exception as e:
            self.get_logger().warn(f'Chyba pri cteni dat: {e}')

def main(args=None):
    rclpy.init(args=args)
    node = VisualFlowPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Node vypnut uzivatelem.')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
