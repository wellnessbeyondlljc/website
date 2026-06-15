# Wheelwright Idempotency Test Suite

**Purpose:** Verify canonical Wheelwright operations are idempotent and concurrency-safe to support fleet evolution at scale.

**Context:** Based on spoke fleet audit findings from epic-session15-fleet-evolution, concurrent operations and replay scenarios expose race conditions and non-idempotent behavior.

## Test Scenarios

### 1. Closeout Replay Idempotency
- **Target:** `wai-closeout.md` Steps 1-12
- **Challenge:** Replaying same closeout twice should detect completion and skip gracefully
- **Critical Points:** Lug reconciliation (Step 1), signal extraction (Step 2), git operations (Step 11-12)

### 2. Concurrent Closeout Operations  
- **Target:** Multiple agents running closeout on same spoke simultaneously
- **Challenge:** File locking/serialization to prevent corruption
- **Critical Points:** WAI-State.json updates, WAI-Lugs.jsonl appends, git operations

### 3. Signal Publication Deduplication
- **Target:** `wai-closeout.md` Step 9b (Signal Teach)
- **Challenge:** Duplicate signal publication should deduplicate at source or destination  
- **Critical Points:** Teaching file creation, WAI-Signals.jsonl appends, hub distribution

### 4. Interrupted Migration Replay
- **Target:** Framework upgrade and spoke migration operations
- **Challenge:** Should resume from checkpoint, not restart from beginning
- **Critical Points:** Version tracking, file copying, state updates

## Test Structure

```
tests/idempotency/
├── README.md                    # This file
├── test_closeout_replay.py      # Closeout replay scenarios
├── test_concurrent_closeout.py  # Concurrent operation scenarios  
├── test_signal_deduplication.py # Signal publishing deduplication
├── test_migration_resume.py     # Migration checkpoint/resume
├── fixtures/                    # Test data and mock spokes
│   ├── mock_spoke_basic/        # Minimal spoke for testing
│   ├── mock_spoke_with_work/    # Spoke with active lugs
│   └── scenarios/               # Specific test scenarios
├── utils/                       # Test utilities
│   ├── spoke_factory.py         # Create test spokes
│   ├── concurrency_helper.py    # Multi-process test utilities
│   └── assertions.py            # Custom assertions for WAI state
└── integration/                 # End-to-end scenarios
    ├── test_fleet_upgrade.py    # Full fleet upgrade simulation
    └── test_spoke_corruption.py # Corruption detection/recovery
```

## Test Categories

### Unit Tests (Fast)
- Individual operation idempotency
- File-level locking behavior  
- Schema validation
- Edge case handling

### Integration Tests (Medium)
- Multi-step operation chains
- Cross-file consistency
- Hub-spoke communication
- State transition validation

### Concurrency Tests (Slow)
- Multi-process race conditions
- Distributed spoke operations
- Network partition scenarios
- Lock contention simulation

## Infrastructure Requirements

### Mock System
- **Mock Spoke Factory:** Generate test spokes with various states
- **Time Control:** Deterministic timestamps for replay testing
- **File System Isolation:** Temporary directories, cleanup automation
- **Git Simulation:** Mock repositories for commit/push testing

### Concurrency Framework  
- **Process Orchestration:** Launch multiple test agents simultaneously
- **Synchronization Points:** Barriers for race condition testing
- **Resource Contention:** Simulate realistic file system delays
- **Failure Injection:** Network timeouts, disk errors, interruptions

### Assertion Framework
- **State Comparison:** Deep diff of WAI-State.json before/after
- **File Integrity:** Verify JSON schema, no corruption  
- **Idempotency Checks:** Multiple runs produce same final state
- **Consistency Validation:** Cross-file references remain valid

## Expected Behaviors

### Closeout Replay
- **First run:** Full closeout execution, all steps complete
- **Second run:** Detection of completed state, graceful skip
- **Outcome:** Identical final state, no duplicate operations

### Concurrent Closeout
- **Scenario:** Two agents start closeout on same spoke simultaneously  
- **Expected:** One proceeds, other waits or aborts cleanly
- **Outcome:** Single consistent final state, no corruption

### Signal Deduplication
- **Scenario:** Same signal published multiple times
- **Expected:** First publication succeeds, subsequent ones skipped
- **Outcome:** Single signal entry, no duplicates in destination

### Migration Resume
- **Scenario:** Migration interrupted mid-process
- **Expected:** Resume from last checkpoint, don't restart
- **Outcome:** Successful completion, no redundant operations

## Missing Prerequisites

### Test Infrastructure
1. **Concurrent Test Runner:** Framework for multi-process testing
2. **Mock Hub/Spoke Factory:** Generate test scenarios with realistic data
3. **File System Monitoring:** Track file operations for race detection
4. **State Comparison Tools:** Deep diff for WAI files
5. **Test Data Generation:** Representative spoke states and work scenarios

### Framework Enhancements
1. **Operation Logging:** Track what operations are in progress
2. **Lock Files:** Prevent concurrent modification of critical files  
3. **Checkpoint Markers:** Enable migration resume from interruptions
4. **Deduplication Logic:** Built-in duplicate detection for signals
5. **State Validation:** Consistency checks for cross-file references

## Success Criteria

### Functionality
- All idempotency scenarios pass with deterministic outcomes
- Concurrent operations handle contention gracefully
- Signal deduplication prevents duplicate entries  
- Migration resume works from any interruption point

### Quality  
- Tests are deterministic (no flaky results)
- Clear failure messages identify specific issues
- Test suite completes in reasonable time (<5 minutes)
- Good coverage of edge cases and error conditions

### Integration
- Tests integrate with existing framework test patterns
- Compatible with CI/CD pipeline execution
- Provides actionable feedback for development
- Supports regression testing for future changes

---

**Next Steps:**
1. Implement basic test infrastructure (spoke factory, assertions)
2. Create closeout replay test as proof of concept
3. Add concurrent operation testing framework  
4. Expand to cover signal deduplication and migration scenarios
5. Integrate with existing benchmarks/e2e test suite