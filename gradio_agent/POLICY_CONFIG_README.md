---
noteId: "505d17c0ca0911f0a8726fb333224e98"
tags: []

---

# VLA Policy Configuration & Pre-loading

Complete guide for configuring and pre-loading VLA policies in the gradio_agent system.

---

## Quick Start

### 1. Configure Your Policy

Edit `policy_config.yaml`:

```yaml
# Which policy to use
policy_path: "ases200q2/Isaac_panda_pick_cube_act_20251116_101319"

# Policy type (usually "act")
policy_type: "act"

# Device: "cuda", "cpu", or null for auto-detect
device: "cuda"
```

### 2. Run With Pre-loading (Optional)

```bash
# Pre-load policy at startup (faster first execution)
python gradio_agent/demo_tool_calling.py --preload-policy

# Or run normally (loads policy on first use)
python gradio_agent/demo_tool_calling.py
```

That's it!

---

## Configuration Methods

### Method 1: YAML Config File (Recommended)

**Edit `policy_config.yaml`:**
```yaml
policy_path: "your/policy/path"
policy_type: "act"
device: "cuda"

# Optional: Robot configuration
robot:
  type: "panda_ros_position"
  id: "my_panda_follower"

# Optional: Execution parameters
execution:
  fps: 30
  default_num_steps: 300
```

✅ **Best for:** Teams, structured configs, version control

---

### Method 2: Environment Variables

```bash
export LEROBOT_POLICY_PATH="your/policy/path"
export LEROBOT_POLICY_TYPE="act"
export LEROBOT_DEVICE="cuda"

python gradio_agent/demo_tool_calling.py --preload-policy
```

✅ **Best for:** Production, CI/CD, Docker

---

### Method 3: Programmatic

```python
from robot_tools import preload_vla_policy

# Option A: Use config file defaults
preload_vla_policy()

# Option B: Explicit configuration
preload_vla_policy(
    policy_path="custom/policy",
    policy_type="act",
    device="cuda"
)
```

✅ **Best for:** Custom scripts, advanced use cases

---

## Configuration Priority

The system uses this priority order (highest to lowest):

```
1. Function Arguments     (highest)
   ↓
2. YAML Config File       (policy_config.yaml)
   ↓
3. Environment Variables  (LEROBOT_*)
   ↓
4. Default Values         (lowest)
```

**Example:** If you set `policy_path` in YAML but also export `LEROBOT_POLICY_PATH`, the YAML value wins.

---

## Policy Pre-loading

### What is Pre-loading?

Pre-loading loads the VLA policy when the application starts instead of on first use.

### When to Pre-load

✅ **Use `--preload-policy` when:**
- You know you'll be using VLA tasks
- You want consistent, fast response times
- Running demos or production deployments
- Benchmarking VLA performance

❌ **Skip pre-loading when:**
- Testing other features (vision, gripper, arm control)
- Quick prototyping of non-VLA features
- Limited GPU memory
- Want fast startup times

### How to Pre-load

**Option 1: Command-line flag (Integrated)**
```bash
python gradio_agent/demo_tool_calling.py --preload-policy
```

**Option 2: Standalone script**
```bash
# Test/verify policy loading first
python gradio_agent/preload_policy_standalone.py

# Then start your app
python gradio_agent/demo_tool_calling.py
```

**Option 3: Programmatic**
```python
from robot_tools import preload_vla_policy

# Pre-load before starting your app
preload_vla_policy()

# Now start your application
# ...
```

### Performance Impact

| Method | App Startup | First VLA Task |
|--------|-------------|----------------|
| **No pre-load** | ~2s | ~5-30s |
| **With pre-load** | ~7-32s | Instant |

The policy stays cached for the entire Python process lifetime.

---

## Available Settings

### Core Settings

| Setting | YAML Key | Env Variable | Default |
|---------|----------|--------------|---------|
| Policy Path | `policy_path` | `LEROBOT_POLICY_PATH` | `ases200q2/Isaac_panda_pick_cube_act_20251116_101319` |
| Policy Type | `policy_type` | `LEROBOT_POLICY_TYPE` | `act` |
| Device | `device` | `LEROBOT_DEVICE` | `null` (auto) |

### Robot Settings (YAML only)

```yaml
robot:
  type: "panda_ros_position"  # or panda_ros (trajectory control)
  id: "my_panda_follower"
```

### Execution Settings (YAML only)

```yaml
execution:
  fps: 30                  # Control loop frequency (Hz)
  default_num_steps: 300   # Default number of steps (~10s at 30 FPS)
```

---

## Common Scenarios

### Use a Different Policy

**YAML:**
```yaml
policy_path: "username/my-custom-policy"
```

**Env Var:**
```bash
export LEROBOT_POLICY_PATH="username/my-custom-policy"
```

---

### Run on CPU Instead of GPU

**YAML:**
```yaml
device: "cpu"
```

**Env Var:**
```bash
export LEROBOT_DEVICE="cpu"
```

---

### Use Local Policy (Not HuggingFace)

**YAML:**
```yaml
policy_path: "/home/user/my_policies/custom_policy"
```

**Env Var:**
```bash
export LEROBOT_POLICY_PATH="/home/user/my_policies/custom_policy"
```

---

### Change Robot Type

**YAML only:**
```yaml
robot:
  type: "panda_ros"  # Trajectory control (smoother but higher latency)
  id: "production_robot"
```

---

### Adjust Execution Speed

**YAML only:**
```yaml
execution:
  fps: 15                  # Slower (half speed)
  default_num_steps: 450   # Run longer (30s at 15 FPS)
```

---

## Testing & Debugging

### View Current Configuration

```bash
# View YAML config
cat gradio_agent/policy_config.yaml

# View environment variables
env | grep LEROBOT_

# Load and inspect config in Python
python -c "from robot_tools import load_policy_config; print(load_policy_config())"
```

### Test Pre-loading

```bash
# Test policy pre-loading standalone
python gradio_agent/preload_policy_standalone.py
```

### Debug Issues

```bash
# Check if YAML is loaded
python -c "from robot_tools import load_policy_config; import json; print(json.dumps(load_policy_config(), indent=2))"

# Check environment variables
env | grep LEROBOT_

# Verify PyYAML is installed
python -c "import yaml; print('PyYAML OK')"
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Config file not found** | Check: `ls -la gradio_agent/policy_config.yaml` |
| **PyYAML not installed** | Run: `pip install pyyaml` |
| **Wrong policy loaded** | Check priority: YAML > Env > Defaults |
| **Policy fails to load** | Verify path exists or HuggingFace access |
| **GPU not available** | Set `device: "cpu"` in config |
| **Out of GPU memory** | Use CPU or load smaller model |

---

## File Locations

```
gradio_agent/
├── policy_config.yaml              ← Main config (edit this)
├── preload_policy_standalone.py    ← Test pre-loading
├── demo_tool_calling.py            ← Main application
├── robot_tools.py                  ← Config loading logic
└── POLICY_CONFIG_README.md         ← This file
```

---

## Examples

### Example 1: Basic Setup

```bash
# 1. Edit config
nano gradio_agent/policy_config.yaml

# 2. Run with pre-loading
python gradio_agent/demo_tool_calling.py --preload-policy
```

---

### Example 2: Development vs Production

**Development (policy_config.yaml):**
```yaml
policy_path: "dev/test_policy"
device: "cpu"
execution:
  fps: 15  # Slower for testing
```

**Production (environment variables):**
```bash
export LEROBOT_POLICY_PATH="prod/optimized_policy_v2"
export LEROBOT_DEVICE="cuda"

python gradio_agent/demo_tool_calling.py --preload-policy
```

---

### Example 3: Multiple Policies

```bash
# Switch policies by editing config
cat > policy_config.yaml <<EOF
policy_path: "robot/pick_task_policy"
EOF

python gradio_agent/demo_tool_calling.py --preload-policy

# Or use environment variable override
export LEROBOT_POLICY_PATH="robot/place_task_policy"
python gradio_agent/demo_tool_calling.py --preload-policy
```

---

## Advanced Usage

### Custom Config Location

```bash
# Point to custom config file
export LEROBOT_CONFIG_PATH="/path/to/custom_config.yaml"
python gradio_agent/demo_tool_calling.py --preload-policy
```

### Programmatic Configuration

```python
from robot_tools import preload_vla_policy, load_policy_config, get_policy_config_value

# Load config and inspect
config = load_policy_config()
print(f"Policy: {config.get('policy_path')}")

# Get specific value with fallback
policy_path = get_policy_config_value("policy_path", default="fallback/policy")

# Pre-load with custom config
preload_vla_policy(
    config_path="/custom/config.yaml",
    policy_path="override/policy"  # This overrides config file
)
```

---

## Best Practices

### ✅ DO

1. **Use `policy_config.yaml` for team settings**
   - Version control this file
   - Document changes in commits

2. **Use environment variables for deployment**
   - CI/CD pipelines
   - Docker containers
   - Cloud deployments

3. **Test configuration before deployment**
   ```bash
   python gradio_agent/preload_policy_standalone.py
   ```

4. **Pre-load in production**
   - Consistent performance
   - Faster response times

### ❌ DON'T

1. **Don't hardcode policy paths in Python**
   - Use configuration system instead
   - More maintainable

2. **Don't mix config methods without documenting**
   - Document which method you're using
   - Note any overrides

3. **Don't forget PyYAML**
   ```bash
   pip install pyyaml
   ```

---

## Requirements

- **Python** ≥ 3.10
- **PyYAML** (for YAML config): `pip install pyyaml`
- **LeRobot** and dependencies (for policy execution)

---

## Summary

**Simplest workflow:**
1. Edit `policy_config.yaml` with your policy path
2. Run `python gradio_agent/demo_tool_calling.py --preload-policy`
3. Done!

**Configuration priority:**
```
Function Args > YAML Config > Env Vars > Defaults
```

**Pre-loading:**
- Use `--preload-policy` for faster first execution
- Skip for faster startup if not using VLA immediately

---

For more details, see:
- `config_flow.txt` - Visual configuration flow diagram
- `CONFIGURATION_SUMMARY.md` - Full implementation details
