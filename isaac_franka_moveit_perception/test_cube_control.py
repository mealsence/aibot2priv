#!/usr/bin/env python3
"""
Simple test script for cube position control
"""

try:
    from isaac_sim_object_control import get_cube_position, set_cube_position, list_scene_objects
    print("✅ Successfully imported cube control functions")
    
    # Test listing objects
    print("\n📋 Testing list_scene_objects...")
    objects = list_scene_objects()
    if objects["success"]:
        print(f"Found {objects['count']} objects")
        for obj in objects["objects"][:3]:  # Show first 3
            print(f"  - {obj['name']}")
    else:
        print(f"❌ Failed to list objects: {objects['error']}")
    
    # Test getting cube position
    print("\n📍 Testing get_cube_position...")
    pos_result = get_cube_position("cube_01")
    if pos_result["success"]:
        print(f"✅ Cube position: {pos_result['formatted']}")
    else:
        print(f"❌ Failed to get cube position: {pos_result['error']}")
    
    # Test setting cube position
    print("\n🎯 Testing set_cube_position...")
    if pos_result["success"]:
        # Move to a test position
        test_pos = [0.3, 0.2, 0.4]
        move_result = set_cube_position("cube_01", test_pos)
        if move_result["success"]:
            print(f"✅ Successfully moved cube to {test_pos}")
            
            # Verify the move
            verify_result = get_cube_position("cube_01")
            if verify_result["success"]:
                print(f"✅ Verified position: {verify_result['formatted']}")
            else:
                print("❌ Failed to verify position")
        else:
            print(f"❌ Failed to move cube: {move_result['error']}")
    else:
        print("❌ Cannot test position setting - couldn't get initial position")
    
    print("\n🎉 Test completed!")
    
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("💡 Make sure you're running this in Isaac Sim Python environment")
except Exception as e:
    print(f"❌ Test failed: {e}")
