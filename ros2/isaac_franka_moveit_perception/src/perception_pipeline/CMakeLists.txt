cmake_minimum_required(VERSION 3.10)
project(perception_pipeline)

# Set CMake policy to suppress Boost warnings (if policy exists)
if(POLICY CMP0167)
  cmake_policy(SET CMP0167 NEW)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(control_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)

set(executable_list
  pick_place_with_grasp
)

foreach(loop_var IN LISTS executable_list)
  add_executable(${loop_var} src/${loop_var}.cpp)
  ament_target_dependencies(${loop_var}
    rclcpp
    geometry_msgs
    sensor_msgs
    shape_msgs
    moveit_msgs
    control_msgs
    moveit_ros_planning_interface
  )

  install(TARGETS
    ${loop_var}
    DESTINATION lib/${PROJECT_NAME}
  )
endforeach()

install(
  DIRECTORY
    config
    launch
    src
  DESTINATION
    share/${PROJECT_NAME}/
)

install(
  PROGRAMS
  launch/pick_and_place.launch.py
  launch/perception_pipeline_demo.launch.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
