import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from my.msg import GamepadState

# https://docs.ros.org/en/ros2_packages/jazzy/api/joy/index.html
BUTTON_MAP = {
    0: "a",
    1: "b",
    2: "x",
    3: "y",
    4: "lb",
    5: "rb",
    6: "select",
    7: "start",
    8: "lstick",
    9: "rstick",
    10: "guide",
}

AXIS_MAP = {
    0: "lx",
    1: "ly",
    2: "lt",
    3: "rx",
    4: "ry",
    5: "rt",
    6: "dpad_x",
    7: "dpad_y",
}

class Move(Node):
    def __init__(self):
        super().__init__('joy_mapper')
        self.subscription = self.create_subscription(
        Joy, '/joy', self.update_state, 1
        )
        self.publisher = self.create_publisher(GamepadState, '/joy_mapped', 1)

    def reset_state(self, state):
        for attr in state.__slots__:
            value = getattr(state, attr)
            if isinstance(value, float):
                setattr(state, attr, 0.0)
            elif isinstance(value, bool):
                setattr(state, attr, False)

    def update_state(self, msg: Joy):
        state = GamepadState()

        # tlačítka
        for i, pressed in enumerate(msg.buttons):
            name = BUTTON_MAP.get(i)
            if name and pressed:
                setattr(state, name, True)
        
        # osy
        for i, val in enumerate(msg.axes):
            name = AXIS_MAP.get(i)
            if name is None:
                continue

            if i in [0, 1, 3, 4] and abs(val) > 0.05:
                if i in [0, 3]:
                    val = -val
                setattr(state, name, float(val))

            elif i in [2, 5] and val < 0.95:
                setattr(state, name, float(val))

            elif i == 6:
                if val == 1:
                    setattr(state, 'dpad_left', True)
                elif val == -1:
                    setattr(state, 'dpad_right', True)
            elif i == 7:
                if val == 1:
                    setattr(state, 'dpad_up', True)
                elif val == -1:
                    setattr(state, 'dpad_down', True)

        self.publisher.publish(state)
        self.reset_state(state)

def main(args=None):
    rclpy.init(args=args)
    node = Move()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    rclpy.shutdown()

if __name__ == '__main__':
    main()
