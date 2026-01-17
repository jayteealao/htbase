---
name: review:reliability
description: Review code for reliability, failure modes, and operational safety under partial outages
usage: /review:reliability [SCOPE] [TARGET] [PATHS] [CONTEXT]
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
    description: 'Additional context: SLOs, failure tolerance, retry policies, critical flows'
    required: false
examples:
  - command: /review:reliability pr 123
    description: Review PR #123 for reliability issues
  - command: /review:reliability worktree "src/services/**"
    description: Review service layer for failure modes
