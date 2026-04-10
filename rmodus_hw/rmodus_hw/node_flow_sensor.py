import rclpy
from rclpy.node import Node
import numpy as np
from geometry_msgs.msg import TwistWithCovarianceStamped
from pmw3901 import PMW3901, BG_CS_FRONT_BCM
import time

class OpticalFlowTwistPublisher(Node):
    def __init__(self):
        super().__init__('optical_flow_node')
        
        # Sjednocené parametry s defaultními hodnotami z druhého nodu
        self.declare_parameters(
            namespace='',
            parameters=[
                ('spi_port', 0),
                ('spi_cs', 0),
                ('deadzone', 3),
                ('timer_period', 0.05),
                ('sensor_frame', 'flow_sensor_link'),
                ('z_height', 0.025), # Výška senzoru nad zemí v metrech
                ('fov_deg', 42.0),    # Field of View senzoru
                ('res_pix', 35),     # Rozlišení senzoru (standard pro PMW3901)
            ]
        )

        # Načtení parametrů do lokálních proměnných
        port = self.get_parameter('spi_port').value
        cs = self.get_parameter('spi_cs').value
        self.deadzone = self.get_parameter('deadzone').value
        self.timer_period = self.get_parameter('timer_period').value
        self.sensor_frame = self.get_parameter('sensor_frame').value
        
        # Parametry pro přepočet na metry
        self.z_height = self.get_parameter('z_height').value
        self.fov_rad = np.radians(self.get_parameter('fov_deg').value)
        self.res_pix = self.get_parameter('res_pix').value

        try:
            # Inicializace HW (používám BG_CS_FRONT_BCM jako fallback pokud je cs=0)
            spi_cs_pin = cs if cs != 0 else BG_CS_FRONT_BCM
            self.sensor = PMW3901(spi_port=port, spi_cs=spi_cs_pin)
            self.sensor.set_rotation(0)
            
            self.get_logger().info(f'Senzor PMW3901 inicializován na SPI{port} s CS{spi_cs_pin}')
            self.get_logger().info(f'Konfigurace: deadzone={self.deadzone}px, height={self.z_height}m')
        except Exception as e:
            self.get_logger().error(f'Chyba inicializace HW: {e}')
            raise e

        # Publisher pro EKF (Twist s kovariancí)
        self.publisher_ = self.create_publisher(
            TwistWithCovarianceStamped, 
            '/visual_flow/data', 
            10
        )
        
        self.timer = self.create_timer(self.timer_period, self.timer_callback)

    def timer_callback(self):
        try:
            # 1. Přečtení surových dat
            dx, dy = self.sensor.get_motion()
            
            # 2. Aplikace Deadzone filtru
            # Pokud je pohyb v pixelech pod prahem, bereme to jako nulu
            raw_x = float(dx) if abs(dx) >= self.deadzone else 0.0
            raw_y = float(dy) if abs(dy) >= self.deadzone else 0.0
            
            # 3. Přepočet na metrickou rychlost (m/s)
            # Koeficient: kolik metrů představuje jeden pixel v dané výšce
            # cf = (2 * height * tan(FOV/2)) / resolution
            cf = (2.0 * self.z_height * np.tan(self.fov_rad / 2.0)) / self.res_pix
            
            # Rychlost = (pixely * koeficient) / čas_v_sekundách
            vx = (raw_x * cf) / self.timer_period
            vy = (raw_y * cf) / self.timer_period

            # 4. Sestavení zprávy
            msg = TwistWithCovarianceStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self.sensor_frame
            
            # Lineární rychlosti v m/s
            msg.twist.twist.linear.x = vx
            msg.twist.twist.linear.y = vy
            msg.twist.twist.linear.z = 0.0
            
            # Kovariance (odhad chyby)
            # Nastavujeme nízkou hodnotu pro X a Y (věříme senzoru)
            # a vysokou pro vše ostatní (senzor to neměří)
            covariance = [0.0] * 36
            covariance[0] = 0.01   # Var(vx)
            covariance[7] = 0.01   # Var(vy)
            covariance[35] = 100.0 # Var(yaw) - senzor neví nic o rotaci
            msg.twist.covariance = covariance

            self.publisher_.publish(msg)
            
        except RuntimeError:
            # Ignorujeme timeouty sběrnice
            pass
        except Exception as e:
            self.get_logger().warn(f'Chyba při zpracování dat: {e}')

def main(args=None):
    rclpy.init(args=args)
    node = OpticalFlowTwistPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()