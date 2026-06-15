# WAI Stewardship Framework

Operational agreement for AI working on Wheelwright framework development.
Prevents missteps by codifying scope, responsibility, methodology.

## 1. SCOPE: Framework vs Spokes

NEVER Modify:
  - WAI-Spoke/ folders (actual wheel session state)
  - Individual wheel configurations

ALWAYS Modify (Framework):
  - wai/ directory (core code)
  - templates/commands/ (skills)
  - templates/WAI-Spoke/ (spoke template)

Pattern: Framework changes in templates, then teach distributes to spokes

## 2. BENCHMARK DESIGN: Framework-Only

Framework Owns:
  - wai-benchmark.md skill
  - benchmark-design-v1 lug (reproducible)
  - benchmarks/ directory
  - 6 modules with baseline=50.0

Never ad-hoc benchmarks. Always reference benchmark-design-v1 lug.

## 3. SKILLS AS AUTHORITATIVE SOURCE

Skills document procedures, parameters, triggers, output.

Test: Can you rebuild CLI from 16 skill files alone?
  YES = Skills are complete
  NO = Skills have gaps, fix them

## 4. DECISIONS: Log Impact >= 8

Architectural decisions with impact 8+ logged to WAI-State.json

## 5. TESTING: All Changes

Skill changes: unit + integration + docs tests
Architecture: E2E + integration tests
Benchmark: use 6-module design

No tests = cannot propagate

## 6. TEACHING: Propagation Pipeline

Framework → templates → manifest → teach → spokes

Never hand-edit spokes. Let teach handle it.

## 7. ARCHITECTURE LAYERS: 5 Tiers

Layer 1: Entry (4 skills) - navigation
Layer 2: Orchestration (2) - lifecycle
Layer 3: Hub Sync (2, framework-only) - teach/learn
Layer 4: Recovery (2) - crash
Layer 5: Governance (6, auto) - constraints

Each skill one responsibility.

## 8. DOCUMENTATION: Not Inline Rules

CLAUDE.md: <50 lines (session protocol)
README.md: <100 lines (orientation)
Inline rules: 0 (all in skills)

Total context: <150 lines

## 9. REVIEW BEFORE PROPAGATION

Checklist:
  - Scope correct
  - Skills updated
  - Tests passing
  - README in templates
  - Manifest updated
  - Decision logged (if impact >= 8)
  - Benchmark codified

All checked = ready to teach

## 10. MISSTEP RECOVERY

If you modify WAI-Spoke/ directly:
  1. Note it
  2. Undo
  3. Redo in templates
  4. Test teach
  5. Document

## Summary

Scope: framework + templates only
Spokes: updated via teach, never hand-edit
Skills: source of truth
Benchmarks: codified, reproducible
Tests: required for all changes
Documentation: rules in skills, not inline
Teaching: framework→templates→manifest→teach→spokes
Review: checklist before propagation

Reference this skill when in doubt.
