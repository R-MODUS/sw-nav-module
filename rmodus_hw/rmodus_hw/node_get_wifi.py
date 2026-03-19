import rclpy
from rclpy.node import Node
from rmodus_interface.srv import GetWifiNetworks
import subprocess
import re

class WifiServiceNode(Node):
    def __init__(self):
        super().__init__('wifi_service_node')
        self.srv = self.create_service(GetWifiNetworks, 'get_wifi_list', self.callback)
        self.get_logger().info('Wifi Node připraven k aktivnímu skenování.')

    def callback(self, request, response):
        self.get_logger().info('Provádím aktivní skenování okolí...')
        try:
            # sudo vynutí čerstvý sken, re.IGNORECASE pro jistotu
            cmd = "sudo iwlist wlan0 scan | grep -i ESSID"
            output = subprocess.check_output(cmd, shell=True).decode('utf-8')
            
            # Najde vše mezi uvozovkami za ESSID:
            networks = re.findall(r'ESSID:"([^"]+)"', output)
            
            # Odstranění duplicit a seřazení podle abecedy
            unique_networks = sorted(list(set([n for n in networks if n.strip()])))
            
            response.networks = unique_networks
            response.success = True
            self.get_logger().info(f'Nalezeno {len(unique_networks)} unikátních sítí.')
            
        except Exception as e:
            self.get_logger().error(f'Skenování selhalo: {e}')
            response.success = False
            response.networks = []
            
        return response

def main():
    rclpy.init()
    node = WifiServiceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()