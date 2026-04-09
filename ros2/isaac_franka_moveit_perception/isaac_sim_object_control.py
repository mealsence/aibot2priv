#!/usr/bin/env python3
"""
Isaac Sim Object Control Module

This module provides functions to manipulate objects in NVIDIA Isaac Sim,
including changing the position of cubes and other objects in the scene.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
import sys
import os

# Try to import Isaac Sim modules
try:
    from omni.isaac.core import World
    from omni.isaac.core.objects import VisualCuboid
    from omni.isaac.core.utils.nucleus import get_assets_root_path
    from omni.isaac.core.utils.stage import add_reference_to_stage, get_current_stage
    from omni.isaac.core.utils.bounds import create_bbox_cache, compute_combined_aabb
    from omni.isaac.core.utils.transformations import tf_matrix_from_pose
    from pxr import Usd, UsdGeom, Gf, Sdf
    ISAAC_SIM_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Isaac Sim modules not available: {e}")
    print("🔄 This script must be run within Isaac Sim Python environment")
    ISAAC_SIM_AVAILABLE = False


class IsaacSimObjectController:
    """Controller for manipulating objects in Isaac Sim"""
    
    def __init__(self):
        """Initialize the Isaac Sim object controller"""
        self.world = None
        self.stage = None
        self.initialized = False
        
    def initialize(self):
        """Initialize Isaac Sim world and stage"""
        if not ISAAC_SIM_AVAILABLE:
            return False
            
        try:
            # Get or create the world
            self.world = World()
            self.stage = get_current_stage()
            self.initialized = True
            print("🤖 Isaac Sim object controller initialized")
            return True
        except Exception as e:
            print(f"⚠️ Failed to initialize Isaac Sim controller: {e}")
            return False
    
    def get_object_prim_path(self, object_name: str) -> Optional[str]:
        """Get the prim path for an object by name"""
        if not self.initialized:
            if not self.initialize():
                return None
                
        try:
            # Search for the object in the stage
            for prim in self.stage.Traverse():
                if prim.GetName() == object_name:
                    return prim.GetPath().pathString
            return None
        except Exception as e:
            print(f"⚠️ Error finding object {object_name}: {e}")
            return None
    
    def get_object_position(self, object_name: str) -> Optional[Dict]:
        """Get current position of an object"""
        if not self.initialized:
            if not self.initialize():
                return None
                
        try:
            prim_path = self.get_object_prim_path(object_name)
            if not prim_path:
                return {"success": False, "error": f"Object '{object_name}' not found"}
            
            # Get the prim and its transform
            prim = self.stage.GetPrimAtPath(prim_path)
            xform = UsdGeom.Xformable(prim)
            
            # Get the world transform
            world_transform = xform.ComputeLocalTransformation(0)
            translation = world_transform.ExtractTranslation()
            
            return {
                "success": True,
                "object_name": object_name,
                "prim_path": prim_path,
                "position": [translation[0], translation[1], translation[2]],
                "formatted": f"[{translation[0]:.3f}, {translation[1]:.3f}, {translation[2]:.3f}]"
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to get position of {object_name}: {str(e)}"}
    
    def set_object_position(self, object_name: str, position: List[float], 
                          orientation: Optional[List[float]] = None) -> Dict:
        """Set the position of an object"""
        if not self.initialized:
            if not self.initialize():
                return {"success": False, "error": "Failed to initialize Isaac Sim controller"}
                
        try:
            prim_path = self.get_object_prim_path(object_name)
            if not prim_path:
                return {"success": False, "error": f"Object '{object_name}' not found"}
            
            # Validate position
            if len(position) != 3:
                return {"success": False, "error": "Position must be a list of 3 values [x, y, z]"}
            
            # Get the prim
            prim = self.stage.GetPrimAtPath(prim_path)
            xform = UsdGeom.Xformable(prim)
            
            # Create transform matrix
            if orientation is None:
                # Default orientation (no rotation)
                orientation = [0, 0, 0, 1]  # quaternion [x, y, z, w]
            
            # Convert position and orientation to transform matrix
            translation = Gf.Vec3d(position[0], position[1], position[2])
            rotation = Gf.Rotation(Gf.Quatd(orientation[3], orientation[0], orientation[1], orientation[2]))
            transform = Gf.Matrix4d().SetTranslation(translation).SetRotation(rotation)
            
            # Clear existing transforms and set new one
            xform.ClearXformOpOrder()
            xform.AddTransformOp().Set(transform)
            
            return {
                "success": True,
                "object_name": object_name,
                "prim_path": prim_path,
                "new_position": position,
                "message": f"Successfully moved {object_name} to {position}"
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to set position of {object_name}: {str(e)}"}
    
    def list_all_objects(self) -> Dict:
        """List all objects in the current stage"""
        if not self.initialized:
            if not self.initialize():
                return {"success": False, "error": "Failed to initialize Isaac Sim controller"}
                
        try:
            objects = []
            for prim in self.stage.Traverse():
                if prim.IsA(UsdGeom.Xformable):
                    objects.append({
                        "name": prim.GetName(),
                        "path": prim.GetPath().pathString,
                        "type": prim.GetTypeName()
                    })
            
            return {
                "success": True,
                "objects": objects,
                "count": len(objects)
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to list objects: {str(e)}"}


# Global controller instance
_object_controller = IsaacSimObjectController()


def get_cube_position(cube_name: str = "cube_01") -> Dict:
    """Get the current position of a cube.
    
    Args:
        cube_name: Name of the cube (default: "cube_01")
    
    Returns:
        Dictionary with success status and position information
    """
    print(f"📍 Getting position of cube '{cube_name}'...")
    
    if not ISAAC_SIM_AVAILABLE:
        return {"success": False, "error": "Isaac Sim modules not available"}
    
    result = _object_controller.get_object_position(cube_name)
    
    if result["success"]:
        print(f"✅ Cube '{cube_name}' position: {result['formatted']}")
    else:
        print(f"❌ Failed to get cube position: {result['error']}")
    
    return result


def set_cube_position(cube_name: str, position: List[float], 
                     orientation: Optional[List[float]] = None) -> Dict:
    """Set the position of a cube.
    
    Args:
        cube_name: Name of the cube (default: "cube_01")
        position: Target position as [x, y, z] in meters
        orientation: Optional orientation as quaternion [x, y, z, w]
    
    Returns:
        Dictionary with success status and action performed
    """
    print(f"🎯 Moving cube '{cube_name}' to position {position}...")
    
    if not ISAAC_SIM_AVAILABLE:
        return {"success": False, "error": "Isaac Sim modules not available"}
    
    result = _object_controller.set_object_position(cube_name, position, orientation)
    
    if result["success"]:
        print(f"✅ Successfully moved cube '{cube_name}' to {position}")
    else:
        print(f"❌ Failed to move cube: {result['error']}")
    
    return result


def move_cube_relative(cube_name: str, delta_position: List[float]) -> Dict:
    """Move a cube by a relative offset from its current position.
    
    Args:
        cube_name: Name of the cube (default: "cube_01")
        delta_position: Relative movement as [dx, dy, dz] in meters
    
    Returns:
        Dictionary with success status and action performed
    """
    print(f"🔄 Moving cube '{cube_name}' by {delta_position}...")
    
    if not ISAAC_SIM_AVAILABLE:
        return {"success": False, "error": "Isaac Sim modules not available"}
    
    # Get current position
    current_result = get_cube_position(cube_name)
    if not current_result["success"]:
        return current_result
    
    # Calculate new position
    current_pos = current_result["position"]
    new_position = [
        current_pos[0] + delta_position[0],
        current_pos[1] + delta_position[1],
        current_pos[2] + delta_position[2]
    ]
    
    # Set new position
    return set_cube_position(cube_name, new_position)


def list_scene_objects() -> Dict:
    """List all objects in the current Isaac Sim scene.
    
    Returns:
        Dictionary with success status and list of objects
    """
    print("📋 Listing all objects in the scene...")
    
    if not ISAAC_SIM_AVAILABLE:
        return {"success": False, "error": "Isaac Sim modules not available"}
    
    result = _object_controller.list_all_objects()
    
    if result["success"]:
        print(f"✅ Found {result['count']} objects in the scene:")
        for obj in result["objects"]:
            print(f"   - {obj['name']} ({obj['type']}) at {obj['path']}")
    else:
        print(f"❌ Failed to list objects: {result['error']}")
    
    return result


def cleanup():
    """Cleanup resources"""
    global _object_controller
    
    if _object_controller.initialized and _object_controller.world:
        try:
            _object_controller.world.clear()
            _object_controller.world = None
            _object_controller.stage = None
            _object_controller.initialized = False
            print("🧹 Isaac Sim object controller cleaned up")
        except Exception as e:
            print(f"⚠️ Error during cleanup: {e}")


# Example usage and testing
if __name__ == "__main__":
    print("🧪 Testing Isaac Sim Object Control Module...")
    
    if not ISAAC_SIM_AVAILABLE:
        print("❌ This script must be run within Isaac Sim Python environment")
        print("💡 To run this in Isaac Sim:")
        print("   1. Open Isaac Sim")
        print("   2. Go to Window > Script Editor")
        print("   3. Load this script and run it")
        sys.exit(1)
    
    try:
        # Test listing objects
        result = list_scene_objects()
        
        # Test getting cube position
        result = get_cube_position("cube_01")
        
        if result["success"]:
            # Test moving cube to a new position
            new_pos = [0.5, 0.0, 0.5]  # 50cm in X, 0cm in Y, 50cm in Z
            result = set_cube_position("cube_01", new_pos)
            
            if result["success"]:
                # Test relative movement
                result = move_cube_relative("cube_01", [0.1, 0.1, 0.0])  # Move 10cm in X and Y
                
                # Get final position
                final_result = get_cube_position("cube_01")
        
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
    finally:
        cleanup()
