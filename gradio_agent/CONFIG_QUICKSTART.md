---
noteId: "72d31d40ca0911f0a8726fb333224e98"
tags: []

---

# Policy Configuration - Quick Start

## 🎯 Two-Minute Setup

### 1. Edit Configuration
```bash
nano gradio_agent/policy_config.yaml
```

Change these three lines:
```yaml
policy_path: "your/policy/path"  # Your policy location
policy_type: "act"               # Usually "act"
device: "cuda"                   # "cuda" or "cpu"
```

### 2. Run
```bash
# With pre-loading (faster first VLA task)
python gradio_agent/demo_tool_calling.py --preload-policy

# Or without pre-loading (faster startup)
python gradio_agent/demo_tool_calling.py
```

Done! ✅

---

## Configuration Priority

```
Function Arguments  (highest priority)
    ↓
YAML Config File    (policy_config.yaml)
    ↓
Environment Vars    (LEROBOT_*)
    ↓
Default Values      (lowest priority)
```

---

## Common Tasks

### Use Different Policy
```yaml
# policy_config.yaml
policy_path: "username/my-custom-policy"
```

### Run on CPU
```yaml
# policy_config.yaml
device: "cpu"
```

### Use Local Policy
```yaml
# policy_config.yaml
policy_path: "/home/user/my_policies/local_policy"
```

### Override with Environment Variable
```bash
export LEROBOT_POLICY_PATH="different/policy"
python gradio_agent/demo_tool_calling.py --preload-policy
```

---

## Pre-loading

**With pre-loading:**
- Slower startup (~7-32s)
- Instant first VLA task
- Use for: Production, demos, benchmarking

**Without pre-loading:**
- Fast startup (~2s)
- First VLA task takes 5-30s
- Use for: Development, testing non-VLA features

---

## Testing

```bash
# Test policy pre-loading
python gradio_agent/preload_policy_standalone.py

# View current config
cat gradio_agent/policy_config.yaml

# Check environment variables
env | grep LEROBOT_
```

---

## Files

- **`policy_config.yaml`** - Main configuration (edit this)
- **`preload_policy_standalone.py`** - Test pre-loading
- **`POLICY_CONFIG_README.md`** - Full documentation
- **`config_flow.txt`** - Visual flow diagram

---

## Need More?

📖 **Full documentation:** [POLICY_CONFIG_README.md](POLICY_CONFIG_README.md)

📊 **Visual guide:** [config_flow.txt](config_flow.txt)
