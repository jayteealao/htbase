---
name: review:cost
description: Review code for changes that increase cloud infrastructure costs
usage: /review:cost [SCOPE] [TARGET] [PATHS] [CONTEXT]
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
    description: 'Additional context: cloud provider (AWS/GCP/Azure), major cost centers, expected traffic'
    required: false
examples:
  - command: /review:cost pr 123
    description: Review PR #123 for cost implications
  - command: /review:cost worktree "src/api/**"
    description: Review API layer for cost increases
