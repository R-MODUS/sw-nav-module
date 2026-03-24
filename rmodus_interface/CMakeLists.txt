cmake_minimum_required(VERSION 3.5)
project(rmodus_interface)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GamepadState.msg"
  "msg/PiStatus.msg"
  "srv/GetWifiNetworks.srv"
  "msg/Bumper.msg"
  DEPENDENCIES std_msgs
)

ament_package()
