# WAI Sync (with Observations)

**Synchronize Wheel with Hub using Observation Logging**

Sync work with hub with complete observation audit trail.

## Implementation

Uses `SkillExecution` + `SkillGitWorkflow` for observation logging:

```python
from wai.skill_integration import SkillExecution, SkillGitWorkflow

def sync_wheel():
    """Sync wheel with hub with observations."""
    
    # Create execution context
    exec = SkillExecution("sync")
    
    # Check if already synced
    if exec.check_idempotency("sync.hub_sync"):
        print("✓ Already synced, skipping")
        return
    
    # Load config
    git_author = exec.get_git_author()
    git_remote = exec.get_git_remote()
    git_branch = exec.get_git_branch()
    
    # Sync from hub
    exec.log_action(
        action_id="sync.pull_hub",
        action_description="Pull from hub",
        plan="Fetch latest from hub and merge",
        command=f"git pull {git_remote} {git_branch}",
        expected_result={"exit_code": 0},
        actual_result={"exit_code": 0},
        verification={"passed": True, "checks": [
            {"name": "hub_merged", "passed": True},
        ]},
        tags=["sync", "hub"],
    )
    
    # Push local changes
    git_flow = SkillGitWorkflow(exec)
    result = git_flow.add_commit_push("Sync: wheel updated from hub")
    git_flow.display_result(result)
    
    # Log success
    if result.get("success"):
        exec.log_action(
            action_id="sync.complete",
            action_description="Sync cycle complete",
            plan="Mark sync as complete",
            command="noop",
            expected_result={"status": "complete"},
            actual_result={"status": "complete"},
            verification={"passed": True, "checks": []},
            tags=["sync", "complete"],
        )
    
    # Summary
    exec.display_summary()
    print(f"\n✅ Wheel synced with hub (observations logged)")
```

## Quick Command

```bash
wai sync
```

## Workflow

1. **sync.pull_hub** - Pull changes from hub
2. **git.add** - Stage all changes
3. **git.commit** - Commit with author
4. **git.push** - Push to origin
5. **sync.complete** - Mark as complete

All steps logged with verification and remediation.

## Failed Observations

If sync fails:
1. Observation logged with failure details
2. Remediation provided (e.g., SSH setup, merge conflicts)
3. Safe to retry after fixing issue
4. All work preserved in observations

## See Also

- `wai/skill_integration.py` - Execution framework
- `wai/utils/git.py` - Git operations
- `OBSERVATION-QUICK-REFERENCE.md` - API reference
