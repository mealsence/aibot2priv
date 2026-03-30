# Instructions to Tele-Operate the real Panda 
1) goto 192.168.1.101/desk/ on the robot pc
2) unlock robot and activate fci
3) source /opt/ros/humble/setup.bash on the current pc fo multiple terminals
4) run ros2 run spacenav spacenav_node and cd REAL_ROBOT./launch_realsense_camera.sh --config camera_config.yaml on separate terminals
5) Turn on controllers in another terminal using ./gradio_setup_controllers.sh
6) Use ./switch_controllers cartesian to enable controller for teleoperation
7) use ./switch_controllers home to enable controller to move to joint position and run ros2 topic pub --once /move_to_home_lerobot/goal_position std_msgs/msg/Float64MultiArray "{data: [0.035, 0.39, -0.093, -2.5, 0.19, 2.9, 0.6]}" to move to home position
