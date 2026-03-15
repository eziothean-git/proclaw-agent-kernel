# Ignore Files Configuration Guide

This document explains the `.gitignore` and `.claudeignore` configurations for the ProClaw repository.

## Overview

- **`.gitignore`**: Controls what Git tracks in version control
- **`.claudeignore`**: Controls what Claude Code includes in its context

## .gitignore (Git Version Control)

### Purpose
Prevents committing unnecessary or sensitive files to the repository.

### Key Patterns Added

#### Rust Build Artifacts
```
kernel-v2/target/
kernel-v2/Cargo.lock
*.rlib
*.rmeta
**/*.rs.bk
*.pdb
```

#### Security & Secrets
```
*.key
*.pem
*.crt
*secret*.txt
*secret*.json
*secret*.yaml
*secret*.yml
.env.production
.env.staging
config/secrets/
secrets/
test_data/secret.md
test_data/**/secret*
```

#### Sisyphus Temporary Files
```
.sisyphus/boulder.json
.sisyphus/plans/
.sisyphus/*.md
!.sisyphus/README.md
```

## .claudeignore (Claude Code Context)

### Purpose
Reduces context size and focuses Claude on relevant code by ignoring:
- Build artifacts and dependencies
- Deprecated documentation
- Sensitive files
- Generated code
- Large binary files

### Categories

#### 1. Dependencies & Build Artifacts
- Node.js: `node_modules/`, lock files
- Rust: `target/`, `Cargo.lock`, compiled artifacts
- Python: `__pycache__/`, `.venv/`, `.pytest_cache/`

#### 2. Deprecated Documentation
```
deprecated/
Documents/deprecated/
agent-kernel/apps/python-kernel/
```

#### 3. Sensitive Files
```
.env*
*.key
*api_key*
*token*.json
*secret*.*
config/secrets/
```

#### 4. Data & Databases
```
*.db
*.sqlite
data/traces/
logs/
*.log
```

#### 5. Temporary & Cache
```
.sisyphus/boulder.json
.sisyphus/drafts/
.sisyphus/plans/
.cache/
temp/
tmp/
```

#### 6. Generated Files
```
*_pb.js
*_grpc_pb.js
*_pb2.py
target/**/build/**/out/*.rs
```

#### 7. Large/Binary Files
```
*.exe
*.dll
*.so
*.zip
*.tar.gz
*.mp4
*.mp3
```

#### 8. Test Reports
```
coverage/
.nyc_output/
**/test-results/
```

#### 9. Outdated Documentation
```
**/COMPILATION_ERRORS*.md
**/IMPLEMENTATION_STATUS*.md
**/PHASE*_COMPLETION.md
**/API_STATUS.md
```

### Important Files Kept

Even if they match ignore patterns, these are explicitly kept:
```
!CLAUDE.md
!README.md
!kernel-v2/README.md
!agent-kernel/README.md
!Documents/README.md
!Documents/*/README.md
```

## Security Best Practices

### Protected Patterns
- **API Keys**: `*api_key*`, `*apikey*`, `*api-key*`
- **Tokens**: `*token*.json` (except `*.example.json`)
- **Secrets**: `*secret*.*` in any format
- **Certificates**: `*.pem`, `*.crt`, `*.key`
- **Environment**: `.env*` (except `.env.example`)

### Recommendations

1. **Never commit secrets**: Use environment variables or secret management tools
2. **Use example files**: Create `.env.example` with placeholder values
3. **Document requirements**: List required environment variables in README
4. **Regular audits**: Review ignored files periodically
5. **Test before commit**: Run `git status` to verify what will be committed

## Testing Ignore Files

### Check Git Status
```bash
# See what will be committed
git status

# See what's ignored
git status --ignored

# Check specific file
git check-ignore -v path/to/file
```

### Verify Claude Context
Claude Code automatically respects `.claudeignore`. To verify:
1. Ask Claude to list files it can see
2. Check that deprecated docs and build artifacts are not mentioned

## Common Issues

### File Still Tracked by Git
If a file is already tracked by Git, adding it to `.gitignore` won't remove it:
```bash
# Remove from Git but keep locally
git rm --cached path/to/file

# Commit the removal
git commit -m "Remove tracked file"
```

### Pattern Not Working
- Check pattern syntax (use `**` for recursive matching)
- Verify file path is correct (relative to repository root)
- Test with `git check-ignore -v path/to/file`

## Maintenance

### When to Update

1. **New file types**: Add patterns for new languages or tools
2. **New secrets**: Add patterns for new credential types
3. **New build artifacts**: Add patterns for new build outputs
4. **Performance issues**: Add patterns for large files slowing down Claude

### Review Schedule

- **Monthly**: Review `.claudeignore` for outdated patterns
- **Quarterly**: Audit ignored files for accidentally ignored important files
- **After major changes**: Update patterns when adding new tools or frameworks

## Examples

### Adding a New Secret Pattern
```bash
# In .gitignore
**/credentials/*.json
!**/credentials/*.example.json
```

### Ignoring Specific Directory
```bash
# In .claudeignore
path/to/large/directory/
```

### Keeping Specific File
```bash
# In .claudeignore
large_files/
!large_files/important.md
```

## Related Files

- `.gitignore`: Git version control ignore rules
- `.claudeignore`: Claude Code context ignore rules
- `Documents/CLEANUP_SUMMARY.md`: Repository cleanup documentation
- `CLAUDE.md`: Guide for Claude Code

## Support

For questions or issues:
1. Check this guide first
2. Review Git documentation: https://git-scm.com/docs/gitignore
3. Review Claude Code documentation
4. Check repository issues for similar problems
