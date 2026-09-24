"""Central e-stop latch + zero velocity for cmd_mux + optional platform mirror."""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Twist
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class EStopNode(Node):
    """
    Latch e-stop from software / HW requests.

    Sources publish Bool(true) on request_topic (rising-edge / pulse).
    Optional HW button node publishes level on hw_active_topic (true while pressed).
    Reset via reset_topic Bool(true) or ~/reset service.
    State is published as Bool on state_topic (true = stop active); twist_mux uses it
    as a lock. While active, zero Twist goes to zero_cmd_topic, the highest-priority
    mux input, because twist_mux itself stops forwarding without sending zero.
    """

    def __init__(self):
        super().__init__("rmodus_estop")
        self._cb = ReentrantCallbackGroup()

        self.declare_parameter("enabled", True)
        self.declare_parameter("publish_rate_hz", 50.0)
        self.declare_parameter("zero_cmd_topic", "/estop/cmd_vel")
        self.declare_parameter("state_topic", "/rmodus/e_stop")
        self.declare_parameter("request_topic", "/rmodus/e_stop/request")
        self.declare_parameter("reset_topic", "/rmodus/e_stop/reset")
        self.declare_parameter("hw_active_topic", "/rmodus/e_stop/hw_active")
        self.declare_parameter("require_clear_to_reset", True)

        self.declare_parameter("platform.enabled", False)
        self.declare_parameter("platform.state_topic", "/hardware/e_stop")
        self.declare_parameter("platform.trigger_service", "/hardware/e_stop_trigger")
        self.declare_parameter("platform.reset_service", "/hardware/e_stop_reset")
        self.declare_parameter("platform.mode", "mirror_out")

        self.enabled = bool(self.get_parameter("enabled").value)
        rate = max(1.0, float(self.get_parameter("publish_rate_hz").value))
        self.zero_cmd_topic = str(self.get_parameter("zero_cmd_topic").value).strip()
        self.state_topic = str(self.get_parameter("state_topic").value)
        self.request_topic = str(self.get_parameter("request_topic").value)
        self.reset_topic = str(self.get_parameter("reset_topic").value)
        self.hw_active_topic = str(self.get_parameter("hw_active_topic").value)
        self.require_clear_to_reset = bool(self.get_parameter("require_clear_to_reset").value)

        self._latched = False
        self._hw_active = False
        self._zero = Twist()
        self._platform_out_active = False

        self.cmd_pub = (
            self.create_publisher(Twist, self.zero_cmd_topic, 10) if self.zero_cmd_topic else None
        )
        self.state_pub = self.create_publisher(Bool, self.state_topic, 10)
        self.create_subscription(Bool, self.request_topic, self._on_request, 10, callback_group=self._cb)
        self.create_subscription(Bool, self.reset_topic, self._on_reset_msg, 10, callback_group=self._cb)
        self.create_subscription(
            Bool, self.hw_active_topic, self._on_hw_active, 10, callback_group=self._cb
        )

        self.create_service(Trigger, "~/trigger", self._srv_trigger, callback_group=self._cb)
        self.create_service(Trigger, "~/reset", self._srv_reset, callback_group=self._cb)

        self._init_platform()

        self.create_timer(1.0 / rate, self._on_timer, callback_group=self._cb)
        self.get_logger().info(
            f"rmodus_estop: zero={self.zero_cmd_topic or '-'}, state={self.state_topic}, "
            f"request={self.request_topic}, reset={self.reset_topic}, "
            f"hw_active={self.hw_active_topic}"
        )

    def _init_platform(self):
        self._platform_enabled = bool(self.get_parameter("platform.enabled").value)
        self._platform_mode = str(self.get_parameter("platform.mode").value).strip().lower()
        self._platform_trigger = None
        self._platform_reset = None
        if not self._platform_enabled:
            return

        state_topic = str(self.get_parameter("platform.state_topic").value)
        trigger_srv = str(self.get_parameter("platform.trigger_service").value)
        reset_srv = str(self.get_parameter("platform.reset_service").value)

        if self._platform_mode in ("follow_in", "both"):
            self.create_subscription(
                Bool, state_topic, self._on_platform_state, 10, callback_group=self._cb
            )
        if self._platform_mode in ("mirror_out", "both"):
            self._platform_trigger = self.create_client(Trigger, trigger_srv, callback_group=self._cb)
            self._platform_reset = self.create_client(Trigger, reset_srv, callback_group=self._cb)
        self.get_logger().info(
            f"Platform e-stop bridge mode={self._platform_mode} state={state_topic}"
        )

    def _active(self) -> bool:
        if not self.enabled:
            return False
        return self._latched or self._hw_active

    def _assert_stop(self, reason: str):
        if not self.enabled:
            return
        was = self._latched
        self._latched = True
        if not was:
            self.get_logger().warn(f"E-STOP latched ({reason})")
            self._publish_zero()
            self._mirror_platform_trigger()

    def _try_reset(self, reason: str) -> bool:
        if self.require_clear_to_reset and self._hw_active:
            self.get_logger().warn(f"E-STOP reset blocked, HW still active ({reason})")
            return False
        was = self._latched
        self._latched = False
        if was:
            self.get_logger().info(f"E-STOP cleared ({reason})")
            self._mirror_platform_reset()
        return True

    def _on_request(self, msg: Bool):
        if msg.data:
            self._assert_stop("request")

    def _on_reset_msg(self, msg: Bool):
        if msg.data:
            self._try_reset("reset topic")

    def _on_hw_active(self, msg: Bool):
        self._hw_active = bool(msg.data)
        if self._hw_active:
            self._assert_stop("hw active")

    def _srv_trigger(self, _req, res):
        self._assert_stop("service trigger")
        res.success = True
        res.message = "e-stop latched"
        return res

    def _srv_reset(self, _req, res):
        ok = self._try_reset("service reset")
        res.success = ok
        res.message = "cleared" if ok else "blocked"
        return res

    def _on_platform_state(self, msg: Bool):
        if msg.data:
            self._assert_stop("platform state")

    def _mirror_platform_trigger(self):
        if not self._platform_trigger or self._platform_out_active:
            return
        if not self._platform_trigger.service_is_ready():
            return
        self._platform_out_active = True
        self._platform_trigger.call_async(Trigger.Request())

    def _mirror_platform_reset(self):
        if not self._platform_reset:
            return
        if not self._platform_reset.service_is_ready():
            return
        self._platform_out_active = False
        self._platform_reset.call_async(Trigger.Request())

    def _publish_zero(self):
        if self.cmd_pub is not None:
            self.cmd_pub.publish(self._zero)

    def _on_timer(self):
        active = self._active()
        msg = Bool()
        msg.data = bool(active)
        self.state_pub.publish(msg)
        if active:
            self._publish_zero()


def main(args=None):
    rclpy.init(args=args)
    node = EStopNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
