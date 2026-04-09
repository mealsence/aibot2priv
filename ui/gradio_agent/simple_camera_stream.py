#!/usr/bin/env python3
"""
Simple Camera Streaming Interface

A clean implementation of camera streaming for Isaac Sim or webcam
that integrates with the existing Gradio demo interface.
"""

import gradio as gr
import cv2
import numpy as np
from PIL import Image as PILImage
import threading
import time
import queue
from typing import Optional, Union
import os

# ROS2 imports (optional, will gracefully degrade if not available)
try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    # Note: cv_bridge has NumPy compatibility issues, using manual conversion
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    print("⚠️ ROS2 not available, falling back to webcam/dummy mode")


class CameraStreamer:
    """Unified camera streamer that supports multiple backends"""
    
    def __init__(self, source: str = "auto"):
        """
        Initialize camera streamer.
        
        Args:
            source: "ros2", "webcam", "dummy", or "auto" (tries ros2 first, then webcam, then dummy)
        """
        self.source = source
        self.latest_frame = None
        self.frame_queue = queue.Queue(maxsize=10)  # Increased buffer size
        self.running = False
        self.capture_thread = None
        
        # Try to initialize the appropriate backend
        self.backend = None
        if source == "auto":
            self.backend = self._initialize_auto()
        elif source == "ros2":
            self.backend = self._initialize_ros2()
        elif source == "webcam":
            self.backend = self._initialize_webcam()
        elif source == "dummy":
            self.backend = self._initialize_dummy()
        else:
            raise ValueError(f"Unknown source: {source}")
    
    def _initialize_auto(self):
        """Try backends in order of preference"""
        # First try ROS2
        if ROS2_AVAILABLE:
            backend = self._initialize_ros2()
            if backend:
                return backend
        
        # Then try webcam
        backend = self._initialize_webcam()
        if backend:
            return backend
        
        # Fall back to dummy
        return self._initialize_dummy()
    
    def _initialize_ros2(self):
        """Initialize ROS2 Isaac Sim camera backend"""
        if not ROS2_AVAILABLE:
            return None
        
        try:
            if not rclpy.ok():
                rclpy.init()
            
            backend = ROS2CameraBackend()
            print("✅ ROS2 camera backend initialized")
            return backend
        except Exception as e:
            print(f"❌ Failed to initialize ROS2 backend: {e}")
            return None
    
    def _initialize_webcam(self):
        """Initialize webcam backend"""
        try:
            backend = WebcamBackend()
            if backend.is_available():
                print("✅ Webcam backend initialized")
                return backend
            else:
                return None
        except Exception as e:
            print(f"❌ Failed to initialize webcam backend: {e}")
            return None
    
    def _initialize_dummy(self):
        """Initialize dummy backend (always works)"""
        backend = DummyBackend()
        print("✅ Dummy camera backend initialized")
        return backend
    
    def start_streaming(self):
        """Start the camera streaming"""
        if self.backend is None:
            raise RuntimeError("No camera backend available")
        
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        print(f"🎥 Camera streaming started ({self.backend.__class__.__name__})")
    
    def stop_streaming(self):
        """Stop the camera streaming"""
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
        print("⏹️ Camera streaming stopped")
    
    def _capture_loop(self):
        """Main capture loop running in background thread"""
        while self.running:
            try:
                frame = self.backend.get_frame()
                if frame is not None:
                    self.latest_frame = frame
                    
                    # Add to queue for streaming
                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()  # Remove old frame
                        self.frame_queue.put(frame, block=False)
                    except queue.Full:
                        pass  # Skip if queue is full
                
                time.sleep(0.033)  # ~30 FPS (reduced from 0.1)
            except Exception as e:
                print(f"Error in capture loop: {e}")
                time.sleep(0.5)
    
    def get_latest_frame(self) -> Optional[PILImage.Image]:
        """Get the most recent frame"""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return self.latest_frame
    
    def get_status(self) -> dict:
        """Get current streaming status"""
        return {
            "running": self.running,
            "backend": self.backend.__class__.__name__ if self.backend else "None",
            "latest_frame_available": self.latest_frame is not None,
            "queue_size": self.frame_queue.qsize()
        }


class ROS2CameraBackend:
    """ROS2 backend for Isaac Sim camera"""
    
    def __init__(self):
        self.node = Node('camera_streamer')
        self.latest_image_msg = None
        
        # Subscribe to Isaac Sim camera topic
        self.subscription = self.node.create_subscription(
            Image,
            '/rgb/camera_1',  # Adjust topic name as needed
            self._image_callback,
            10
        )
    
    def _image_callback(self, msg):
        """ROS2 image callback"""
        self.latest_image_msg = msg
    
    def get_frame(self) -> Optional[PILImage.Image]:
        """Get latest frame from ROS2"""
        # Spin once to process callbacks
        rclpy.spin_once(self.node, timeout_sec=0.01)
        
        if self.latest_image_msg is None:
            return None
        
        try:
            # Manual conversion from ROS Image to PIL Image
            # This avoids cv_bridge NumPy compatibility issues
            msg = self.latest_image_msg
            
            # Convert ROS Image data to numpy array
            if msg.encoding == 'rgb8':
                # RGB8 format: 3 channels, 8 bits per channel
                img_array = np.frombuffer(msg.data, dtype=np.uint8)
                img_array = img_array.reshape((msg.height, msg.width, 3))
            elif msg.encoding == 'bgr8':
                # BGR8 format: convert to RGB
                img_array = np.frombuffer(msg.data, dtype=np.uint8)
                img_array = img_array.reshape((msg.height, msg.width, 3))
                # Convert BGR to RGB
                img_array = img_array[:, :, [2, 1, 0]]
            elif msg.encoding == 'mono8':
                # Grayscale: convert to RGB
                img_array = np.frombuffer(msg.data, dtype=np.uint8)
                img_array = img_array.reshape((msg.height, msg.width))
                # Convert to RGB by stacking the grayscale channel
                img_array = np.stack([img_array, img_array, img_array], axis=2)
            else:
                print(f"Unsupported encoding: {msg.encoding}")
                return None
            
            # Convert to PIL Image
            pil_image = PILImage.fromarray(img_array)
            return pil_image
            
        except Exception as e:
            print(f"Error converting ROS image: {e}")
            return None


class WebcamBackend:
    """Webcam backend using OpenCV"""
    
    def __init__(self, device_id: int = 0):
        self.cap = cv2.VideoCapture(device_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
    
    def is_available(self) -> bool:
        """Check if webcam is available"""
        return self.cap.isOpened()
    
    def get_frame(self) -> Optional[PILImage.Image]:
        """Get frame from webcam"""
        if not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Convert to PIL Image
        pil_image = PILImage.fromarray(frame_rgb)
        return pil_image
    
    def __del__(self):
        if hasattr(self, 'cap'):
            self.cap.release()


class DummyBackend:
    """Dummy backend that generates synthetic images"""
    
    def __init__(self):
        self.frame_count = 0
    
    def get_frame(self) -> PILImage.Image:
        """Generate a dummy frame"""
        self.frame_count += 1
        
        # Create a simple colored image with frame counter
        width, height = 640, 480
        
        # Create gradient background
        img_array = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add gradient
        for y in range(height):
            for x in range(width):
                img_array[y, x] = [
                    (x * 255) // width,  # Red gradient
                    (y * 255) // height,  # Green gradient
                    ((x + y) * 255) // (width + height)  # Blue gradient
                ]
        
        # Add frame counter text
        pil_image = PILImage.fromarray(img_array)
        
        return pil_image


def create_camera_interface():
    """Create a standalone camera streaming interface"""
    
    # Global camera streamer instance
    camera_streamer = None
    
    def start_camera(source_choice):
        """Start camera streaming"""
        nonlocal camera_streamer
        
        try:
            if camera_streamer is not None:
                camera_streamer.stop_streaming()
            
            camera_streamer = CameraStreamer(source=source_choice.lower())
            camera_streamer.start_streaming()
            
            status = camera_streamer.get_status()
            return f"✅ Camera started with {status['backend']} backend"
        except Exception as e:
            return f"❌ Failed to start camera: {e}"
    
    def stop_camera():
        """Stop camera streaming"""
        nonlocal camera_streamer
        
        if camera_streamer is not None:
            camera_streamer.stop_streaming()
            return "⏹️ Camera stopped"
        return "❌ No camera running"
    
    def get_frame():
        """Get current camera frame"""
        if camera_streamer is not None and camera_streamer.running:
            frame = camera_streamer.get_latest_frame()
            if frame is not None:
                status = camera_streamer.get_status()
                return frame, f"📸 Frame from {status['backend']} | Queue: {status['queue_size']}"
            else:
                return None, "⏳ Waiting for frame..."
        return None, "❌ Camera not running"
    
    def get_status_info():
        """Get detailed status information"""
        if camera_streamer is not None:
            status = camera_streamer.get_status()
            return f"""
**Status:** {'🟢 Running' if status['running'] else '🔴 Stopped'}
**Backend:** {status['backend']}
**Frame Available:** {'✅' if status['latest_frame_available'] else '❌'}
**Queue Size:** {status['queue_size']}
            """.strip()
        return "❌ No camera instance"
    
    # Create Gradio interface
    with gr.Blocks(title="Simple Camera Stream", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 📹 Simple Camera Streaming")
        gr.Markdown("Stream from Isaac Sim (ROS2), webcam, or dummy source")
        
        with gr.Row():
            with gr.Column(scale=2):
                # Camera display
                camera_display = gr.Image(
                    label="Live Camera Feed",
                    type="pil",
                    height=400
                )
                
                # Frame info
                frame_info = gr.Textbox(
                    label="Frame Info",
                    value="Click 'Start Camera' to begin",
                    interactive=False
                )
            
            with gr.Column(scale=1):
                # Controls
                gr.Markdown("## 🎛️ Controls")
                
                source_choice = gr.Dropdown(
                    choices=["Auto", "ROS2", "Webcam", "Dummy"],
                    value="Auto",
                    label="Camera Source"
                )
                
                with gr.Row():
                    start_btn = gr.Button("🚀 Start Camera", variant="primary")
                    stop_btn = gr.Button("⏹️ Stop Camera", variant="secondary")
                
                refresh_btn = gr.Button("🔄 Refresh Frame", variant="secondary")
                
                # Status
                gr.Markdown("## 📊 Status")
                status_info = gr.Textbox(
                    label="Camera Status",
                    value="Ready",
                    lines=5,
                    interactive=False
                )
        
        # Event handlers
        start_btn.click(
            fn=start_camera,
            inputs=[source_choice],
            outputs=[status_info]
        )
        
        stop_btn.click(
            fn=stop_camera,
            outputs=[status_info]
        )
        
        refresh_btn.click(
            fn=get_frame,
            outputs=[camera_display, frame_info]
        )
        
        # Auto-refresh every 0.5 seconds (reduced latency)
        timer = gr.Timer(0.5)
        timer.tick(
            fn=get_frame,
            outputs=[camera_display, frame_info]
        )
        
        # Update status every 3 seconds
        status_timer = gr.Timer(3.0)
        status_timer.tick(
            fn=get_status_info,
            outputs=[status_info]
        )
    
    return demo


def add_camera_tab_to_demo(demo_blocks):
    """Add camera streaming tab to existing demo interface"""
    
    # This function can be called from demo.py to integrate camera streaming
    # For now, we'll just return the camera interface
    return create_camera_interface()


def main():
    """Main function to run standalone camera interface"""
    print("🎥 Starting Simple Camera Streaming Interface...")
    
    demo = create_camera_interface()
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,  # Different port than main demo
        share=False,
        show_error=True
    )


if __name__ == "__main__":
    main()
