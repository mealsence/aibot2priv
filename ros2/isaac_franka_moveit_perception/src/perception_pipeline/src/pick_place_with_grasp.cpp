// Build with MoveIt2 / ROS2 (Humble+ & MoveIt2)

#include <rclcpp/rclcpp.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit_msgs/msg/collision_object.hpp>
#include <moveit_msgs/msg/attached_collision_object.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <geometry_msgs/msg/pose.hpp>
#include <chrono>
#include <thread>

// Optional: for Gripper action client
#include <rclcpp_action/rclcpp_action.hpp>
#include <control_msgs/action/gripper_command.hpp>

using namespace std::chrono_literals;

// --- CONFIG — customize to your robot / setup ---
static const std::string ARM_GROUP     = "panda_arm";   // MoveIt planning group for the arm
static const std::string GRIPPER_GROUP = "hand";        // MoveIt planning group for the gripper
static const std::string EE_LINK       = "panda_hand";  // End-effector link name to attach to
static const std::string BOX_ID        = "cube";        // Collision object id

// If using MoveGroup for gripper, provide a simple open/close joint target map (names -> values)
const std::map<std::string, double> GRIPPER_OPEN_POS  = { {"panda_finger_joint1", 0.04} };
const std::map<std::string, double> GRIPPER_CLOSED_POS = { {"panda_finger_joint1", 0.022} };

// If using action client (Option B), set desired positions in meters for GripperCommand
static const double GRIPPER_ACTION_OPEN_POS  = 0.04;  // meters
static const double GRIPPER_ACTION_CLOSED_POS = 0.0;  // meters
// ------------------------------------------------

void apply_sleep(double s) { std::this_thread::sleep_for(std::chrono::duration<double>(s)); }

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);
  auto node = rclcpp::Node::make_shared("pick_place_with_grasp");
  rclcpp::executors::SingleThreadedExecutor exec;
  exec.add_node(node);

  // Interfaces
  moveit::planning_interface::MoveGroupInterface arm_move_group(node, ARM_GROUP);
  moveit::planning_interface::PlanningSceneInterface planning_scene;

  // Optional: gripper MoveGroup (Option A)
  moveit::planning_interface::MoveGroupInterface gripper_move_group(node, GRIPPER_GROUP);

  // Optional: Gripper action client (Option B)
  using GripperAction = control_msgs::action::GripperCommand;
  auto action_client = rclcpp_action::create_client<GripperAction>(node, "/robotiq_gripper_controller/gripper_cmd");

  // Basic move settings
  arm_move_group.setPlanningTime(10.0);
  arm_move_group.setMaxVelocityScalingFactor(0.2);
  arm_move_group.setMaxAccelerationScalingFactor(0.2);

  RCLCPP_INFO(node->get_logger(), "=== Adding collision box to the scene ===");

  // 1) Add box to planning scene (box sits on table)
  moveit_msgs::msg::CollisionObject box;
  box.id = BOX_ID;
  box.header.frame_id = arm_move_group.getPlanningFrame();

  shape_msgs::msg::SolidPrimitive primitive;
  primitive.type = primitive.BOX;
  primitive.dimensions = {0.04, 0.04, 0.05};

  geometry_msgs::msg::Pose box_pose;
  box_pose.orientation.w = 1.0;
  box_pose.position.x = 0.5; // in front of the robot
  box_pose.position.y = 0.0;
  box_pose.position.z = 0.025; // half height above table

  box.primitives.push_back(primitive);
  box.primitive_poses.push_back(box_pose);
  box.operation = box.ADD;

  planning_scene.addCollisionObjects({box});
  RCLCPP_INFO(node->get_logger(), "Added box '%s' to planning scene (frame: %s)", BOX_ID.c_str(), box.header.frame_id.c_str());
  apply_sleep(1.5);

  // 2) Move arm to pre-grasp (above box)
  geometry_msgs::msg::Pose pre_grasp = box_pose;
  pre_grasp.position.z += 0.2; // approach from above
  pre_grasp.orientation.w = 0.0;
  pre_grasp.orientation.x = 1.0;
  pre_grasp.orientation.y = 0.0;
  pre_grasp.orientation.z = 0.0;

  arm_move_group.setPoseTarget(pre_grasp, EE_LINK);
  {
    auto result = arm_move_group.move();
    if (result != moveit::core::MoveItErrorCode::SUCCESS) {
      RCLCPP_WARN(node->get_logger(), "Failed to move to pre-grasp pose");
    } else {
      RCLCPP_INFO(node->get_logger(), "Reached pre-grasp pose");
    }
  }
  apply_sleep(1.0);

  // ---------------------------
  // GRIPPER OPEN (two options)
  // ---------------------------

  bool use_gripper_movegroup = true; // set false to use action client option
  if (use_gripper_movegroup) {
    // Option A: use MoveGroup to set gripper joint targets
    RCLCPP_INFO(node->get_logger(), "Opening gripper via MoveGroup");
    gripper_move_group.setMaxVelocityScalingFactor(1.0);
    gripper_move_group.setMaxAccelerationScalingFactor(1.0);

    // set joint target(s)
    for (const auto & kv : GRIPPER_OPEN_POS) {
      gripper_move_group.setJointValueTarget(kv.first, kv.second);
    }
    auto res = gripper_move_group.move();
    if (res != moveit::core::MoveItErrorCode::SUCCESS) {
      RCLCPP_WARN(node->get_logger(), "Failed to move gripper to OPEN position");
    }
  } else {
    // Option B: use GripperCommand action
    RCLCPP_INFO(node->get_logger(), "Opening gripper via GripperCommand action");
    if (!action_client->wait_for_action_server(5s)) {
      RCLCPP_ERROR(node->get_logger(), "Gripper action server not available");
    } else {
      auto goal_msg = GripperAction::Goal();
      goal_msg.command.position = GRIPPER_ACTION_OPEN_POS;
      goal_msg.command.max_effort = 50.0; // tune
      auto send_goal_options = rclcpp_action::Client<GripperAction>::SendGoalOptions();
      auto future_goal_handle = action_client->async_send_goal(goal_msg, send_goal_options);
      // wait synchronously
      if (rclcpp::spin_until_future_complete(node, future_goal_handle) != rclcpp::FutureReturnCode::SUCCESS) {
        RCLCPP_ERROR(node->get_logger(), "Send goal failed");
      } else {
        auto goal_handle = future_goal_handle.get();
        if (!goal_handle) RCLCPP_ERROR(node->get_logger(), "Goal was rejected");
        else {
          auto result_future = action_client->async_get_result(goal_handle);
          if (rclcpp::spin_until_future_complete(node, result_future) == rclcpp::FutureReturnCode::SUCCESS) {
            RCLCPP_INFO(node->get_logger(), "Gripper opened (action)");
          }
        }
      }
    }
  }
  apply_sleep(1.0);

  // 3) Lower to grasp pose
  geometry_msgs::msg::Pose grasp_pose = pre_grasp;
  grasp_pose.position.z = box_pose.position.z + 0.1;
  grasp_pose.orientation.w = 0.0;
  grasp_pose.orientation.x = 1.0;
  grasp_pose.orientation.y = 0.0;
  grasp_pose.orientation.z = 0.0;
  arm_move_group.setPoseTarget(grasp_pose, EE_LINK);
  {
    auto res = arm_move_group.move();
    if (res != moveit::core::MoveItErrorCode::SUCCESS)
      RCLCPP_WARN(node->get_logger(), "Failed to move to grasp pose");
    else
      RCLCPP_INFO(node->get_logger(), "Reached grasp pose");
  }
  apply_sleep(1.0);

  // 4) CLOSE gripper (same two options)
  if (use_gripper_movegroup) {
    RCLCPP_INFO(node->get_logger(), "Closing gripper via MoveGroup");
    for (const auto & kv : GRIPPER_CLOSED_POS) {
      gripper_move_group.setJointValueTarget(kv.first, kv.second);
    }
    auto res = gripper_move_group.move();
    if (res != moveit::core::MoveItErrorCode::SUCCESS) {
      RCLCPP_WARN(node->get_logger(), "Failed to close gripper (MoveGroup)");
    }
  } else {
    RCLCPP_INFO(node->get_logger(), "Closing gripper via Action");
    if (!action_client->wait_for_action_server(5s)) {
      RCLCPP_ERROR(node->get_logger(), "Gripper action server not available");
    } else {
      auto goal_msg = GripperAction::Goal();
      goal_msg.command.position = GRIPPER_ACTION_CLOSED_POS;
      goal_msg.command.max_effort = 50.0;
      auto send_goal_options = rclcpp_action::Client<GripperAction>::SendGoalOptions();
      auto future_goal_handle = action_client->async_send_goal(goal_msg, send_goal_options);
      if (rclcpp::spin_until_future_complete(node, future_goal_handle) == rclcpp::FutureReturnCode::SUCCESS) {
        auto goal_handle = future_goal_handle.get();
        if (goal_handle) {
          auto result_future = action_client->async_get_result(goal_handle);
          if (rclcpp::spin_until_future_complete(node, result_future) == rclcpp::FutureReturnCode::SUCCESS) {
            RCLCPP_INFO(node->get_logger(), "Gripper closed (action)");
          }
        }
      }
    }
  }
  apply_sleep(1.0);

  // 5) Attach object to the robot so MoveIt ignores it as external obstacle
  {
    RCLCPP_INFO(node->get_logger(), "Attaching object '%s' to '%s'", BOX_ID.c_str(), EE_LINK.c_str());

    moveit_msgs::msg::AttachedCollisionObject attached;
    attached.link_name = EE_LINK;
    attached.object = box; // attach the same collision object we added (box)
    // Optional: specify which robot links are allowed to touch the object (touch_links)
    attached.touch_links = { "panda_leftfinger", "panda_rightfinger", EE_LINK };
    planning_scene.applyAttachedCollisionObject(attached);
    apply_sleep(1.0);
  }

  // 6) Lift slightly then move to drop pose
  geometry_msgs::msg::Pose post_grasp = grasp_pose;
  post_grasp.position.z += 0.15; // lift up
  post_grasp.orientation.w = 0.0;
  post_grasp.orientation.x = 1.0;
  post_grasp.orientation.y = 0.0;
  post_grasp.orientation.z = 0.0;

  arm_move_group.setPoseTarget(post_grasp, EE_LINK);
  {
    auto res = arm_move_group.move();
    if (res != moveit::core::MoveItErrorCode::SUCCESS)
      RCLCPP_WARN(node->get_logger(), "Failed to lift after grasp");
  }
  apply_sleep(1.0);

  geometry_msgs::msg::Pose drop_pose = post_grasp;
  drop_pose.position.x = 0.16;
  drop_pose.position.y = 0.61; 
  drop_pose.position.z = 0.25;
  drop_pose.orientation.w = 0.0;
  drop_pose.orientation.x = 1.0;
  drop_pose.orientation.y = 0.0;
  drop_pose.orientation.z = 0.0;
  arm_move_group.setPoseTarget(drop_pose, EE_LINK);
  {
    auto res = arm_move_group.move();
    if (res != moveit::core::MoveItErrorCode::SUCCESS)
      RCLCPP_WARN(node->get_logger(), "Failed to reach drop pose");
    else
      RCLCPP_INFO(node->get_logger(), "Reached drop pose");
  }
  apply_sleep(1.0);

  // 7) Open gripper to release
  if (use_gripper_movegroup) {
    RCLCPP_INFO(node->get_logger(), "Opening gripper to release (MoveGroup)");
    for (const auto & kv : GRIPPER_OPEN_POS) {
      gripper_move_group.setJointValueTarget(kv.first, kv.second);
    }
    gripper_move_group.move();
  } else {
    RCLCPP_INFO(node->get_logger(), "Opening gripper to release (Action)");
    if (action_client->wait_for_action_server(2s)) {
      auto goal_msg = GripperAction::Goal();
      goal_msg.command.position = GRIPPER_ACTION_OPEN_POS;
      goal_msg.command.max_effort = 50.0;
      auto fut = action_client->async_send_goal(goal_msg);
      rclcpp::spin_until_future_complete(node, fut);
    }
  }
  apply_sleep(1.0);

  // 8) Detach and add object back to the world at drop pose
  {
    RCLCPP_INFO(node->get_logger(), "Detaching object and adding back to world as collision object");
    arm_move_group.detachObject(BOX_ID);
    // update box pose to current drop location
    moveit_msgs::msg::CollisionObject box2 = box;
    box2.header.frame_id = arm_move_group.getPlanningFrame();
    box2.primitive_poses[0] = drop_pose;
    box2.operation = box2.ADD;
    planning_scene.addCollisionObjects({box2});
  }

  RCLCPP_INFO(node->get_logger(), "Pick-and-place demo finished");
  rclcpp::shutdown();
  return 0;
}
