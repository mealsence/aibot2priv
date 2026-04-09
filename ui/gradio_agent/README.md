---
noteId: "02cc8860c90a11f0aaa2594ec8ff02d3"
tags: []

---

# HRC Demo - Portable Package for lerobot-ros-isaac

This folder contains a simplified, portable version of the HRC DS-RFM demo interface that can be integrated into lerobot-ros-isaac.


# Default: Fastest mode (no discovery, position topic directly)
python demo_tool_calling.py

# With action server discovery (slower startup, but tries action server first)
python demo_tool_calling.py --discover-arm-server

# Full preload including VLA policy
python demo_tool_calling.py --preload-policy


## Contents

- **demo_tool_calling.py** - Main entry point with Gradio interface
- **image_getter.py** - Camera/image capture functionality
- **robot_tools.py** - Robot control functions (arm, gripper, etc.)
- **utils.py** - Pause detection utility for voice chat
- **speaking.py** - TTS streaming stub
- **simple_camera_stream.py** - Live camera streaming
- **two_d_img_annotation_utils.py** - Image annotation using Gemini Vision API
- **world_model.py** - World model for tracking objects and locations
- **system_prompt_tool_calling.txt** - System prompt for the LLM agent
- **requirements.txt** - Python dependencies
- **assets/images/A-STAR_LOGO.png** - Logo image for UI

## Installation

1. Copy this entire `hrc_demo` folder into your lerobot-ros-isaac repository.

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure ROS2 is sourced:
```bash
source /opt/ros/humble/setup.bash  # or your ROS2 distro
```

4. Set environment variables:
```bash
export OPENAI_API_KEY="your-key-here"  # or GOOGLE_API_KEY for Gemini
```

## Usage

Run the demo interface:
```bash
python demo_tool_calling.py
```

Options:
- `--llm openai` or `--llm gemini` - Choose LLM provider (default: openai)
- `--transcriber openai|gemini|meralion` - Choose transcription service (default: meralion)

The interface will be available at `http://0.0.0.0:7868`

## Features

- **Voice Chat (Streaming)** - Real-time voice conversation with pause detection
- **Text Input** - Type messages directly
- **Live Camera Stream** - Real-time camera feed from Isaac Sim
- **Detected Objects Display** - Shows annotated results from vision tools
- **Robot Control** - Direct tool calling for arm/gripper control

## Integration Notes

- All imports are relative and should work when placed in lerobot-ros-isaac
- The `detected_objects/` directory is automatically created if missing
- ROS2 topics expected:
  - `/rgb/camera_1` - RGB camera feed
  - `/camera_1/depth/image_raw` - Depth camera feed
  - `/tf` - Transform frames
  - `/panda_hand_controller/gripper_cmd` - Gripper action server
  - `/panda_arm_controller/follow_joint_trajectory` - Arm action server (or auto-discovered)

## Dependencies

See `requirements.txt` for full list. Key dependencies:
- gradio>=4.44.0
- mbodied (for LanguageAgent and tool calling)
- rclpy (ROS2 Python client)
- openai or google-genai (for LLM)
- gTTS (for text-to-speech)

## Notes

- The `detected_objects/` directory will be automatically created when needed
- Camera streaming supports ROS2, webcam, or dummy backends (auto-detected)
- All robot tools are exposed via the LanguageAgent for natural language control
