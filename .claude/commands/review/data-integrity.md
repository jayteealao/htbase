---
name: review:data-integrity
description: Review data integrity - ensure stored data remains correct over time, across failures, retries, and concurrent writes
usage: /review:data-integrity [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "src/models/**", "src/repositories/**")'
    required: false
  - name: CONTEXT
    description: 'Additional context: critical invariants, transactional guarantees, consistency expectations'
    required: false
examples:
  - command: /review:data-integrity pr 123
    description: Review PR #123 for data integrity issues
  - command: /review:data-integrity worktree "src/models/**"
    description: Review model layer for integrity violations
