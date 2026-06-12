from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from PIL import Image as PILImage
import numpy as np
import rclpy
import time
from two_d_img_annotation_utils import annotate_image
import tf2_ros
from geometry_msgs.msg import TransformStamped
from tf_transformations import quaternion_matrix
import matplotlib.pyplot as plt
from tf2_msgs.msg import TFMessage
import os

class ImageProvider(Node):
    def __init__(self):
        super().__init__('image_provider')
        self.bridge = CvBridge()
        self.latest_color = None
        self.latest_depth = None
        
        # TF buffer (no default listener)
        self.tf_buffer = tf2_ros.Buffer(cache_time=rclpy.duration.Duration(seconds=5.0))
        # Remove the default listener:
        # self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        # Instead, subscribe to /tf and feed the buffer manually:
        self.create_subscription(TFMessage, '/tf', self._tf_depth_cb, 10)

        self.create_subscription(Image, '/rgb/camera_1', self._color_cb, 10)
        self.create_subscription(Image, '/camera_1/depth/image_raw', self._depth_cb, 10)

    def _tf_depth_cb(self, msg):
        # Feed each transform into the buffer
        for transform in msg.transforms:
            self.tf_buffer.set_transform(transform, "tf_depth")

    def _color_cb(self, msg: Image):
        self.latest_color = msg

    def _depth_cb(self, msg: Image):
        self.latest_depth = msg

    def get_latest_rgb(self) -> PILImage.Image:
        if self.latest_color is None:
            raise RuntimeError("No color frame received yet")
        
        # Convert ROS Image to OpenCV image (NumPy array)
        cv_image = self.bridge.imgmsg_to_cv2(self.latest_color, desired_encoding='rgb8')

        # Convert OpenCV (HWC RGB) to PIL Image
        pil_image = PILImage.fromarray(cv_image)

        return pil_image


    def get_latest_depth(self) -> np.ndarray:
        if self.latest_depth is None:
            raise RuntimeError("No depth frame received yet")
        return self.bridge.imgmsg_to_cv2(self.latest_depth, '32FC1')


def _stamp_as_int(msg):
    """
    Return header time stamp as a single int nanoseconds.
    Works for ROS 2 (sec + nanosec) and ROS 1 (msg.header.stamp.to_nsec()).
    """
    h = msg.header
    if hasattr(h.stamp, "nanosec"):          # ROS 2
        return h.stamp.sec * 1_000_000_000 + h.stamp.nanosec
    else:                                    # ROS 1 compatibility
        return h.stamp.to_nsec()

def capture_image(image_provider, timeout_sec=5.0, require_view_matrix=False):
    """
    Block until we receive *new* RGB **and** depth frames.
    Optionally retrieve the view matrix using the timestamp of the depth image.
    Ensure all timestamps are within 5 seconds of each other.
    
    Args:
        image_provider: The ImageProvider instance
        timeout_sec: Timeout for waiting for frames
        require_view_matrix: If True, requires view matrix (TF transforms). If False, returns None for view_matrix.
    """
    # ---------- 0. remember the stamps of the most-recent frames ----------
    last_color_stamp = (_stamp_as_int(image_provider.latest_color)
                        if image_provider.latest_color else None)
    last_depth_stamp = (_stamp_as_int(image_provider.latest_depth)
                        if image_provider.latest_depth else None)

    start_time = time.time()

    while True:
        rclpy.spin_once(image_provider, timeout_sec=0.05)

        # Need both frames present
        if image_provider.latest_color and image_provider.latest_depth:
            new_color = _stamp_as_int(image_provider.latest_color)
            new_depth = _stamp_as_int(image_provider.latest_depth)

            # First-ever capture OR both stamps advanced?
            if (last_color_stamp is None or new_color != last_color_stamp) and \
               (last_depth_stamp is None or new_depth != last_depth_stamp):
                # Check if timestamps are within 5 seconds
                if abs(new_color - new_depth) <= 5_000_000_000:  # 5 seconds in nanoseconds
                    break    # we've got a fresh pair

        if time.time() - start_time > timeout_sec:
            raise TimeoutError("Timeout waiting for NEW RGB and depth frames")

    # ---------- convert & return ----------
    pil_rgb  = image_provider.get_latest_rgb()
    depth_np = image_provider.get_latest_depth()

    # Retrieve the view matrix using latest available transform (if required)
    view_matrix = None
    view_matrix_stamp = None
    
    if require_view_matrix:
        while time.time() - start_time < timeout_sec:
            try:
                tf_msg = image_provider.tf_buffer.lookup_transform(
                    "camera_1", "world", rclpy.time.Time())
                view_matrix = _transform_to_homogeneous(tf_msg.transform).astype(np.float32)
                view_matrix_stamp = _stamp_as_int(tf_msg)

                # Ensure view matrix timestamp is within 5 seconds of depth frame
                if abs(view_matrix_stamp - new_depth) <= 5_000_000_000:  # 5 seconds in nanoseconds
                    break
            except Exception as e:
                print("Waiting for TF...")
                rclpy.spin_once(image_provider, timeout_sec=0.05)

        if view_matrix is None:
            raise RuntimeError("Failed to get a valid view matrix within the timeout")
        # Print a warning if view_matrix is not None but not within 5s of depth
        if view_matrix is not None and view_matrix_stamp is not None and abs(view_matrix_stamp - new_depth) > 5_000_000_000:
            print(f"[WARNING] View matrix timestamp {view_matrix_stamp} is NOT within 5s of depth frame {new_depth} (diff: {abs(view_matrix_stamp - new_depth)})")

        # Debug print: camera pose in world coordinates
        # The camera pose (translation and rotation) can be extracted from the view_matrix
        camera_position = np.linalg.inv(view_matrix)[:3, 3]
        # For orientation, extract rotation matrix and convert to Euler angles if needed
    else:
        print("Skipping view matrix retrieval (not required)")


    # visualize the depth image using matplotlib and save for debug
    depth_img = np.nan_to_num(depth_np, nan=0.0)

    # Auto-create detected_objects directory if it doesn't exist
    detected_objects_dir = 'detected_objects'
    if not os.path.exists(detected_objects_dir):
        os.makedirs(detected_objects_dir)
        print(f"Created directory: {detected_objects_dir}")

    plt.figure(figsize=(8, 6))
    plt.imshow(depth_img, cmap='plasma', vmin=0, vmax=10)  # Adjust vmax as needed for your depth range
    plt.colorbar(label='Depth (meters)')
    plt.title('Depth Image (raw 32FC1)')
    plt.axis('off')  # Hide axis ticks/labels if you want
    plt.tight_layout()
    plt.savefig('detected_objects/depth_image_matplotlib.png')
    return pil_rgb, depth_np, view_matrix




def _transform_to_homogeneous(t: TransformStamped) -> np.ndarray:
    """
    Convert geometry_msgs/Transform to a 4×4 homogeneous matrix.
    """
    q = t.rotation                   # quaternion (x, y, z, w)
    M = quaternion_matrix([q.x, q.y, q.z, q.w])   # 4×4
    M[0, 3], M[1, 3], M[2, 3] = t.translation.x, t.translation.y, t.translation.z
    return M         # parent → child

def get_view_matrix(tf_buffer, camera_frame, world_frame="world",
                    node=None, timeout_sec=2.0):
    """
    Retrieve the view matrix using the TF buffer at the specified timestamp.
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        try:
            # Try to get the transform using latest available time
            tf_msg = tf_buffer.lookup_transform(camera_frame, world_frame, rclpy.time.Time())
            return _transform_to_homogeneous(tf_msg.transform).astype(np.float32)
        except Exception as e:
            #print(f"Warning: Failed to get TF: {e}")
            print("Waiting for TF...")
            
        if node is not None:
            rclpy.spin_once(node, timeout_sec=0.05)   # keep callbacks flowing
    
    raise RuntimeError(f"TF for {world_frame}->{camera_frame} not received in {timeout_sec}s")


if __name__ == '__main__':
    rclpy.init()
    image_provider = ImageProvider()
    camera_intrinsics = {"fx": 634.09, "fy": 566.49, "cx": 640, "cy": 360}
    # image received is 720x1280, focal length is 1.93, horizontal aperture is 3.896, vertical aperture is 2.453
    # fx = (focal length * width) / horizontal aperture
    # fy = (focal length * height) / vertical aperture
    # cx = width / 2
    # cy = height / 2
    rgb_msg, depth_np, view_matrix = capture_image(image_provider)
    print("view matrix\n", view_matrix)
    print(depth_np.shape)
    annotate_image(rgb_msg, depth_np, camera_intrinsics, view_matrix, task="detect_locations")

