---
name: review:release
description: Review changes for safe shipping with clear versioning, rollout, migration, and rollback plans
usage: /review:release [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "CHANGELOG.md", "package.json")'
    required: false
  - name: CONTEXT
    description: 'Additional context: release process (semantic versioning/calver), rollout strategy (canary/blue-green), feature flag system, migration process'
    required: false
examples:
  - command: /review:release pr 123
    description: Review PR #123 for release safety
  - command: /review:release worktree "CHANGELOG.md package.json"
    description: Review versioning and changelog for release
