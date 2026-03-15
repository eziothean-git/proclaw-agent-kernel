# ProClaw Documentation

This directory contains all documentation for the ProClaw project, organized by category.

## Directory Structure

### architecture/
Architecture and design documentation:
- System architecture specifications
- Component designs (BlockComposer, Memory Base, etc.)
- Gateway architecture
- Agent system design

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

## Documentation Maintenance

When adding new documentation:
1. Place it in the appropriate category directory
2. Use descriptive filenames with lowercase and hyphens
3. Move outdated docs to `deprecated/` rather than deleting them
4. Update this README if adding new categories
