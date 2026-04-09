import json
import types
from PIL import ImageDraw, ImageFont, ImageColor, Image
import os
from google import genai
from google.genai import types
#from mbodied.types.sense.vision import Image as MImage
import numpy as np
import enum
import time

# Configuration for API rate limiting and optimization
VISION_CONFIG = {
    "enable_verification": False,   # Set to False to skip verification (faster, relies on filtering)
    "batch_verification": True,     # Use batch verification to reduce API calls
    "max_retries": 1,               # Reduced from 2 for faster processing (filtering handles quality)
    "retry_delay": 1.0,             # Seconds to wait between retries
    "api_call_delay": 0.3,          # Seconds to wait between individual API calls
    "min_success_rate": 0.3,        # Minimum success rate before retrying (30%)
}

# Credits: https://colab.research.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Spatial_understanding.ipynb#scrollTo=HghvVpbU0Uap

bounding_box_system_instructions = """
    Return bounding boxes as a JSON array with UNIQUE labels. Never return masks or code fencing. Limit to 25 objects.
    Name objects according to their unique characteristic (colors, size, position, unique characteristics, etc..).
    If there are identical objects, name them as "[object] 1", "[object] 2", etc.
    If there are no objects, return an empty array.
      """

additional_colors = [colorname for (colorname, colorcode) in ImageColor.colormap.items()]

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
chat = client.chats.create(
    model="gemini-2.0-flash",
    config = types.GenerateContentConfig(
        system_instruction=bounding_box_system_instructions)
)

near = 0.3  # Near clipping plane in meters
far = 4.0  # Far clipping plane in meters

def rate_limited_api_call(api_call_func, delay=None):
    """
    Helper function to add rate limiting to API calls.
    """
    if delay is None:
        delay = VISION_CONFIG["api_call_delay"]
    
    time.sleep(delay)
    return api_call_func()

def get_optimized_config(**overrides):
    """
    Get configuration with optional overrides.
    """
    config = VISION_CONFIG.copy()
    config.update(overrides)
    return config

def to_pixel_boxes(boxes_norm, img_w, img_h, base=1000):
    """
    Convert Gemini’s 0-…-base coordinates → absolute pixel coordinates.

    Args
    ----
    boxes_norm : list[dict]   # [{'box_2d':[y1,x1,y2,x2], 'label':…}, …]
    img_w, img_h : int        # width, height of the RGB/depth image
    base : int or float       # 1000 if Gemini uses 0-1000, 1.0 if 0-1

    Returns
    -------
    list[dict] in pixel space (integers, already clipped to image bounds)
    """
    px_boxes = []
    for b in boxes_norm:
        y1,x1,y2,x2 = b["box_2d"]

        # scale → pixel space
        y1 = int(y1 / base * img_h)
        x1 = int(x1 / base * img_w)
        y2 = int(y2 / base * img_h)
        x2 = int(x2 / base * img_w)

        # keep inside image
        y1 = max(0, min(img_h-1, y1)); y2 = max(0, min(img_h-1, y2))
        x1 = max(0, min(img_w-1, x1)); x2 = max(0, min(img_w-1, x2))

        # ensure y1<x2, x1<x2
        if y1 > y2: y1, y2 = y2, y1
        if x1 > x2: x1, x2 = x2, x1

        px_boxes.append({"label": b.get("label",""), "box_2d": [y1,x1,y2,x2]})
        #print("px_boxes: ", px_boxes)
    return px_boxes


# @title Parsing JSON output
def parse_json(json_output: str):
    # Parsing out the markdown fencing
    lines = json_output.splitlines()
    for i, line in enumerate(lines):
        if line == "```json":
            json_output = "\n".join(lines[i+1:])  # Remove everything before "```json"
            json_output = json_output.split("```")[0]  # Remove everything after the closing "```"
            break  # Exit the loop once "```json" is found
    return json_output


def pixel_to_camera_coordinates(x, y, depth, intrinsics):
    """
    From pixel (x,y) + depth [m]  →  camera-frame XYZ  (ROS optical: +X right, +Y down, +Z forward)
    """
    fx, fy, cx, cy = intrinsics["fx"], intrinsics["fy"], intrinsics["cx"], intrinsics["cy"]
    z  = depth
    x_c = (x - cx) * z / fx
    y_c = (y - cy) * z / fy          # <-- sign is *not* flipped
    return np.array([x_c, y_c, z])


def get_camera_to_world_matrix(view_matrix):
    # What you already have is row-major (world→camera, ROS optical)
    return np.linalg.inv(view_matrix)




def get_world_coordinates(bboxes, depth, intrinsics, view_matrix, task):
    """Compute 3D world coordinates for each bounding box using depth image."""

    results = []
    for bb in bboxes:
        y1, x1, y2, x2 = map(int, bb["box_2d"])
        cx_pix = (x1 + x2) // 2
        cy_pix = (y1 + y2) // 2
        if task == "check_target":
            patch = depth[cy_pix-2:cy_pix+3, cx_pix-2:cx_pix+3]  # check 5x5 patch about centre
        elif task == "detect_locations":
            patch = depth[y1:y2, x1:x2]
        valid = patch[(patch > near) & (patch < far)]
        if valid.size == 0:
            print(f"[WARN] no valid depth for {bb['label']}")
            continue
        
        depth_med = float(np.nanmedian(valid)) # the valid patch is just used to calculate the median depth
        cam_xyz = pixel_to_camera_coordinates(cx_pix, cy_pix, depth_med, intrinsics)
        print("cam_xyz: ", cam_xyz)
        centroid_camera_hom = np.append(cam_xyz, 1.0)
        cam_to_world = get_camera_to_world_matrix(view_matrix)
        world_xyz = cam_to_world @ centroid_camera_hom
        #print("Bounding box centroid in world coordinates:", world_xyz[:3])
        print(f"[{bb['label']}] Center pixel: ({cx_pix},{cy_pix}), median depth = {depth_med:.3f} m")
        print(f"   → World XYZ = {world_xyz[:3]}")

        results.append({"label": bb["label"], "world_xyz": world_xyz[:3]})
    
    return results


# Objects to exclude from detection results (case-insensitive partial match)
EXCLUDED_OBJECTS = [
    "table", "desk", "surface", "robot", "arm", "gripper", "panda", "franka",
    "floor", "wall", "background", "workspace"
]

def _should_exclude_object(label: str) -> bool:
    """Check if an object label should be excluded from results."""
    label_lower = label.lower()
    return any(excluded in label_lower for excluded in EXCLUDED_OBJECTS)


def annotate_raw(image: Image.Image, task: str):
    if task == "check_target":
        prompt = (
            "Detect the 2d bounding boxes of SMALL MANIPULABLE OBJECTS on the table (cubes, balls, bottles, cups, tools, etc.). "
            "DO NOT detect the table itself, the floor, walls, or the robot arm. "
            "Only detect objects that a robot could pick up. "
            "Use unique object name labels with colors/characteristics (e.g., 'red cube', 'blue ball'). "
            "Ensure the bounding boxes are tight around the objects. "
            "If there are no small objects, return an empty array."
        )
    elif task == "detect_locations":
        prompt = (
            "Detect the 2D bounding boxes of potential target locations in the image, "
            "such as tables, shelves, or flat surfaces. "
            "Do NOT include any objects that are on those surfaces. "
            "Keep the bounding boxes as tight as possible around the flat surfaces only. "
            "Do NOT include the legs, empty space, floor etc. "
            "If there are multiple identical locations, number them for uniqueness. "
            "If no such surfaces are visible, return an empty array."
        )
    else:
        raise ValueError(f"Unknown task: {task}. Supported tasks: 'check_target', 'detect_locations'.")

    global chat
    response = chat.send_message([image, prompt])
    print(response.text)
    bounding_boxes_json = parse_json(response.text)
    try:
        bounding_boxes = json.loads(bounding_boxes_json)
        img_w, img_h = image.size
        boxes_px = to_pixel_boxes(bounding_boxes, img_w, img_h, base=1000)
        
        # Filter out excluded objects (tables, robots, etc.)
        if task == "check_target":
            original_count = len(boxes_px)
            boxes_px = [box for box in boxes_px if not _should_exclude_object(box["label"])]
            filtered_count = original_count - len(boxes_px)
            if filtered_count > 0:
                print(f"[FILTER] Excluded {filtered_count} non-manipulable objects (tables, robots, etc.)")
        
        return boxes_px
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print("Response text:", response.text)
        chat = client.chats.create(
                model="gemini-2.0-flash",
                config = types.GenerateContentConfig(
                system_instruction=bounding_box_system_instructions)) # reinitialize chat
        return []
    

def plot_and_crop(image: Image.Image, boxes: list[dict]):
    """
    Draw boxes on `image` (for debugging) and return a list of (label, crop).
    """
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("NotoSansCJK-Regular.ttc", size=14)
    colors = [
        'red', 'green', 'blue', 'yellow', 'orange', 'pink', 'purple', 'brown',
        'gray', 'beige', 'turquoise', 'cyan', 'magenta', 'lime', 'navy', 'maroon',
        'teal', 'olive', 'coral', 'lavender', 'violet', 'gold', 'silver',
    ]

    crops = []
    for i, bb in enumerate(boxes):
        y1,x1,y2,x2 = bb["box_2d"]
        color = colors[i % len(colors)]

        # draw box + label
        draw.rectangle(((x1,y1),(x2,y2)), outline=color, width=3)
        draw.text((x1+4, y1-16), bb["label"], fill=color, font=font)

        # crop
        crop = image.crop((x1, y1, x2, y2))
        crops.append((bb["label"], crop))

    return image, crops

class VerificationResponse(enum.Enum):
    YES = "yes"
    NO = "no"

def verify_crops(crops: list[tuple[str, Image.Image]], batch_verification=True):
    """
    Send crops to Gemini-verification and return dict[label → bool_ok].
    Uses a response schema to ensure the output is either 'yes' or 'no'.
    Can batch multiple objects into a single call to reduce API usage.
    """
    import time
    
    vclient = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    results = {}
    
    if not batch_verification or len(crops) == 1:
        # Individual verification (original method)
        for label, img in crops:
            # Add delay to respect rate limits
            time.sleep(0.5)  # 500ms delay between calls
            
            prompt = f"Verify whether {label} is in the image. The image may be taken from an angle - account for distortion. If it is a location, verify that it is a flat surface."
            try:
                response = vclient.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[prompt, img],
                    config={
                        'response_mime_type': 'text/x.enum',
                        'response_schema': VerificationResponse,
                    },
                )
                
                print(f"[VERIFY] {label}: {response.text.strip()}")
                ok = response.text.strip().lower() == VerificationResponse.YES.value
                results[label] = ok
            except Exception as e:
                print(f"[VERIFY ERROR] {label}: {e}")
                results[label] = False  # Default to failed verification
        
    else:
        # Batch verification - multiple objects in one call
        print(f"[BATCH VERIFY] Processing {len(crops)} objects in single call...")
        
        # Create a simpler, more direct batch prompt
        object_list = ", ".join([f"'{label}'" for label, _ in crops])
        batch_prompt = f"For each image crop, answer YES or NO - is the labeled object visible?\nObjects to verify: {object_list}\nRespond with ONLY the object name followed by YES or NO, one per line."
        contents = [batch_prompt]
        
        for label, img in crops:
            contents.append(f"\n{label}:")
            contents.append(img)
        
        try:
            response = vclient.models.generate_content(
                model='gemini-2.0-flash',
                contents=contents
            )
            
            # Parse batch response - look for yes/no anywhere in the response
            response_text = response.text.strip().lower()
            response_lines = response_text.split('\n')
            
            for label, _ in crops:
                label_lower = label.lower()
                found_answer = False
                
                # Search through all lines for this label
                for line in response_lines:
                    line_lower = line.lower()
                    # Check if this line mentions the label
                    if label_lower in line_lower or any(word in line_lower for word in label_lower.split()):
                        if 'yes' in line_lower:
                            results[label] = True
                            print(f"[BATCH VERIFY] {label}: yes")
                            found_answer = True
                            break
                        elif 'no' in line_lower:
                            results[label] = False
                            print(f"[BATCH VERIFY] {label}: no")
                            found_answer = True
                            break
                
                if not found_answer:
                    # More lenient fallback: assume yes if object was detected by the model
                    # (since we already filtered out tables/robots)
                    results[label] = True
                    print(f"[BATCH VERIFY] {label}: yes (assumed - object detected)")
                    
        except Exception as e:
            print(f"[BATCH VERIFY ERROR] {e}")
            # Lenient fallback: accept all detected objects
            for label, _ in crops:
                results[label] = True
                print(f"[BATCH VERIFY] {label}: yes (error fallback)")
    
    print("Verification results:", results)
    return results

# annotate and verify loop -- this is the entry point for the annotation process
def annotate_image(image, depth, intrinsics, view_matrix, task, max_retries=None, enable_verification=None, batch_verification=None):
    """
    1) annotate → 2) plot+crop → 3) verify (optional).
    Always return all objects; only compute world-coordinates for verified crops.
    For failed verifications, set world_xyz to None on the last attempt.
    
    Args:
        max_retries: Maximum number of attempts (uses VISION_CONFIG default if None)
        enable_verification: Whether to perform verification (uses VISION_CONFIG default if None)
        batch_verification: Whether to batch verification calls (uses VISION_CONFIG default if None)
    """
    import time
    
    # Use configuration defaults if parameters not specified
    config = get_optimized_config()
    if max_retries is None:
        max_retries = config["max_retries"]
    if enable_verification is None:
        enable_verification = config["enable_verification"]
    if batch_verification is None:
        batch_verification = config["batch_verification"]
    
    print(f"[CONFIG] max_retries={max_retries}, verification={'enabled' if enable_verification else 'disabled'}, batch={'enabled' if batch_verification else 'disabled'}")
    
    original_image = image.copy()  # Make a copy of the original image to reset it
    
    for attempt in range(1, max_retries + 1):
        print(f"[INFO] Attempt {attempt}: Annotating{'and verifying' if enable_verification else ''} bounding boxes.")

        # Reset the image to its original state
        image = original_image.copy()

        # Step 1: Annotate the image with bounding boxes
        try:
            boxes = annotate_raw(image, task)
            if not boxes:
                print(f"[WARN] No objects detected in attempt {attempt}")
                if attempt < max_retries:
                    continue
                else:
                    return None, []
        except Exception as e:
            print(f"[ERROR] Annotation failed in attempt {attempt}: {e}")
            if attempt < max_retries:
                time.sleep(1)  # Wait before retry
                continue
            else:
                return None, []

        # Step 2: Draw bounding boxes and crop regions
        annotated_img, crops = plot_and_crop(image, boxes)

        # Auto-create detected_objects directory if it doesn't exist
        detected_objects_dir = 'detected_objects'
        if not os.path.exists(detected_objects_dir):
            os.makedirs(detected_objects_dir)
            print(f"Created directory: {detected_objects_dir}")

        # Optional: Save debug image for each attempt
        annotated_img.save(f"detected_objects/detacted_objects_attempt{attempt}.png")

        # Step 3: Verify crops (optional)
        if enable_verification:
            try:
                verdicts = verify_crops(crops, batch_verification=batch_verification)
            except Exception as e:
                print(f"[ERROR] Verification failed in attempt {attempt}: {e}")
                # If verification fails, accept all objects (fallback)
                verdicts = {bb["label"]: True for bb in boxes}
        else:
            # Skip verification - accept all detected objects
            verdicts = {bb["label"]: True for bb in boxes}
            print(f"[INFO] Verification disabled - accepting all {len(boxes)} detected objects")

        # Step 4: Compute world coordinates for verified crops, None for failed
        results = []
        verified_count = sum(1 for verdict in verdicts.values() if verdict)
        failed_count = len(boxes) - verified_count
        
        print(f"[INFO] Verification summary: {verified_count} verified, {failed_count} failed")
        
        for bb in boxes:
            label = bb["label"]
            if verdicts.get(label, False):
                try:
                    coords = get_world_coordinates([bb], depth, intrinsics, view_matrix, task)
                    world_xyz = coords[0]["world_xyz"] if coords else None
                except Exception as e:
                    print(f"[WARN] Failed to get world coordinates for {label}: {e}")
                    world_xyz = None
            else:
                world_xyz = None
            results.append({"label": label, "box_2d": bb["box_2d"], "world_xyz": world_xyz})

        # Check if we should retry
        all_verified = all(verdicts.get(bb["label"], False) for bb in boxes)
        success_rate = verified_count / len(boxes) if boxes else 0
        
        # More lenient retry conditions - only retry if success rate is very low
        config = get_optimized_config()
        should_retry = (
            not all_verified and 
            attempt < max_retries and 
            success_rate < config["min_success_rate"] and
            len(boxes) > 0
        )
        
        if should_retry:
            print(f"[INFO] Low success rate ({success_rate:.1%}), retrying...")
            time.sleep(config["retry_delay"])  # Add delay before retry to respect rate limits
            continue

        # Accept results if we have reasonable success or this is the last attempt
        print(f"[INFO] Returning {verified_count} verified objects from attempt {attempt}")
        return annotated_img, results

    print(f"[ERROR] No valid objects found after {max_retries} attempts.")
    return None, []  # Return empty results if all attempts fail
    


# utility function to update the context of the object detection chat
def update_obj_detection_context(context):
    chat.send_message(context)
    print("Context of object detection chat updated:")


def update_world_locations(world_model, detected_locations):
    """
    Update the world model with detected locations.
    
    Args:
        world_model: WorldModel instance to update
        detected_locations: List of detected locations with world coordinates
    """
    for location in detected_locations:
        label = location.get("label", "")
        world_xyz = location.get("world_xyz")
        
        if world_xyz is not None and label:
            # Update the world model with the detected location
            world_model.locations[label] = world_xyz
            print(f"[INFO] Updated world model with location: {label} at {world_xyz}")
        elif label:
            print(f"[WARNING] Location {label} detected but no world coordinates available")