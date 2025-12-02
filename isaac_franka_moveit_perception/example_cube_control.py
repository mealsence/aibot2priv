#!/usr/bin/env python3
"""
Example Usage: Cube Position Control in Isaac Sim

This script demonstrates how to use the Isaac Sim object control module
to change the position of cubes in your Isaac Sim scene.
"""

from isaac_sim_object_control import (
    get_cube_position, 
    set_cube_position, 
    move_cube_relative, 
    list_scene_objects,
    cleanup
)
import time


def main():
    """Main example function demonstrating cube control"""
    
    print("🎮 Isaac Sim Cube Control Example")
    print("=" * 40)
    
    try:
        # Step 1: List all objects in the scene
        print("\n📋 Step 1: Listing all objects in the scene...")
        objects_result = list_scene_objects()
        
        if not objects_result["success"]:
            print("❌ Cannot proceed - failed to list objects")
            return
        
        # Step 2: Get current cube position
        print("\n📍 Step 2: Getting current cube position...")
        current_pos_result = get_cube_position("cube_01")
        
        if not current_pos_result["success"]:
            print("❌ Cannot proceed - cube not found")
            return
        
        print(f"🎯 Current cube position: {current_pos_result['formatted']}")
        
        # Step 3: Move cube to a specific position
        print("\n🎯 Step 3: Moving cube to position [0.3, 0.2, 0.5]...")
        target_position = [0.3, 0.2, 0.5]  # 30cm X, 20cm Y, 50cm Z
        move_result = set_cube_position("cube_01", target_position)
        
        if move_result["success"]:
            print("✅ Cube moved successfully!")
            time.sleep(2)  # Wait to see the movement
        else:
            print(f"❌ Failed to move cube: {move_result['error']}")
            return
        
        # Step 4: Verify new position
        print("\n📍 Step 4: Verifying new position...")
        new_pos_result = get_cube_position("cube_01")
        if new_pos_result["success"]:
            print(f"🎯 New cube position: {new_pos_result['formatted']}")
        
        # Step 5: Move cube relative to current position
        print("\n🔄 Step 5: Moving cube relative by [0.1, -0.1, 0.0]...")
        relative_move = [0.1, -0.1, 0.0]  # 10cm forward, 10cm left, no height change
        relative_result = move_cube_relative("cube_01", relative_move)
        
        if relative_result["success"]:
            print("✅ Relative movement successful!")
            time.sleep(2)  # Wait to see the movement
        else:
            print(f"❌ Failed relative movement: {relative_result['error']}")
        
        # Step 6: Final position check
        print("\n📍 Step 6: Final position check...")
        final_pos_result = get_cube_position("cube_01")
        if final_pos_result["success"]:
            print(f"🎯 Final cube position: {final_pos_result['formatted']}")
        
        # Step 7: Move cube back to original position
        print("\n🔄 Step 7: Moving cube back to original position...")
        if current_pos_result["success"]:
            original_pos = current_pos_result["position"]
            return_result = set_cube_position("cube_01", original_pos)
            
            if return_result["success"]:
                print("✅ Cube returned to original position!")
                time.sleep(2)
            else:
                print(f"❌ Failed to return cube: {return_result['error']}")
        
        print("\n🎉 Cube control example completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Example interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during example: {e}")
    finally:
        # Always cleanup
        print("\n🧹 Cleaning up...")
        cleanup()


def demo_positions():
    """Demonstrate various cube positions"""
    
    print("🎨 Demo: Moving cube to various positions")
    print("=" * 40)
    
    positions = [
        ([0.0, 0.0, 0.5], "Center, 50cm high"),
        ([0.3, 0.3, 0.25], "Front-right, 25cm high"),
        ([-0.3, 0.3, 0.25], "Front-left, 25cm high"),
        ([0.3, -0.3, 0.25], "Back-right, 25cm high"),
        ([-0.3, -0.3, 0.25], "Back-left, 25cm high"),
        ([0.0, 0.0, 0.1], "Center, 10cm high"),
    ]
    
    try:
        for i, (position, description) in enumerate(positions):
            print(f"\n📍 Position {i+1}: {description}")
            print(f"   Moving to {position}...")
            
            result = set_cube_position("cube_01", position)
            
            if result["success"]:
                print(f"   ✅ Moved successfully!")
                time.sleep(3)  # Wait to see the position
            else:
                print(f"   ❌ Failed to move: {result['error']}")
                break
        
        print("\n🎉 Position demo completed!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")


def interactive_control():
    """Interactive cube control for testing"""
    
    print("🎮 Interactive Cube Control")
    print("=" * 30)
    print("Commands:")
    print("  get - Get current cube position")
    print("  set x y z - Set cube position (in meters)")
    print("  move dx dy dz - Move cube relative to current position")
    print("  list - List all objects in scene")
    print("  demo - Run position demo")
    print("  quit - Exit")
    print("=" * 30)
    
    try:
        while True:
            try:
                command = input("\n🎮 Enter command: ").strip().lower()
                
                if command == "quit" or command == "q":
                    break
                elif command == "get":
                    result = get_cube_position("cube_01")
                elif command == "list":
                    result = list_scene_objects()
                elif command == "demo":
                    demo_positions()
                    continue
                elif command.startswith("set "):
                    parts = command.split()
                    if len(parts) == 4:
                        try:
                            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                            result = set_cube_position("cube_01", [x, y, z])
                        except ValueError:
                            print("❌ Invalid coordinates - use numbers")
                            continue
                    else:
                        print("❌ Usage: set x y z (e.g., set 0.5 0.0 0.5)")
                        continue
                elif command.startswith("move "):
                    parts = command.split()
                    if len(parts) == 4:
                        try:
                            dx, dy, dz = float(parts[1]), float(parts[2]), float(parts[3])
                            result = move_cube_relative("cube_01", [dx, dy, dz])
                        except ValueError:
                            print("❌ Invalid coordinates - use numbers")
                            continue
                    else:
                        print("❌ Usage: move dx dy dz (e.g., move 0.1 0.0 0.0)")
                        continue
                else:
                    print("❌ Unknown command. Try: get, set, move, list, demo, quit")
                    continue
                
                # Display result if we have one
                if 'result' in locals() and result:
                    if result["success"]:
                        print("✅ Command executed successfully!")
                        if "formatted" in result:
                            print(f"   Position: {result['formatted']}")
                        elif "new_position" in result:
                            print(f"   New position: {result['new_position']}")
                    else:
                        print(f"❌ Command failed: {result['error']}")
                        
            except EOFError:
                break
            except KeyboardInterrupt:
                break
        
        print("\n👋 Goodbye!")
        
    except Exception as e:
        print(f"\n❌ Error in interactive mode: {e}")


if __name__ == "__main__":
    print("🎮 Isaac Sim Cube Control Examples")
    print("=" * 40)
    print("This script demonstrates cube position control in Isaac Sim.")
    print("Make sure you have Isaac Sim running with a scene containing 'cube_01'")
    print()
    print("Choose an example:")
    print("1. Basic example (recommended)")
    print("2. Position demo")
    print("3. Interactive control")
    print("4. Run all examples")
    
    try:
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            main()
        elif choice == "2":
            demo_positions()
        elif choice == "3":
            interactive_control()
        elif choice == "4":
            main()
            time.sleep(2)
            demo_positions()
            time.sleep(2)
            interactive_control()
        else:
            print("Running basic example...")
            main()
            
    except KeyboardInterrupt:
        print("\n⚠️ Example interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        cleanup()
