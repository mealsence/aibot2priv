from launch import LaunchDescription
from launch_ros.actions import Node
#from launch.substitutions import PathJoinSubstitution
from moveit_configs_utils import MoveItConfigsBuilder
#from launch_ros.substitutions import FindPackageShare
#from ament_index_python.packages import get_package_share_directory
    
def generate_launch_description():

    moveit_config = (
        MoveItConfigsBuilder("panda")
        .robot_description(file_path="config/panda.urdf.xacro")
        .robot_description_semantic(file_path="config/panda.srdf")
        .robot_description_kinematics(file_path="config/kinematics.yaml")
        .trajectory_execution(file_path="config/gripper_moveit_controllers.yaml")
        .to_moveit_configs()
    )

    pick_and_place_demo = Node(
        name="pick_place_with_grasp",
        package="perception_pipeline",
        executable="pick_place_with_grasp",
        output="screen",
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
        ],
    )

    return LaunchDescription([pick_and_place_demo])
