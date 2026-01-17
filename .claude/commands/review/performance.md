---
name: review:performance
description: Review code for algorithmic and system-level performance issues
usage: /review:performance [SCOPE] [TARGET] [PATHS] [CONTEXT]
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
    description: 'Additional context: performance goals, latency budget, throughput, typical data sizes'
    required: false
examples:
  - command: /review:performance pr 123
    description: Review PR #123 for performance issues
  - command: /review:performance worktree "src/api/**"
    description: Review API layer for performance regressions
