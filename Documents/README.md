# ProClaw Documentation

This directory contains all documentation for the ProClaw project, organized by category.

## Directory Structure

### architecture/
Architecture and design documentation:
- System architecture specifications
- Component designs (BlockComposer, Memory Base, etc.)
- Gateway architecture
- Agent system design
- **PROMPT_CACHING_OPTIMIZATION.md** - Prompt 缓存优化方案（静态/动态分离、多 Provider 适配）

### plans/
Planning documents and analysis:
- Batch execution plans
- Gateway flow verification
- Feature implementation plans
- Analysis reports
- `drafts/` - Work-in-progress planning documents

### tests/
Test reports and testing documentation:
- Integration test reports
- Test plans
- Full test coverage reports

### prompts/
Prompt templates and documentation:
- System prompts for Prime Personality
- XML output format prompts
- Prompt engineering guidelines

### skills/
Skills system documentation:
- Skills README and overview
- Rust kernel skill mapping

### deprecated/
Outdated documentation kept for reference:
- Old architecture problem reports
- Completed refactor summaries
- Migration guides for completed migrations
- Historical code quality reports

## Active Documentation in Root

- `/CLAUDE.md` - Guide for Claude Code when working with this repository
- `/README.md` - Main project README
- `/agent-kernel/README.md` - Gateway (TypeScript) README
- `/agent-kernel/QUICKSTART.md` - Gateway quickstart guide
- `/kernel-v2/README.md` - Rust Kernel v2 README

## Key Architecture Documents

| Document | Description |
|----------|-------------|
| [Prompt Caching Optimization](architecture/PROMPT_CACHING_OPTIMIZATION.md) | 静态/动态分离、多 Provider 缓存策略 |
| [BlockComposer V2 Design](architecture/BLOCKCOMPOSER_V2_DESIGN.md) | Block 组装服务设计 |
| [Gateway Architecture](architecture/gateway-architecture.md) | TypeScript Gateway 架构 |
| [Agent Architecture Spec](architecture/agent_kernel_architecture_spec.md) | 完整架构规范 |

## Documentation Maintenance

When adding new documentation:
1. Place it in the appropriate category directory
2. Use descriptive filenames with lowercase and hyphens
3. Move outdated docs to `deprecated/` rather than deleting them
4. Update this README if adding new categories
