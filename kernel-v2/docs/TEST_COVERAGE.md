# ProClaw Kernel v2 - Test Coverage Tracking

> This document tracks test coverage for the ProClaw Agent Kernel v2. Update this document when adding, modifying, or removing tests.

**Last Updated:** 2026-03-18
**Maintainer:** Development Team

---

## Test Structure Overview

```
kernel-v2/
├── src/                    # Inline unit tests (#[cfg(test)] modules)
│   ├── config/             # Configuration tests
│   ├── block_composer/     # Block composer tests
│   ├── scheduler/          # Scheduler tests
│   ├── coordinator/        # Coordinator tests
│   ├── skills/             # Skill tests
│   ├── personality/        # Personality tests
│   └── ...
└── tests/                  # Integration tests
    ├── integration_tests.rs    # Lock manager tests
    ├── skill_basic_tests.rs    # Skill basic tests
    ├── e2e_integration_tests.rs # End-to-end tests
    └── full_chain_integration_test.rs # Full chain tests
```

---

## Module Coverage Matrix

| Module | Unit Tests | Integration Tests | E2E Tests | Coverage | Status |
|--------|------------|-------------------|-----------|----------|--------|
| **Config** | | | | | |
| `config/app.rs` | - | - | - | Low | 🔴 Need tests |
| `config/dynamic.rs` | - | - | - | Low | 🔴 Need tests |
| `config/prompt_loader.rs` | ✅ 1 test | - | - | Medium | 🟡 Expand |
| **Block Composer** | | | | | |
| `block_composer/mod.rs` | ✅ 3 tests | - | - | Medium | 🟡 Expand |
| ~~`block_composer/cache.rs`~~ | - | - | - | N/A | ⚪ Removed |
| **Scheduler** | | | | | |
| `scheduler/context_builder.rs` | - | - | - | Low | 🔴 Need tests |
| `scheduler/output_parser.rs` | ✅ 4 tests | - | - | Good | 🟢 OK |
| `scheduler/xml_parser.rs` | ✅ 2 tests | - | - | Good | 🟢 OK |
| `scheduler/xml_models.rs` | ✅ 4 tests | - | - | Good | 🟢 OK |
| `scheduler/thread_executor.rs` | - | - | - | Low | 🔴 Need tests |
| `scheduler/batch_task_executor.rs` | ✅ 1 test | - | - | Medium | 🟡 Expand |
| `scheduler/parallel_executor.rs` | ✅ 1 test | - | - | Medium | 🟡 Expand |
| `scheduler/multi_session_orchestrator.rs` | ✅ 1 test | - | - | Medium | 🟡 Expand |
| `scheduler/time_budget_monitor.rs` | ✅ 4 tests | - | - | Good | 🟢 OK |
| `scheduler/snapshot_collector.rs` | ✅ 2 tests | - | - | Good | 🟢 OK |
| **Coordinator** | | | | | |
| `coordinator/lock_manager.rs` | ✅ 2 tests | ✅ 2 tests | - | Good | 🟢 OK |
| `coordinator/ticket.rs` | - | - | - | Low | 🔴 Need tests |
| `coordinator/skill_registry.rs` | - | ✅ 4 tests | - | Good | 🟢 OK |
| `coordinator/coordinator_impl.rs` | - | - | - | Low | 🔴 Need tests |
| **Skills** | | | | | |
| `skills/bash_skill.rs` | - | ✅ 1 test | - | Medium | 🟡 Expand |
| `skills/gateway_skill.rs` | - | - | - | Low | 🔴 Need tests |
| `skills/composer_skill.rs` | - | - | - | Low | 🔴 Need tests |
| `skills/scheduler_skill.rs` | - | - | - | Low | 🔴 Need tests |
| `skills/os_interface_skill.rs` | - | - | - | Low | 🔴 Need tests |
| **Personality** | | | | | |
| `personality/prime.rs` | - | - | ✅ 1 test | Medium | 🟡 Expand |
| `personality/config.rs` | - | - | - | Low | 🔴 Need tests |
| `personality/models.rs` | - | - | - | Low | 🔴 Need tests |
| **Agent Thread** | | | | | |
| `agent_thread/storage.rs` | ✅ 2 tests | - | - | Good | 🟢 OK |
| `agent_thread/models.rs` | - | - | - | Low | 🔴 Need tests |
| **Providers** | | | | | |
| `providers/bash.rs` | ✅ 2 tests | - | - | Good | 🟢 OK |
| `providers/memory.rs` | - | - | - | Low | 🔴 Need tests |
| **LLM** | | | | | |
| `llm/router.rs` | - | - | - | Low | 🔴 Need tests |
| `llm/client.rs` | - | - | - | Low | 🔴 Need tests |
| `llm/config.rs` | - | - | - | Low | 🔴 Need tests |
| **Auth** | | | | | |
| `auth/mod.rs` | ✅ 1 test | - | - | Medium | 🟡 Expand |
| **Session** | | | | | |
| `session/process.rs` | - | - | - | Low | 🔴 Need tests |
| **Server** | | | | | |
| `server/agent_kernel.rs` | - | - | - | Low | 🔴 Need tests |
| `server/composer_server.rs` | - | - | - | Low | 🔴 Need tests |
| **Executor** | | | | | |
| `executor/ir_executor.rs` | - | - | ✅ 1 test | Medium | 🟡 Expand |

---

## Test Inventory

### Unit Tests (Inline)

| File | Test Name | Purpose | Status |
|------|-----------|---------|--------|
| `config/prompt_loader.rs` | `test_fallback_prompt` | Verify fallback prompt when file not found | ✅ |
| `block_composer/mod.rs` | `test_block_store_operations` | Block store CRUD operations | ✅ |
| `block_composer/mod.rs` | `test_engine_compose_integration` | Block composition integration | ✅ |
| `block_composer/mod.rs` | `test_engine_dynamic_block_lifecycle` | Dynamic block lifecycle | ✅ |
| `scheduler/output_parser.rs` | `test_parse_json_response` | Parse valid JSON response | ✅ |
| `scheduler/output_parser.rs` | `test_parse_json_multiple_actions` | Parse JSON with multiple actions | ✅ |
| `scheduler/output_parser.rs` | `test_parse_xml_fallback` | XML fallback parsing | ✅ |
| `scheduler/output_parser.rs` | `test_parse_empty_response` | Handle empty response | ✅ |
| `scheduler/xml_parser.rs` | `test_parse_simple_response` | Parse simple XML | ⚪ Deprecated |
| `scheduler/xml_parser.rs` | `test_extract_from_markdown` | Extract from markdown | ⚪ Deprecated |
| `scheduler/xml_parser.rs` | `test_to_parsed_intent` | Convert to parsed intent | ✅ |
| `scheduler/xml_models.rs` | `test_roundtrip` | XML serialization roundtrip | ⚪ Deprecated |
| `scheduler/xml_models.rs` | `test_serialize_response` | Serialize agent response | ✅ |
| `scheduler/xml_models.rs` | `test_system_notice_serialization` | System notice serialization | ✅ |
| `scheduler/xml_models.rs` | `test_task_status_report` | Task status report | ✅ |
| `scheduler/batch_task_executor.rs` | `test_execute_with_short_budget` | Budget timeout handling | ✅ |
| `scheduler/parallel_executor.rs` | `test_parallel_execution_mock` | Mock parallel execution | ✅ |
| `scheduler/multi_session_orchestrator.rs` | `test_merge_results` | Result merging | ✅ |
| `scheduler/time_budget_monitor.rs` | `test_monitor_basic` | Basic monitor operations | ✅ |
| `scheduler/time_budget_monitor.rs` | `test_monitor_elapsed` | Elapsed time tracking | ✅ |
| `scheduler/time_budget_monitor.rs` | `test_time_budget_default` | Default budget values | ✅ |
| `scheduler/time_budget_monitor.rs` | `test_warning_threshold` | Warning threshold logic | ✅ |
| `scheduler/time_budget_monitor.rs` | `test_report_generation` | Report generation | ✅ |
| `scheduler/snapshot_collector.rs` | `test_snapshot_collector_new` | Collector initialization | ✅ |
| `scheduler/snapshot_collector.rs` | `test_store_and_get_snapshot` | Snapshot storage | ✅ |
| `coordinator/lock_manager.rs` | `test_acquire_and_release` | Lock acquire/release | ✅ |
| `agent_thread/storage.rs` | `test_create_and_load_thread` | Thread creation and loading | ✅ |
| `agent_thread/storage.rs` | `test_append_and_read_events` | Event append and read | ✅ |
| `providers/bash.rs` | `test_execution_success` | Bash command success | ✅ |
| `providers/bash.rs` | `test_execution_with_working_dir` | Working directory handling | ✅ |
| `auth/mod.rs` | `test_token_expiration` | Token expiration check | ✅ |

### Integration Tests (tests/)

| File | Test Name | Purpose | Status |
|------|-----------|---------|--------|
| `integration_tests.rs` | `test_full_lock_workflow` | Complete lock workflow | ✅ |
| `integration_tests.rs` | `test_multiple_directories` | Multi-directory locking | ✅ |
| `skill_basic_tests.rs` | `test_bash_skill_basic` | Basic bash skill execution | ✅ |
| `skill_basic_tests.rs` | `test_os_interface_permission_denied` | Permission check for OS interface | ✅ |
| `skill_basic_tests.rs` | `test_scheduler_permission_denied` | Permission check for scheduler | ✅ |
| `skill_basic_tests.rs` | `test_bash_read_test_file` | Read test file via bash | ✅ |
| `e2e_integration_tests.rs` | `test_e2e_prime_generates_ir` | Prime IR generation | ✅ |
| `e2e_integration_tests.rs` | `test_e2e_direct_skill_execution` | Direct skill execution | ✅ |
| `e2e_integration_tests.rs` | `test_e2e_with_real_test_file` | Real file reading | ✅ |
| `full_chain_integration_test.rs` | `test_full_chain_prime_to_execution` | Full chain execution | ✅ |

---

## Test Categories

### By Type

| Type | Count | Description |
|------|-------|-------------|
| Unit Tests | 32 | Fast, isolated tests in source files |
| Integration Tests | 10 | Tests involving multiple components |
| E2E Tests | 4 | Full system tests with real LLM calls |
| Deprecated | 4 | Tests for deprecated XML functionality |

### By Priority

| Priority | Description | Count |
|----------|-------------|-------|
| P0 - Critical | Core functionality, must pass | 20 |
| P1 - High | Important features | 15 |
| P2 - Medium | Edge cases, error handling | 10 |
| P3 - Low | Nice-to-have coverage | 5 |

---

## Coverage Goals

### Current Status (2026-03-18)

- **Unit Tests:** 32 tests
- **Integration Tests:** 10 tests
- **E2E Tests:** 4 tests
- **Total:** 46 tests

### Target Goals

| Milestone | Target | Current | Gap |
|-----------|--------|---------|-----|
| Q1 2026 | 60 tests | 46 | +14 |
| Q2 2026 | 100 tests | 46 | +54 |

### Priority Areas for New Tests

1. **🔴 High Priority (Need Tests)**
   - `config/app.rs` - Configuration loading and validation
   - `scheduler/context_builder.rs` - Context building with PromptLoader
   - `executor/ir_executor.rs` - IR execution flow
   - `session/process.rs` - Process lifecycle

2. **🟡 Medium Priority (Expand Coverage)**
   - `config/prompt_loader.rs` - Prompt loading edge cases
   - `personality/prime.rs` - More Prime scenarios
   - `skills/` - All skill implementations

3. **🟢 Low Priority (Maintenance)**
   - Add property-based tests
   - Add performance benchmarks
   - Add stress tests

---

## Test Commands

```bash
# Run all tests
cargo test

# Run only unit tests (fast)
cargo test --lib

# Run integration tests
cargo test --test integration_tests
cargo test --test skill_basic_tests
cargo test --test e2e_integration_tests
cargo test --test full_chain_integration_test

# Run with verbose output
cargo test -- --nocapture

# Run specific test
cargo test test_name

# Run tests matching pattern
cargo test "block_composer"

# Generate coverage report (requires tarpaulin)
cargo tarpaulin --out Html
```

---

## Test Data

Test data files are located in `/home/eziothean/ProClaw/test_data/`:

```
test_data/
├── os_interface_test/
│   └── README.md          # Test file for file reading tests
└── file_chain/            # File chain test data
```

---

## Changelog

### 2026-03-18
- Created TEST_COVERAGE.md document
- Removed `cache.rs` and related tests (cache mechanism removed)
- Updated test files to use new `prompts` config structure
- Added `PromptLoader` tests
- Marked XML tests as deprecated (JSON is now primary format)

### Previous
- Initial test suite created
- Integration tests for lock manager
- E2E tests for Prime Personality
- Skill execution tests

---

## Notes

### Deprecated Tests
Tests marked as "Deprecated" are for the XML communication protocol which has been replaced by JSON. These tests are kept for backward compatibility testing but are ignored by default.

### E2E Test Requirements
E2E tests require:
- Valid LLM API key (set via `OPENAI_API_KEY` or ARK API key)
- Network access for API calls
- Test data files in `test_data/` directory

### Adding New Tests
When adding new tests:
1. Add unit tests inline in the source file under `#[cfg(test)] mod tests`
2. Add integration tests to appropriate file in `tests/` directory
3. Update this document with test details
4. Ensure test passes with `cargo test`

---

## Contributors

- Development Team - Initial test suite
- Claude Code - Test coverage document and refactoring
