# Gripper Control Module

A standalone Python module for controlling robot grippers that can be easily imported into other repositories controlled by LLMs.

## Features

- **Simple Interface**: Clean, LLM-friendly function signature
- **Standardized Responses**: Consistent dictionary return format
- **Error Handling**: Built-in validation and error reporting
- **Standalone**: No external dependencies beyond Python standard library
- **Easy Integration**: Simple import and use in any Python project

## Function Signature

```python
def control_gripper(action: str, force: float = 0.5) -> Dict:
    """Control the robot gripper.
    
    Args:
        action: Gripper action - "open", "close", or "grasp"
        force: Grip force between 0.0 and 1.0 (for close/grasp actions)
    
    Returns:
        Dictionary with success status and action performed
    """
```

## Usage

### 1. Copy the Module

Copy `gripper_control_module.py` to your target repository.

### 2. Import and Use

```python
from gripper_control_module import control_gripper

# Open gripper
result = control_gripper("open")
print(result)
# Output: {"success": True, "action": "opened", "message": "Gripper opened"}

# Close gripper with default force (0.5)
result = control_gripper("close")
print(result)
# Output: {"success": True, "action": "close", "force": 0.5, "message": "Gripper closed with force 0.5"}

# Grasp with custom force
result = control_gripper("grasp", 0.8)
print(result)
# Output: {"success": True, "action": "grasp", "force": 0.8, "message": "Gripper grasped with force 0.8"}
```

### 3. Response Format

All responses follow this structure:

**Success Response:**
```python
{
    "success": True,
    "action": "opened|closed|grasped",
    "message": "Description of action",
    "force": 0.5  # Only for close/grasp actions
}
```

**Error Response:**
```python
{
    "success": False,
    "error": "Error description"
}
```

## Supported Actions

| Action | Description | Force Parameter |
|--------|-------------|-----------------|
| `"open"` | Open gripper to maximum width | Not used |
| `"close"` | Close gripper completely | Optional (0.0-1.0) |
| `"grasp"` | Close gripper with specific force | Required (0.0-1.0) |

## Force Values

- **0.0**: Minimum force (gentle grip)
- **0.5**: Medium force (default)
- **1.0**: Maximum force (strong grip)

## Testing

Run the module directly to test:

```bash
python3 gripper_control_module.py
```

Or test the example usage:

```bash
python3 example_usage.py
```

## Integration with LLM Systems

This module is designed to work seamlessly with LLM-controlled systems:

1. **Clear Function Names**: Descriptive function and parameter names
2. **Structured Output**: Consistent dictionary responses for easy parsing
3. **Error Handling**: Graceful error responses for invalid inputs
4. **Documentation**: Comprehensive docstrings for LLM understanding

## Example LLM Prompt

```
You can control the robot gripper using the control_gripper function:
- control_gripper("open") - opens the gripper
- control_gripper("close") - closes the gripper with medium force
- control_gripper("grasp", 0.8) - grasps with 80% force

The function returns a dictionary with success status and details.
```

## Requirements

- Python 3.6+
- No external packages required
- Only uses Python standard library (`time`, `typing`)
