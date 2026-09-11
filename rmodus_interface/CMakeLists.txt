cmake_minimum_required(VERSION 3.5)
project(rmodus_interface)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GamepadState.msg"
  "msg/PiStatus.msg"
  "msg/Bumper.msg"
  "srv/GetWifiNetworks.srv"
  "srv/ListProfiles.srv"
  "srv/GetProfile.srv"
  "srv/SaveProfile.srv"
  "srv/CreateProfile.srv"
  "srv/DeleteProfile.srv"
  "srv/RenameProfile.srv"
  "srv/ActivateProfile.srv"
  "srv/GetNetworkConfig.srv"
  "srv/SetNetworkConfig.srv"
  DEPENDENCIES std_msgs
)

ament_package()
