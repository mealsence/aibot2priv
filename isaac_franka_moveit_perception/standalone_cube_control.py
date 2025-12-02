#!/usr/bin/env python3
"""
Standalone Isaac Sim Cube Position Control

This script can be run directly in Isaac Sim's Script Editor
without any external dependencies or imports.
"""

import sys
import time
from typing import Dict, List, Optional

# Try to import Isaac Sim modules
try:
    from omni.isaac.core import World
    from omni.isaac.core.utils.stage import get_current_stage
    from omni.isaac.core.utils.nucleus import get_assets_root_path
    from omni.isaac.core.objects import DynamicCuboid
    from pxr import Usd, UsdGeom, Gf, Sdf
    import omni.kit.commands
    ISAAC_SIM_AVAILABLE = True
    print("✅ Isaac Sim modules loaded successfully")
except ImportError as e:
    print(f"❌ Isaac Sim modules not available: {e}")
    print("💡 This script must be run within Isaac Sim Python environment")
    ISAAC_SIM_AVAILABLE = False


class CubeController:
    """Standalone cube controller for Isaac Sim"""
    
    def __init__(self):
        self.stage = None
        self.initialized = False
        
    def initialize(self):
        """Initialize the controller"""
        if not ISAAC_SIM_AVAILABLE:
            return False
            
        try:
            self.stage = get_current_stage()
            if not self.stage:
                print("❌ No stage found - make sure a USD scene is loaded")
                return False
                
            self.initialized = True
            print("✅ Cube controller initialized")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize: {e}")
            return False
    
    def find_cube(self, cube_name: str = "cube_01") -> Optional[str]:
        """Find a cube by name and return its prim path"""
        if not self.initialized:
            if not self.initialize():
                return None
                
        try:
            for prim in self.stage.Traverse():
                if prim.GetName() == cube_name:
                    print(f"✅ Found cube '{cube_name}' at {prim.GetPath()}")
                    return prim.GetPath().pathString
            print(f"❌ Cube '{cube_name}' not found in scene")
            return None
        except Exception as e:
            print(f"❌ Error finding cube: {e}")
            return None
    
    def get_position(self, cube_name: str = "cube_01") -> Optional[Dict]:
        """Get current position of a cube"""
        prim_path = self.find_cube(cube_name)
        if not prim_path:
            return None
            
        try:
            prim = self.stage.GetPrimAtPath(prim_path)
            xform = UsdGeom.Xformable(prim)
            
            # Get the transformation matrix
            time_code = 0.0  # Default time
            transform = xform.GetLocalTransformation(time_code)
            translation = transform.ExtractTranslation()
            
            position = [translation[0], translation[1], translation[2]]
            print(f"📍 Cube '{cube_name}' position: [{position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}]")
            
            return {
                "success": True,
                "position": position,
                "formatted": f"[{position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}]"
            }
            
        except Exception as e:
            print(f"❌ Error getting position: {e}")
            return None
    
    def set_position(self, cube_name: str, position: List[float]) -> bool:
        """Set the position of a cube"""
        if len(position) != 3:
            print("❌ Position must be [x, y, z]")
            return False
            
        prim_path = self.find_cube(cube_name)
        if not prim_path:
            return False
            
        try:
            # Method 1: Try using Isaac Sim commands
            if ISAAC_SIM_AVAILABLE:
                try:
                    # Use Isaac Sim's transform command
                    omni.kit.commands.execute(
                        "TransformPrimCommand",
                        path_to_prim=prim_path,
                        new_transform=Gf.Matrix4d().SetTranslation(Gf.Vec3d(position[0], position[1], position[2]))
                    )
                    print(f"✅ Moved cube '{cube_name}' to [{position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}] (using commands)")
                    return True
                except Exception as cmd_error:
                    print(f"⚠️ Command method failed: {cmd_error}")
            
            # Method 2: Fallback to direct USD manipulation
            prim = self.stage.GetPrimAtPath(prim_path)
            xform = UsdGeom.Xformable(prim)
            
            # Clear existing transforms
            xform.ClearXformOpOrder()
            
            # Add translate operation and set position
            translate_op = xform.AddTranslateOp()
            translate_op.Set(Gf.Vec3d(position[0], position[1], position[2]))
            
            # Force stage update
            self.stage.GetRootLayer().Save()
            
            # Method 3: Try to trigger a stage update
            try:
                from omni.isaac.core.utils.stage import update_stage
                update_stage()
            except:
                pass
            
            print(f"✅ Moved cube '{cube_name}' to [{position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}] (using USD)")
            return True
            
        except Exception as e:
            print(f"❌ Error setting position: {e}")
            return False
    
    def move_relative(self, cube_name: str, delta: List[float]) -> bool:
        """Move cube relative to current position"""
        current = self.get_position(cube_name)
        if not current:
            return False
            
        new_position = [
            current["position"][0] + delta[0],
            current["position"][1] + delta[1],
            current["position"][2] + delta[2]
        ]
        
        return self.set_position(cube_name, new_position)
    
    def list_objects(self):
        """List all objects in the scene"""
        if not self.initialized:
            if not self.initialize():
                return
                
        try:
            print("📋 Objects in scene:")
            count = 0
            for prim in self.stage.Traverse():
                if prim.IsA(UsdGeom.Xformable):
                    print(f"  - {prim.GetName()} ({prim.GetTypeName()})")
                    count += 1
                    if count >= 10:  # Limit output
                        print(f"  ... and {count} more objects")
                        break
            print(f"✅ Found {count} objects")
        except Exception as e:
            print(f"❌ Error listing objects: {e}")


def demo_cube_control():
    """Demonstration of cube control functionality"""
    print("🎮 Isaac Sim Cube Control Demo")
    print("=" * 40)
    
    if not ISAAC_SIM_AVAILABLE:
        print("❌ This script must be run in Isaac Sim")
        return
    
    controller = CubeController()
    
    # List objects
    print("\n📋 Listing objects...")
    controller.list_objects()
    
    # Get current position
    print("\n📍 Getting current cube position...")
    current = controller.get_position("cube_01")
    
    if current:
        # Move to new position
        print("\n🎯 Moving cube to [0.3, 0.2, 0.4]...")
        if controller.set_position("cube_01", [0.3, 0.2, 0.4]):
            time.sleep(2)
            
            # Move relative
            print("\n🔄 Moving cube relative by [0.1, -0.1, 0.0]...")
            if controller.move_relative("cube_01", [0.1, -0.1, 0.0]):
                time.sleep(2)
                
                # Return to original position
                print("\n🔄 Returning to original position...")
                controller.set_position("cube_01", current["position"])
    
    print("\n🎉 Demo completed!")


def interactive_control():
    """Interactive cube control"""
    print("🎮 Interactive Cube Control")
    print("=" * 30)
    print("Commands:")
    print("  get - Get cube position")
    print("  set x y z - Set position")
    print("  move dx dy dz - Move relative")
    print("  list - List objects")
    print("  demo - Run demo")
    print("  quit - Exit")
    print("=" * 30)
    
    controller = CubeController()
    
    while True:
        try:
            command = input("\n> ").strip().lower()
            
            if command in ["quit", "q", "exit"]:
                break
            elif command == "get":
                controller.get_position("cube_01")
            elif command == "list":
                controller.list_objects()
            elif command == "demo":
                demo_cube_control()
            elif command.startswith("set "):
                parts = command.split()
                if len(parts) == 4:
                    try:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        controller.set_position("cube_01", [x, y, z])
                    except ValueError:
                        print("❌ Invalid numbers")
                else:
                    print("❌ Usage: set x y z")
            elif command.startswith("move "):
                parts = command.split()
                if len(parts) == 4:
                    try:
                        dx, dy, dz = float(parts[1]), float(parts[2]), float(parts[3])
                        controller.move_relative("cube_01", [dx, dy, dz])
                    except ValueError:
                        print("❌ Invalid numbers")
                else:
                    print("❌ Usage: move dx dy dz")
            else:
                print("❌ Unknown command")
                
        except (EOFError, KeyboardInterrupt):
            break
    
    print("👋 Goodbye!")


# Main execution
if __name__ == "__main__":
    print("🎮 Isaac Sim Standalone Cube Control")
    print("=" * 40)
    print("This script controls cube positions in Isaac Sim")
    print("Make sure you have a scene loaded with 'cube_01'")
    print()
    print("Choose mode:")
    print("1. Demo (automatic)")
    print("2. Interactive (manual control)")
    
    try:
        choice = input("\nEnter choice (1-2): ").strip()
        
        if choice == "2":
            interactive_control()
        else:
            demo_cube_control()
            
    except (EOFError, KeyboardInterrupt):
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
