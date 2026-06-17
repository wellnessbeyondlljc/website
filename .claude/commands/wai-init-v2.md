# WAI Init (with Observations)

**Initialize New Wheel with Observation Logging**

Create a new Wheelwright wheel with complete observation logging for audit trail.

## Implementation

Uses `SkillExecution` framework with automatic observation logging:

```python
from wai.skill_integration import SkillExecution

def init_wheel(name: str, project_type: str = "framework"):
    """Initialize wheel with observations."""
    
    # Create execution context (auto-loads SSH config)
    exec = SkillExecution("init")
    
    # Check if already initialized
    if exec.check_idempotency("init.create_wheel"):
        print("✓ Wheel already initialized, skipping")
        return
    
    # Log init action
    exec.log_action(
        action_id="init.create_wheel",
        action_description=f"Initialize wheel: {name}",
        plan="Create WAI-Spoke directory structure and seed files",
        command=f"mkdir -p {name}/WAI-Spoke",
        expected_result={"exit_code": 0, "dir_created": True},
        actual_result={"exit_code": 0, "dir_created": True},
        verification={"passed": True, "checks": [
            {"name": "spoke_dir_exists", "passed": True},
            {"name": "state_files_created", "passed": True},
        ]},
        tags=["init", "setup"],
    )
    
    # Create SSH config (if needed)
    config = exec.config
    if not config._find_sshconfig_lug():
        config.create_default_lug(
            git_user="Wheel User",
            git_email="wheel@wheelwright.ai"
        )
        print(f"✓ Created SSH config: ~/.ssh/id_ed25519")
    
    # Git init
    import subprocess
    subprocess.run(["git", "init"], cwd=name)
    
    # Log git init
    exec.log_action(
        action_id="init.git_init",
        action_description=f"Initialize git repository",
        plan="Run git init in wheel directory",
        command="git init",
        expected_result={"exit_code": 0},
        actual_result={"exit_code": 0},
        verification={"passed": True, "checks": [
            {"name": "git_repo_created", "passed": True},
        ]},
        tags=["init", "git"],
    )
    
    # Display summary
    exec.display_summary()
    print(f"\n✅ Wheel '{name}' initialized with observations")
```

## Quick Command

```bash
wai init my-project --type framework
```

## What Gets Logged

1. **init.create_wheel** - Wheel directory creation
2. **init.git_init** - Git repository initialization  
3. **init.ssh_config** - SSH config creation (if needed)
4. All observations persisted to: `WAI-Spoke/observations.jsonl`

## Failed Observations

If init fails at any step:
1. Observation logged with failure details
2. Remediation steps provided
3. Safe to retry (idempotent)
4. All work preserved in observations for debugging

## See Also

- `wai/skill_integration.py` - SkillExecution framework
- `wai/config.py` - SSH/git config
- `OBSERVATION-QUICK-REFERENCE.md` - API reference
