import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range, PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header
import tf2_ros
import math

from rmodus_interface.msg import Bumper


class ObstacleCloudNode(Node):
    def __init__(self):
        super().__init__('obstacle_cloud_node')

        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('output_topic', '/sensors/combined_cloud')
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('cliff_threshold_m', 0.12)
        self.declare_parameter('cliff_point_offset_m', 0.05)
        self.declare_parameter('cliff_circle_points', 10)
        self.declare_parameter('cliff_circle_radius_m', 0.06)
        self.declare_parameter('bumper_points_per_sensor', 7)
        self.declare_parameter('tf_timeout_sec', 0.05)
        self.declare_parameter('enable_dynamic_discovery', True)
        self.declare_parameter('sensor_discovery_rate_hz', 1.0)
        self.declare_parameter('bumper_topic_prefix', '/bumper/')
        self.declare_parameter('cliff_topic_prefix', '/cliff/')
        self.declare_parameter('persistent_enabled', True)
        self.declare_parameter('persistent_topic', '/sensors/combined_cloud_map')
        self.declare_parameter('persistent_frame', 'map')
        self.declare_parameter('persistent_merge_distance_m', 0.05)
        self.declare_parameter('persistent_max_points', 4000)
        self.declare_parameter('persistent_decay_sec', 0.0)
        self.declare_parameter(
            'range_topics',
            ['/range/sensor_0', '/range/sensor_1', '/range/sensor_2', '/range/sensor_3', '/cliff/fl', '/cliff/fr', '/cliff/rl', '/cliff/rr'],
        )
        self.declare_parameter('bumper_topics', ['/bumper/front', '/bumper/rear', '/bumper/left', '/bumper/right'])
        self.declare_parameter(
            'range_topic_frames',
            ['/cliff/fl:cliff_sensor_fl_beam_frame', '/cliff/fr:cliff_sensor_fr_beam_frame', '/cliff/rl:cliff_sensor_rl_beam_frame', '/cliff/rr:cliff_sensor_rr_beam_frame'],
        )
        self.declare_parameter(
            'bumper_topic_frames',
            ['/bumper/front:bumper_front_link', '/bumper/rear:bumper_rear_link', '/bumper/left:bumper_left_link', '/bumper/right:bumper_right_link'],
        )

        self.base_frame = str(self.get_parameter('base_frame').value)
        self.output_topic = str(self.get_parameter('output_topic').value)
        self.publish_rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self.cliff_threshold_m = float(self.get_parameter('cliff_threshold_m').value)
        self.cliff_point_offset_m = float(self.get_parameter('cliff_point_offset_m').value)
        self.cliff_circle_points = max(1, int(self.get_parameter('cliff_circle_points').value))
        self.cliff_circle_radius_m = max(0.0, float(self.get_parameter('cliff_circle_radius_m').value))
        self.bumper_points_per_sensor = max(2, int(self.get_parameter('bumper_points_per_sensor').value))
        self.tf_timeout_sec = max(0.0, float(self.get_parameter('tf_timeout_sec').value))
        self.enable_dynamic_discovery = bool(self.get_parameter('enable_dynamic_discovery').value)
        self.sensor_discovery_rate_hz = max(0.1, float(self.get_parameter('sensor_discovery_rate_hz').value))
        self.bumper_topic_prefix = str(self.get_parameter('bumper_topic_prefix').value)
        self.cliff_topic_prefix = str(self.get_parameter('cliff_topic_prefix').value)
        self.persistent_enabled = bool(self.get_parameter('persistent_enabled').value)
        self.persistent_topic = str(self.get_parameter('persistent_topic').value)
        self.persistent_frame = str(self.get_parameter('persistent_frame').value)
        self.persistent_merge_distance_m = max(0.0, float(self.get_parameter('persistent_merge_distance_m').value))
        self.persistent_max_points = max(1, int(self.get_parameter('persistent_max_points').value))
        self.persistent_decay_sec = max(0.0, float(self.get_parameter('persistent_decay_sec').value))
        self.name_aliases = {
            'front_left': 'fl',
            'front_right': 'fr',
            'rear_left': 'rl',
            'rear_right': 'rr',
        }

        range_topics = list(self.get_parameter('range_topics').value)
        bumper_topics = list(self.get_parameter('bumper_topics').value)
        self.range_topic_frames = self._parse_mapping_list(list(self.get_parameter('range_topic_frames').value))
        self.bumper_topic_frames = self._parse_mapping_list(list(self.get_parameter('bumper_topic_frames').value))

        # TF2 buffer pro transformace
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # Paměť pro stavy senzorů
        self.last_ranges = {}  # {frame_id: Range}
        self.last_bumpers = {}  # {frame_id: Bumper}
        self._sensor_subscriptions = []
        self.subscribed_range_topics = set()
        self.subscribed_bumper_topics = set()
        self.persistent_points = []
        self.persistent_point_times = []

        for topic in range_topics:
            self._register_range_topic(topic)
        for topic in bumper_topics:
            self._register_bumper_topic(topic)

        if self.enable_dynamic_discovery:
            self._discover_dynamic_topics()
            self.create_timer(1.0 / self.sensor_discovery_rate_hz, self._discover_dynamic_topics)

        self.pc_pub = self.create_publisher(PointCloud2, self.output_topic, 10)
        self.persistent_pc_pub = None
        if self.persistent_enabled:
            self.persistent_pc_pub = self.create_publisher(PointCloud2, self.persistent_topic, 10)

        # Timer pro generování mraku
        period = 1.0 / self.publish_rate_hz if self.publish_rate_hz > 0.0 else 0.05
        self.create_timer(period, self.publish_cloud)
        self.get_logger().info(f'Obstacle cloud active: {self.output_topic} in frame {self.base_frame}')
        if self.persistent_enabled:
            self.get_logger().info(
                f'Persistent obstacle cloud active: {self.persistent_topic} in frame {self.persistent_frame}'
            )

    def _parse_mapping_list(self, mappings):
        parsed = {}
        for raw in mappings:
            if ':' not in raw:
                continue
            key, value = raw.split(':', 1)
            parsed[str(key).strip()] = str(value).strip()
        return parsed

    def _register_range_topic(self, topic):
        if topic in self.subscribed_range_topics:
            return
        self._sensor_subscriptions.append(
            self.create_subscription(
                Range,
                topic,
                lambda msg, t=topic: self.range_cb(msg, t),
                10,
            )
        )
        self.subscribed_range_topics.add(topic)
        self.get_logger().info(f'Subscribed range topic: {topic}')

    def _register_bumper_topic(self, topic):
        if topic in self.subscribed_bumper_topics:
            return
        self._sensor_subscriptions.append(
            self.create_subscription(
                Bumper,
                topic,
                lambda msg, t=topic: self.bumper_cb(msg, t),
                10,
            )
        )
        self.subscribed_bumper_topics.add(topic)
        self.get_logger().info(f'Subscribed bumper topic: {topic}')

    def _discover_dynamic_topics(self):
        for topic_name, topic_types in self.get_topic_names_and_types():
            if topic_name.startswith(self.cliff_topic_prefix) and 'sensor_msgs/msg/Range' in topic_types:
                if topic_name not in self.range_topic_frames:
                    self.range_topic_frames[topic_name] = self._default_range_frame(topic_name)
                self._register_range_topic(topic_name)

            if topic_name.startswith(self.bumper_topic_prefix) and 'rmodus_interface/msg/Bumper' in topic_types:
                if topic_name not in self.bumper_topic_frames:
                    self.bumper_topic_frames[topic_name] = self._default_bumper_frame(topic_name)
                self._register_bumper_topic(topic_name)

    def _default_range_frame(self, topic):
        suffix = topic.rstrip('/').split('/')[-1]
        suffix = self.name_aliases.get(suffix, suffix)
        return f'cliff_sensor_{suffix}_beam_frame'

    def _default_bumper_frame(self, topic):
        suffix = topic.rstrip('/').split('/')[-1]
        suffix = self.name_aliases.get(suffix, suffix)
        return f'bumper_{suffix}_link'

    def bumper_cb(self, msg, topic):
        frame_id = msg.header.frame_id.strip() if msg.header.frame_id else ''
        if not frame_id:
            frame_id = self.bumper_topic_frames.get(topic, '')
        if not frame_id:
            return
        self.last_bumpers[frame_id] = msg

    def range_cb(self, msg, topic):
        frame_id = msg.header.frame_id.strip() if msg.header.frame_id else ''
        if not frame_id:
            frame_id = self.range_topic_frames.get(topic, '')
        if not frame_id:
            return
        self.last_ranges[frame_id] = msg

    def publish_cloud(self):
        points = []
        now = self.get_clock().now().to_msg()

        # Zpracování Cliff senzorů
        for frame, msg in self.last_ranges.items():
            if msg.range > self.cliff_threshold_m:
                # Vykreslíme malý kruh kolem detekce, ať je cliff výraznější v RViz/costmapě.
                center = self.transform_point(self.cliff_point_offset_m, 0.0, 0.0, frame, self.base_frame)
                if center:
                    points.append(center)
                if self.cliff_circle_points > 1 and self.cliff_circle_radius_m > 0.0:
                    for i in range(self.cliff_circle_points):
                        angle = 2.0 * math.pi * i / self.cliff_circle_points
                        x_off = self.cliff_point_offset_m + self.cliff_circle_radius_m * math.cos(angle)
                        y_off = self.cliff_circle_radius_m * math.sin(angle)
                        p = self.transform_point(x_off, y_off, 0.0, frame, self.base_frame)
                        if p:
                            points.append(p)

        # Zpracování Bumperů
        for frame, msg in self.last_bumpers.items():
            if msg.contact:
                # Vygenerujeme úsečku bodů přes šířku bumperu
                width = float(msg.width) if msg.width > 0.0 else 0.20
                depth = float(msg.depth) if msg.depth > 0.0 else 0.01
                num_points = self.bumper_points_per_sensor
                for i in range(num_points):
                    y_off = (i / (num_points - 1) - 0.5) * width
                    p = self.transform_point(depth, y_off, 0.0, frame, self.base_frame)
                    if p:
                        points.append(p)

        # Vytvoření a publikace PC2
        header = Header(stamp=now, frame_id=self.base_frame)
        pc_msg = point_cloud2.create_cloud_xyz32(header, points)
        self.pc_pub.publish(pc_msg)
        self._update_persistent_cloud(points, now)

    def _update_persistent_cloud(self, points, stamp_msg):
        if not self.persistent_enabled or self.persistent_pc_pub is None:
            return

        now_sec = float(stamp_msg.sec) + float(stamp_msg.nanosec) * 1e-9
        if self.persistent_decay_sec > 0.0 and self.persistent_point_times:
            kept_points = []
            kept_times = []
            oldest_allowed = now_sec - self.persistent_decay_sec
            for idx, point in enumerate(self.persistent_points):
                if self.persistent_point_times[idx] >= oldest_allowed:
                    kept_points.append(point)
                    kept_times.append(self.persistent_point_times[idx])
            self.persistent_points = kept_points
            self.persistent_point_times = kept_times

        merge_dist_sq = self.persistent_merge_distance_m * self.persistent_merge_distance_m
        for point in points:
            p_map = self.transform_point(
                float(point[0]),
                float(point[1]),
                float(point[2]),
                self.base_frame,
                self.persistent_frame,
            )
            if p_map is None:
                continue

            if merge_dist_sq > 0.0:
                duplicate = False
                for existing in self.persistent_points:
                    dx = existing[0] - p_map[0]
                    dy = existing[1] - p_map[1]
                    dz = existing[2] - p_map[2]
                    if (dx * dx + dy * dy + dz * dz) <= merge_dist_sq:
                        duplicate = True
                        break
                if duplicate:
                    continue

            self.persistent_points.append(p_map)
            self.persistent_point_times.append(now_sec)

            if len(self.persistent_points) > self.persistent_max_points:
                overflow = len(self.persistent_points) - self.persistent_max_points
                self.persistent_points = self.persistent_points[overflow:]
                self.persistent_point_times = self.persistent_point_times[overflow:]

        header = Header(stamp=stamp_msg, frame_id=self.persistent_frame)
        persistent_msg = point_cloud2.create_cloud_xyz32(header, self.persistent_points)
        self.persistent_pc_pub.publish(persistent_msg)

    def _rotate_vector_by_quaternion(self, x, y, z, qx, qy, qz, qw):
        # q * v * q_conj
        ix = qw * x + qy * z - qz * y
        iy = qw * y + qz * x - qx * z
        iz = qw * z + qx * y - qy * x
        iw = -qx * x - qy * y - qz * z

        rx = ix * qw + iw * (-qx) + iy * (-qz) - iz * (-qy)
        ry = iy * qw + iw * (-qy) + iz * (-qx) - ix * (-qz)
        rz = iz * qw + iw * (-qz) + ix * (-qy) - iy * (-qx)
        return rx, ry, rz

    def transform_point(self, x, y, z, from_frame, to_frame):
        try:
            t = self.tf_buffer.lookup_transform(
                to_frame,
                from_frame,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=self.tf_timeout_sec),
            )
            tx = t.transform.translation.x
            ty = t.transform.translation.y
            tz = t.transform.translation.z
            qx = t.transform.rotation.x
            qy = t.transform.rotation.y
            qz = t.transform.rotation.z
            qw = t.transform.rotation.w

            norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
            if norm < 1e-9:
                return [tx + x, ty + y, tz + z]
            qx /= norm
            qy /= norm
            qz /= norm
            qw /= norm

            rx, ry, rz = self._rotate_vector_by_quaternion(x, y, z, qx, qy, qz, qw)
            return [tx + rx, ty + ry, tz + rz]
        except Exception as exc:
            self.get_logger().debug(f'TF transform failed {from_frame}->{to_frame}: {exc}')
            return None


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleCloudNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()