import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range, PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header
import tf2_ros
import tf2_geometry_msgs

from rmodus_interface.msg import Bumper

class SensorFusionNode(Node):
    def __init__(self):
        super().__init__('sensor_fusion_node')
        
        # TF2 buffer pro transformace
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # Paměť pro stavy senzorů
        self.last_ranges = {}  # {frame_id: msg}
        self.last_bumpers = {} # {frame_id: msg}

        # Subscribery (dynamicky nebo vyjmenované)
        # Pro zjednodušení ukázka jednoho:
        self.create_subscription(Range, '/range/sensor_0', 
            lambda msg: self.range_cb(msg, 'sensor_0_link'), 10)
        
        self.create_subscription(Bumper, '/bumper/front', 
            lambda msg: self.bumper_cb(msg, 'front_bumper_link'), 10)

        self.pc_pub = self.create_publisher(PointCloud2, '/sensors/combined_cloud', 10)
        
        # Timer pro generování mraku (20 Hz)
        self.create_timer(0.05, self.publish_cloud)

    def bumper_cb(self, msg, frame_id):
        # Uložíme si poslední zprávu pro daný rámec
        self.last_bumpers[frame_id] = msg

    def range_cb(self, msg, frame):
        self.last_ranges[frame] = msg

    def publish_cloud(self):
        points = []
        now = self.get_clock().now().to_msg()

        # Zpracování Cliff senzorů
        for frame, msg in self.last_ranges.items():
            if msg.range > 0.12: # Práh pro propast
                # Přidáme bod 2cm před senzor v base_link souřadnicích
                p = self.transform_point(0.02, 0.0, 0.0, frame, 'base_link')
                if p: points.append(p)

        # Zpracování Bumperů
        for frame, msg in self.last_bumpers.items():
            if msg.contact:
                # Vygenerujeme úsečku bodů podle msg.width
                num_points = 5
                for i in range(num_points):
                    y_off = (i / (num_points - 1) - 0.5) * msg.width
                    p = self.transform_point(0.0, y_off, 0.0, frame, 'base_link')
                    if p: points.append(p)

        # Vytvoření a publikace PC2
        if points:
            header = Header(stamp=now, frame_id='base_link')
            pc_msg = point_cloud2.create_cloud_xyz32(header, points)
            self.pc_pub.publish(pc_msg)

    def transform_point(self, x, y, z, from_frame, to_frame):
        try:
            # Získáme transformaci z URDF
            t = self.tf_buffer.lookup_transform(to_frame, from_frame, rclpy.time.Time())
            # Jednoduchý statický výpočet (pro PointCloud stačí pozice linku + offset)
            # V reálu by se použilo tf2_geometry_msgs pro rotaci
            return [t.transform.translation.x + x, 
                    t.transform.translation.y + y, 
                    t.transform.translation.z + z]
        except Exception:
            return None