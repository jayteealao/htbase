---
name: review:architecture
description: Review code for architectural issues including boundaries, dependencies, and layering
usage: /review:architecture [SCOPE] [TARGET] [PATHS] [CONTEXT]
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
    description: 'Additional context: architecture goals, boundaries, layering rules, established patterns'
    required: false
examples:
  - command: /review:architecture pr 123
    description: Review PR #123 for architectural issues
  - command: /review:architecture worktree "src/**"
    description: Review working tree for architectural violations
