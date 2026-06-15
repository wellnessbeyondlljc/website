# Idempotency Test Implementation Plan

**Status:** Test scaffolds complete, ready for implementation  
**Created:** 2026-03-19  
**Context:** Support for epic-session15-fleet-evolution  

## What's Been Delivered

### Test Scaffolds Created ✓
- `test_closeout_replay.py` - Tests closeout operation idempotency
- `test_concurrent_closeout.py` - Tests concurrent operation handling
- `test_signal_deduplication.py` - Tests signal publishing deduplication
- `test_migration_resume.py` - Tests migration checkpoint/resume

### Test Infrastructure ✓
- `utils/spoke_factory.py` - Creates test spokes and hubs with realistic data
- `utils/assertions.py` - Custom assertions for WAI state validation
- `utils/concurrency_helper.py` - Multi-process testing utilities
- `run_tests.py` - Test orchestration and reporting

### Test Coverage Designed ✓
- **Closeout Replay:** Same operation twice should skip gracefully
- **Concurrent Operations:** File locking and serialization verification
- **Signal Deduplication:** Prevention of duplicate signal entries
- **Migration Resume:** Interrupted operations resume from checkpoints

## Missing Prerequisites for Implementation

### 1. Actual Closeout Implementation
**Current State:** Test scaffolds exist but call mock implementations  
**Required:** 
- Real closeout logic that can be called from tests
- Proper lug reconciliation (Step 1 of wai-closeout.md)
- Signal extraction (Step 2)
- State updates (Step 5)
- Git operations (Steps 11-12)

**Integration Point:**
```python
# In test files, replace mock implementations:
def _execute_closeout(self) -> Dict[str, Any]:
    # TODO: Call actual closeout implementation
    from wai.closeout import execute_closeout_protocol
    return execute_closeout_protocol(self.spoke_dir)
```

### 2. File Locking Infrastructure
**Current State:** Test framework expects lock files but no implementation exists  
**Required:**
- `WAI-Spoke/.closeout.lock` file creation in closeout operations
- `WAI-Spoke/.migration.lock` for migration operations  
- Atomic lock acquisition/release
- Proper cleanup on process failure

**Expected Behavior:**
- Concurrent operations detect existing locks and abort gracefully
- Lock files contain process info for debugging
- Stale lock cleanup on next operation

### 3. Migration Checkpoint System
**Current State:** Test framework validates checkpoint files but no system exists  
**Required:**
- `.migration-checkpoint.json` files for interrupted migrations
- Resume logic that continues from last completed step
- Version tracking to prevent redundant migrations
- Rollback capability for failed migrations

**Schema:**
```json
{
  "migration_id": "migrate-2.0.15-to-2.0.18",
  "started_at": "2026-03-19T10:00:00Z",
  "target_version": "2.0.18",
  "files_to_copy": ["templates/commands/wai.md", ...],
  "files_completed": ["templates/commands/wai.md"],
  "state_updated": false
}
```

### 4. Signal Deduplication Logic
**Current State:** Tests validate deduplication but no implementation exists  
**Required:**
- Duplicate detection in `WAI-Signals.jsonl` appends
- Teaching file deduplication by timestamp
- Hub-side duplicate filtering for cross-spoke signals
- Idempotent signal adoption in Step 3a of wai.md

**Implementation Points:**
- wai-closeout.md Step 9b (Signal Teach)
- wai.md Step 3a (Teaching adoption)
- WAI-Signals.jsonl append operations

### 5. Test Execution Environment
**Current State:** Tests are scaffolded but not runnable  
**Required:**
- Fix import path issues (utils modules not found)
- Mock implementation completion for runnable tests  
- Integration with existing test infrastructure
- CI/CD pipeline integration

## Implementation Phases

### Phase 1: Foundation (1-2 weeks)
1. **Fix Import Issues**
   - Add proper `__init__.py` files
   - Fix Python path configuration
   - Resolve mock object type issues

2. **Mock Implementation Completion**
   - Complete mock closeout logic in test files
   - Add realistic file operations
   - Implement basic state transitions

3. **Basic Test Execution**
   - Get tests running with mock implementations
   - Validate test framework functionality
   - Establish CI integration

### Phase 2: Real Implementation Integration (2-3 weeks)
1. **File Locking System**
   - Implement lock file creation/cleanup
   - Add concurrent operation detection
   - Test with real multi-process scenarios

2. **Closeout Implementation**
   - Integrate with real closeout logic
   - Test idempotency with actual operations
   - Validate git operation handling

3. **Signal System**
   - Add deduplication to signal operations
   - Test teaching file generation
   - Validate hub distribution

### Phase 3: Migration & Advanced Features (1-2 weeks)
1. **Migration Checkpoints**
   - Implement checkpoint save/restore
   - Add interruption handling
   - Test fleet upgrade scenarios

2. **Performance & Reliability** 
   - Add stress testing for concurrent operations
   - Test corruption recovery scenarios
   - Performance impact measurement

## Integration with Existing Framework

### Test Suite Integration
- Add to existing `benchmarks/e2e/test_skills.py` infrastructure
- Use existing test patterns and assertions
- Integrate with `run-integration-tests.sh`

### Quality Gates
- Add idempotency tests to shipit quality gates
- Require passing tests before releases
- Include in regression testing suite

### Documentation
- Update skill documentation with idempotency guarantees
- Add troubleshooting guides for concurrent operations
- Document migration resume procedures

## Success Metrics

### Functional
- All 4 test categories pass consistently
- Concurrent operations handle contention gracefully  
- Interrupted migrations resume successfully
- No duplicate signals in production scenarios

### Performance
- Test suite completes in <5 minutes
- Concurrency overhead <20% performance impact
- Migration resume saves >80% of work on interruption
- Zero file corruption in stress tests

### Quality
- Tests are deterministic (no flaky failures)
- Clear error messages for all failure modes
- Good coverage of edge cases and error conditions
- Actionable feedback for developers

## Risk Mitigation

### High-Risk Areas
1. **Multi-process testing** - Complex to debug, potential race conditions
2. **Git operation mocking** - Real git required for realistic testing  
3. **File system timing** - OS-dependent behavior in concurrent scenarios
4. **Mock vs real gaps** - Mocks may not capture real-world failure modes

### Mitigation Strategies
1. **Comprehensive logging** - All operations logged for debugging
2. **Graceful degradation** - Tests skip if environment doesn't support features
3. **Multiple test environments** - Test on Linux, macOS, Windows
4. **Progressive integration** - Start with mocks, gradually replace with real implementations

## Next Immediate Steps

1. **Fix import issues** - Add proper Python path handling
2. **Complete mock implementations** - Make tests runnable
3. **Integrate with existing test framework** - Use established patterns
4. **Create minimal viable test** - One fully working test as proof of concept
5. **Plan real implementation integration** - Design interfaces between tests and framework code

---

**Delivered Artifacts:**
- ✅ Test plan and strategy
- ✅ Test scaffolds for all 4 scenarios  
- ✅ Test infrastructure (factories, assertions, concurrency helpers)
- ✅ Expected behavior documentation
- ✅ Implementation roadmap

**Ready for:** Framework team to implement actual operations and integrate with test scaffolds.