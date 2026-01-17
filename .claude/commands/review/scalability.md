---
name: review:scalability
description: Review code for scalability issues under higher load, larger datasets, and more tenants
usage: /review:scalability [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "src/**/*.ts")'
    required: false
  - name: CONTEXT
    description: 'Additional context: expected growth, concurrency, data volume, multi-tenant architecture'
    required: false
examples:
  - command: /review:scalability pr 123
    description: Review PR #123 for scalability issues
  - command: /review:scalability worktree "src/services/**"
    description: Review service layer for scale bottlenecks
