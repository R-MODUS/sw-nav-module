"""Host drive: /cmd_vel -> per-unit wheel speeds, optional encoder feedback -> /odom + /joint_states.

Driver unit contract (firmware side):
  <cmd_topic>   std_msgs/Float32MultiArray  wheel speed per channel [rad/s], index = channel
  <state_topic> std_msgs/Int32MultiArray    cumulative encoder ticks per channel (optional)

Kinematics, inversion and scaling live here; a unit only runs PID per channel.
Commands are sent at a fixed rate and drop to zeros after cmd_timeout_sec without /cmd_vel,
so the unit can treat a missing command stream as a stop.
"""

import math

import rclpy
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32MultiArray, Int32MultiArray

from rmodus_chassis.kinematics import Kinematics

TWO_PI = 2.0 * math.pi
INT32_SPAN = 1 << 32
INT32_HALF = 1 << 31


def _tick_delta(new, old):
    return (new - old + INT32_HALF) % INT32_SPAN - INT32_HALF


def _yaw_quaternion(yaw):
    return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class _Unit:
    def __init__(self, name, cmd_topic, state_topic, channels):
        self.name = name
        self.cmd_topic = cmd_topic
        self.state_topic = state_topic
        self.channels = channels
        self.cmd_pub = None
        self.last_state_time = None


class _Wheel:
    def __init__(self, name, unit, channel, invert, ticks_per_rev):
        self.name = name
        self.unit = unit
        self.channel = channel
        self.sign = -1.0 if invert else 1.0
        self.ticks_per_rev = ticks_per_rev
        self.last_ticks = None
        self.angle = 0.0
        self.velocity = 0.0
        self.odom_ref = None

    @property
    def has_feedback(self):
        return bool(self.unit.state_topic) and self.ticks_per_rev > 0


class DriveNode(Node):
    def __init__(self):
        super().__init__("rmodus_drive")

        p = self.declare_parameter
        cmd_vel_topic = p("cmd_vel_topic", "/cmd_vel").value
        mode = p("mode", "diff2").value
        wheel_radius = float(p("wheel_radius", 0.05).value)
        track_width = float(p("track_width", 0.3).value)
        wheelbase = float(p("wheelbase", 0.0).value)
        self.max_wheel_speed = float(p("max_wheel_speed", 10.0).value)
        cmd_rate = float(p("cmd_rate_hz", 20.0).value)
        self.cmd_timeout = float(p("cmd_timeout_sec", 0.5).value)

        unit_names = list(p("unit_names", ["main"]).value)
        unit_cmd_topics = list(p("unit_cmd_topics", ["/drive/main/cmd"]).value)
        unit_state_topics = list(p("unit_state_topics", ["/drive/main/state"]).value)
        unit_channels = list(p("unit_channels", [0]).value)

        wheel_names = list(p("wheel_names", ["wheel_l", "wheel_r"]).value)
        wheel_units = list(p("wheel_units", ["main", "main"]).value)
        wheel_channels = list(p("wheel_channels", [0, 1]).value)
        wheel_inverts = list(p("wheel_inverts", [False, True]).value)
        wheel_tpr = list(p("wheel_ticks_per_rev", [0, 0]).value)

        self.state_timeout = float(p("state_timeout_sec", 0.5).value)
        feedback_rate = float(p("feedback_rate_hz", 20.0).value)
        self.publish_odom = bool(p("publish_odom", True).value)
        odom_topic = p("odom_topic", "/odom").value
        self.odom_frame = p("odom_frame", "odom").value
        self.base_frame = p("base_frame", "base_footprint").value
        self.publish_tf = bool(p("publish_tf", False).value)
        self.publish_joint_states = bool(p("publish_joint_states", True).value)
        joint_states_topic = p("joint_states_topic", "/joint_states").value

        n_units = len(unit_names)
        if not (len(unit_cmd_topics) == len(unit_state_topics) == len(unit_channels) == n_units):
            raise ValueError("unit_* parameter lists must have the same length")
        n_wheels = len(wheel_names)
        if not (
            len(wheel_units) == len(wheel_channels) == len(wheel_inverts) == len(wheel_tpr) == n_wheels
        ):
            raise ValueError("wheel_* parameter lists must have the same length")
        if n_wheels == 0:
            raise ValueError("drive needs at least one wheel")
        if len(set(wheel_names)) != n_wheels:
            raise ValueError(f"duplicate wheel names: {wheel_names}")

        self.units = {}
        for name, cmd, state, ch in zip(unit_names, unit_cmd_topics, unit_state_topics, unit_channels):
            if name in self.units:
                raise ValueError(f"duplicate drive unit '{name}'")
            self.units[name] = _Unit(name, str(cmd), str(state or ""), int(ch))

        self.wheels = []
        used = set()
        for name, unit_name, ch, inv, tpr in zip(
            wheel_names, wheel_units, wheel_channels, wheel_inverts, wheel_tpr
        ):
            unit = self.units.get(unit_name)
            if unit is None:
                raise ValueError(f"wheel '{name}' references unknown unit '{unit_name}'")
            if (unit_name, int(ch)) in used:
                raise ValueError(f"unit '{unit_name}' channel {ch} assigned twice")
            if int(ch) < 0:
                raise ValueError(f"wheel '{name}' has negative channel")
            used.add((unit_name, int(ch)))
            self.wheels.append(_Wheel(name, unit, int(ch), bool(inv), int(tpr)))

        for unit in self.units.values():
            needed = 1 + max((w.channel for w in self.wheels if w.unit is unit), default=-1)
            if unit.channels <= 0:
                unit.channels = needed
            elif unit.channels < needed:
                raise ValueError(
                    f"unit '{unit.name}' has channels={unit.channels} but a wheel uses channel {needed - 1}"
                )

        self.kin = Kinematics(mode, wheel_names, wheel_radius, track_width, wheelbase)

        cmd_qos = QoSProfile(depth=1)
        for unit in self.units.values():
            if unit.channels == 0:
                self.get_logger().warn(f"unit '{unit.name}' has no wheels — not publishing")
                continue
            unit.cmd_pub = self.create_publisher(Float32MultiArray, unit.cmd_topic, cmd_qos)
            if unit.state_topic:
                self.create_subscription(
                    Int32MultiArray,
                    unit.state_topic,
                    lambda msg, u=unit: self._on_state(u, msg),
                    qos_profile_sensor_data,
                )

        self.cmd = (0.0, 0.0, 0.0)
        self.last_cmd_time = None
        self.create_subscription(Twist, cmd_vel_topic, self._on_cmd_vel, 10)
        self.create_timer(1.0 / max(cmd_rate, 1.0), self._send_commands)

        self.feedback_wheels = [w for w in self.wheels if w.has_feedback]
        self.odom_pub = None
        self.joint_pub = None
        self.tf_broadcaster = None
        self.x = self.y = self.yaw = 0.0
        self.last_odom_time = None
        self._unobservable_warned = False
        if self.feedback_wheels:
            if self.publish_odom:
                self.odom_pub = self.create_publisher(Odometry, odom_topic, 10)
                if self.publish_tf:
                    from tf2_ros import TransformBroadcaster

                    self.tf_broadcaster = TransformBroadcaster(self)
            if self.publish_joint_states:
                self.joint_pub = self.create_publisher(JointState, joint_states_topic, 10)
            if self.odom_pub or self.joint_pub:
                self.create_timer(1.0 / max(feedback_rate, 1.0), self._publish_feedback)

        self.get_logger().info(
            f"mode={mode} wheels={wheel_names} units="
            + ", ".join(
                f"{u.name}[{u.channels}ch cmd={u.cmd_topic} state={u.state_topic or '-'}]"
                for u in self.units.values()
            )
            + f" feedback={[w.name for w in self.feedback_wheels] or 'none'}"
            + f" odom={'on' if self.odom_pub else 'off'} tf={'on' if self.tf_broadcaster else 'off'}"
        )

    # --- command path -------------------------------------------------------

    def _on_cmd_vel(self, msg: Twist):
        self.cmd = (msg.linear.x, msg.linear.y, msg.angular.z)
        self.last_cmd_time = self.get_clock().now()

    def _cmd_fresh(self):
        if self.last_cmd_time is None:
            return False
        age = (self.get_clock().now() - self.last_cmd_time).nanoseconds * 1e-9
        return age <= self.cmd_timeout

    def _send_commands(self):
        if self._cmd_fresh():
            speeds = self.kin.inverse(*self.cmd, max_wheel_speed=self.max_wheel_speed)
        else:
            speeds = [0.0] * len(self.wheels)
        self._publish_speeds(speeds)

    def _publish_speeds(self, speeds):
        frames = {
            name: [0.0] * u.channels for name, u in self.units.items() if u.cmd_pub is not None
        }
        for wheel, speed in zip(self.wheels, speeds):
            if wheel.unit.name in frames:
                frames[wheel.unit.name][wheel.channel] = float(wheel.sign * speed)
        for name, data in frames.items():
            self.units[name].cmd_pub.publish(Float32MultiArray(data=data))

    def stop(self):
        self._publish_speeds([0.0] * len(self.wheels))

    # --- feedback path ------------------------------------------------------

    def _on_state(self, unit: _Unit, msg: Int32MultiArray):
        now = self.get_clock().now()
        dt = None
        if unit.last_state_time is not None:
            dt = (now - unit.last_state_time).nanoseconds * 1e-9
        unit.last_state_time = now

        for wheel in self.wheels:
            if wheel.unit is not unit or not wheel.has_feedback:
                continue
            if wheel.channel >= len(msg.data):
                self.get_logger().warn(
                    f"unit '{unit.name}' state has {len(msg.data)} values, "
                    f"wheel '{wheel.name}' needs channel {wheel.channel}",
                    throttle_duration_sec=5.0,
                )
                wheel.last_ticks = None
                continue
            ticks = int(msg.data[wheel.channel])
            if wheel.last_ticks is None or dt is None or dt <= 0.0:
                wheel.last_ticks = ticks
                wheel.velocity = 0.0
                continue
            delta = _tick_delta(ticks, wheel.last_ticks)
            wheel.last_ticks = ticks
            step = wheel.sign * TWO_PI * delta / wheel.ticks_per_rev
            velocity = step / dt
            if self.max_wheel_speed > 0.0 and abs(velocity) > 3.0 * self.max_wheel_speed:
                # Counter reset (unit reboot) looks like an impossible jump.
                self.get_logger().warn(
                    f"wheel '{wheel.name}' tick jump {delta} — treating as counter reset",
                    throttle_duration_sec=5.0,
                )
                wheel.velocity = 0.0
                wheel.odom_ref = None
                continue
            wheel.angle += step
            wheel.velocity = velocity

    def _wheel_fresh(self, wheel: _Wheel, now):
        t = wheel.unit.last_state_time
        if t is None or wheel.last_ticks is None:
            return False
        return (now - t).nanoseconds * 1e-9 <= self.state_timeout

    def _publish_feedback(self):
        now = self.get_clock().now()
        fresh = [w for w in self.feedback_wheels if self._wheel_fresh(w, now)]
        for wheel in self.feedback_wheels:
            if wheel not in fresh:
                wheel.odom_ref = None

        if self.joint_pub is not None and fresh:
            js = JointState()
            js.header.stamp = now.to_msg()
            js.name = [w.name for w in fresh]
            js.position = [w.angle for w in fresh]
            js.velocity = [w.velocity for w in fresh]
            self.joint_pub.publish(js)

        if self.odom_pub is not None:
            self._update_odom(now, fresh)

    def _update_odom(self, now, fresh):
        index = {id(w): i for i, w in enumerate(self.wheels)}
        steps, step_idx = [], []
        for wheel in fresh:
            if wheel.odom_ref is None:
                wheel.odom_ref = wheel.angle
                continue
            steps.append(wheel.angle - wheel.odom_ref)
            step_idx.append(index[id(wheel)])
            wheel.odom_ref = wheel.angle

        twist = self.kin.forward([index[id(w)] for w in fresh], [w.velocity for w in fresh])
        if twist is None:
            if fresh and not self._unobservable_warned:
                self.get_logger().warn(
                    f"feedback from {[w.name for w in fresh]} cannot observe {self.kin.mode} motion — no /odom"
                )
                self._unobservable_warned = True
            return
        self._unobservable_warned = False

        motion = self.kin.forward(step_idx, steps) if steps else None
        if motion is not None:
            dx, dy, dyaw = motion
            mid = self.yaw + dyaw / 2.0
            self.x += dx * math.cos(mid) - dy * math.sin(mid)
            self.y += dx * math.sin(mid) + dy * math.cos(mid)
            self.yaw = math.atan2(math.sin(self.yaw + dyaw), math.cos(self.yaw + dyaw))

        qx, qy, qz, qw = _yaw_quaternion(self.yaw)
        stamp = now.to_msg()

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.orientation.x = qx
        odom.pose.pose.orientation.y = qy
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist.linear.x = twist[0]
        odom.twist.twist.linear.y = twist[1]
        odom.twist.twist.angular.z = twist[2]
        vy_var = 0.01 if self.kin.holonomic else 1e-6
        odom.pose.covariance = _diag([0.01, 0.01, 1e6, 1e6, 1e6, 0.05])
        odom.twist.covariance = _diag([0.005, vy_var, 1e6, 1e6, 1e6, 0.02])
        self.odom_pub.publish(odom)

        if self.tf_broadcaster is not None:
            tf = TransformStamped()
            tf.header.stamp = stamp
            tf.header.frame_id = self.odom_frame
            tf.child_frame_id = self.base_frame
            tf.transform.translation.x = self.x
            tf.transform.translation.y = self.y
            tf.transform.rotation.x = qx
            tf.transform.rotation.y = qy
            tf.transform.rotation.z = qz
            tf.transform.rotation.w = qw
            self.tf_broadcaster.sendTransform(tf)


def _diag(values):
    cov = [0.0] * 36
    for i, v in enumerate(values):
        cov[i * 7] = v
    return cov


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DriveNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            try:
                node.stop()
            except Exception:
                pass
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
