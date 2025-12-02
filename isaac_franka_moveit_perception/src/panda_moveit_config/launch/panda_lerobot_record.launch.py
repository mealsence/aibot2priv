import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    """
    Launch file optimized for LeRobot fast data collection.

    This launch file:
    - Only spawns panda_position_controller (fast direct position control)
    - Does NOT spawn panda_arm_controller (avoids resource conflict)
    - Optionally launches RViz for visualization
    - Supports both Isaac Sim and mock hardware modes

    Usage:
        # With Isaac Sim (recommended):
        ros2 launch panda_moveit_config panda_lerobot_record.launch.py ros2_control_hardware_type:=isaac

        # With mock hardware (testing):
        ros2 launch panda_moveit_config panda_lerobot_record.launch.py

        # With RViz visualization:
        ros2 launch panda_moveit_config panda_lerobot_record.launch.py rviz:=true
    """

    # Command-line arguments
    ros2_control_hardware_type = DeclareLaunchArgument(
        "ros2_control_hardware_type",
        default_value="mock_components",
        description="ROS 2 control hardware interface type -- [mock_components, isaac]",
    )

    rviz_arg = DeclareLaunchArgument(
        "rviz",
        default_value="false",
        description="Launch RViz for visualization",
    )

    # Get the path to initial_positions.yaml in xacro-compatible format
    # xacro.load_yaml() can handle $(find) format or absolute paths
    initial_positions_file = os.path.join(
        get_package_share_directory("panda_moveit_config"),
        "config",
        "initial_positions.yaml",
    )

    # Build MoveIt config (needed for robot description)
    moveit_config = (
        MoveItConfigsBuilder("panda")
        .robot_description(
            file_path="config/panda.urdf.xacro",
            mappings={
                "ros2_control_hardware_type": LaunchConfiguration(
                    "ros2_control_hardware_type"
                ),
                "initial_positions_file": initial_positions_file,
            },
        )
        .robot_description_semantic(file_path="config/panda.srdf")
        .planning_scene_monitor(
            publish_robot_description=True, publish_robot_description_semantic=True
        )
        .to_moveit_configs()
    )

    # Static TF (world -> panda_link0)
    static_tf_node = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="static_transform_publisher",
        output="log",
        arguments=["0.0", "0.0", "0.0", "0.0", "0.0", "0.0", "world", "panda_link0"],
    )

    # Robot state publisher
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="both",
        parameters=[moveit_config.robot_description],
    )

    # ros2_control node
    ros2_controllers_path = os.path.join(
        get_package_share_directory("panda_moveit_config"),
        "config",
        "ros2_controllers.yaml",
    )
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[ros2_controllers_path],
        remappings=[
            ("/controller_manager/robot_description", "/robot_description"),
        ],
        output="screen",
    )

    # Spawn joint_state_broadcaster (always needed)
    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            "/controller_manager",
        ],
    )

    # Spawn panda_position_controller (FAST mode - direct position commands)
    panda_position_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["panda_position_controller", "-c", "/controller_manager"],
    )

    # Spawn panda_hand_controller (gripper)
    panda_hand_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["panda_hand_controller", "-c", "/controller_manager"],
    )

    # Optional RViz
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=[
            "-d",
            os.path.join(
                get_package_share_directory("panda_moveit_config"),
                "launch",
                "moveit.rviz",
            ),
        ],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
        ],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )

    return LaunchDescription(
        [
            ros2_control_hardware_type,
            rviz_arg,
            static_tf_node,
            robot_state_publisher,
            ros2_control_node,
            joint_state_broadcaster_spawner,
            panda_position_controller_spawner,
            panda_hand_controller_spawner,
            rviz_node,
        ]
    )
