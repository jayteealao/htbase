---
name: review:api-contracts
description: Review API contracts for stability, correctness, and usability for consumers
usage: /review:api-contracts [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "src/api/**/*.ts")'
    required: false
  - name: CONTEXT
    description: 'Additional context: public vs internal API, versioning policy, backward-compat requirements'
    required: false
examples:
  - command: /review:api-contracts pr 123
    description: Review PR #123 for API contract issues
  - command: /review:api-contracts worktree "src/api/**"
    description: Review API layer for contract violations
