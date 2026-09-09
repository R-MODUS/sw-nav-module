"""Central e-stop latch + cmd_vel gate + optional GPIO button + platform mirror."""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Twist
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class EStopNode(Node):
    """
    Latch e-stop from software requests / GPIO, gate /cmd_vel → /cmd_vel_safe.

    Sources publish Bool(true) on request_topic (rising-edge / pulse).
    Reset via reset_topic Bool(true) or ~/reset service.
    State is published as Bool on state_topic (true = stop active).
    """

    def __init__(self):
        super().__init__("rmodus_estop")
        self._cb = ReentrantCallbackGroup()

        self.declare_parameter("enabled", True)
        self.declare_parameter("publish_rate_hz", 50.0)
        self.declare_parameter("cmd_vel_input_topic", "/cmd_vel")
        self.declare_parameter("cmd_vel_output_topic", "/cmd_vel_safe")
        self.declare_parameter("state_topic", "/rmodus/e_stop")
        self.declare_parameter("request_topic", "/rmodus/e_stop/request")
        self.declare_parameter("reset_topic", "/rmodus/e_stop/reset")
        self.declare_parameter("require_clear_to_reset", False)

        self.declare_parameter("gpio_button.enabled", False)
        self.declare_parameter("gpio_button.pin", 16)
        self.declare_parameter("gpio_button.active_high", False)
        self.declare_parameter("gpio_button.pull_up", True)

        self.declare_parameter("platform.enabled", False)
        self.declare_parameter("platform.state_topic", "/hardware/e_stop")
        self.declare_parameter("platform.trigger_service", "/hardware/e_stop_trigger")
        self.declare_parameter("platform.reset_service", "/hardware/e_stop_reset")
        self.declare_parameter("platform.mode", "mirror_out")

        self.enabled = bool(self.get_parameter("enabled").value)
        rate = max(1.0, float(self.get_parameter("publish_rate_hz").value))
        self.cmd_in = str(self.get_parameter("cmd_vel_input_topic").value)
        self.cmd_out = str(self.get_parameter("cmd_vel_output_topic").value)
        self.state_topic = str(self.get_parameter("state_topic").value)
        self.request_topic = str(self.get_parameter("request_topic").value)
        self.reset_topic = str(self.get_parameter("reset_topic").value)
        # Kept for YAML compatibility; GPIO pressed always blocks reset.
        self.get_parameter("require_clear_to_reset")

        self._latched = False
        self._zero = Twist()
        self._platform_out_active = False

        self.cmd_pub = self.create_publisher(Twist, self.cmd_out, 10)
        self.state_pub = self.create_publisher(Bool, self.state_topic, 10)
        self.create_subscription(Twist, self.cmd_in, self._on_cmd_vel, 10, callback_group=self._cb)
        self.create_subscription(Bool, self.request_topic, self._on_request, 10, callback_group=self._cb)
        self.create_subscription(Bool, self.reset_topic, self._on_reset_msg, 10, callback_group=self._cb)

        self.create_service(Trigger, "~/trigger", self._srv_trigger, callback_group=self._cb)
        self.create_service(Trigger, "~/reset", self._srv_reset, callback_group=self._cb)

        self._gpio = None
        self._gpio_was_pressed = False
        self._init_gpio()
        self._init_platform()

        self.create_timer(1.0 / rate, self._on_timer, callback_group=self._cb)
        self.get_logger().info(
            f"rmodus_estop: {self.cmd_in}->{self.cmd_out}, state={self.state_topic}, "
            f"request={self.request_topic}, reset={self.reset_topic}"
        )

    def _init_gpio(self):
        if not bool(self.get_parameter("gpio_button.enabled").value):
            return
        pin = int(self.get_parameter("gpio_button.pin").value)
        pull_up = bool(self.get_parameter("gpio_button.pull_up").value)
        try:
            from gpiozero import Button

            self._gpio = Button(pin, pull_up=pull_up)
            self.get_logger().info(f"GPIO e-stop button on pin {pin}")
        except Exception as exc:
            self.get_logger().error(f"GPIO button init failed: {exc}")
            self._gpio = None

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

    def _gpio_pressed(self) -> bool:
        if self._gpio is None:
            return False
        return bool(self._gpio.is_pressed)

    def _active(self) -> bool:
        if not self.enabled:
            return False
        return self._latched or self._gpio_pressed()

    def _assert_stop(self, reason: str):
        if not self.enabled:
            return
        was = self._latched
        self._latched = True
        if not was:
            self.get_logger().warn(f"E-STOP latched ({reason})")
            self._mirror_platform_trigger()

    def _try_reset(self, reason: str) -> bool:
        if self._gpio_pressed():
            self.get_logger().warn(f"E-STOP reset blocked, GPIO still pressed ({reason})")
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

    def _on_cmd_vel(self, msg: Twist):
        if self._active():
            self.cmd_pub.publish(self._zero)
            return
        self.cmd_pub.publish(msg)

    def _on_timer(self):
        pressed = self._gpio_pressed()
        if pressed and not self._gpio_was_pressed:
            self._assert_stop("gpio")
        self._gpio_was_pressed = pressed

        active = self._active()
        msg = Bool()
        msg.data = bool(active)
        self.state_pub.publish(msg)
        if active:
            self.cmd_pub.publish(self._zero)


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
