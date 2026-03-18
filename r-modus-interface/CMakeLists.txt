cmake_minimum_required(VERSION 3.5)
project(r-modus-interface)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GamepadState.msg"
  "msg/PiStatus.msg"
  "srv/GetWifiNetworks.srv"
)

ament_package()
