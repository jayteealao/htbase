---
name: review:frontend-performance
description: Review frontend changes for bundle size, rendering efficiency, and user-perceived latency
usage: /review:frontend-performance [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "src/components/**")'
    required: false
  - name: CONTEXT
    description: 'Additional context: framework (React/Vue/Angular), bundle tooling (Webpack/Vite/Rollup), performance goals (LCP, FID, CLS)'
    required: false
examples:
  - command: /review:frontend-performance pr 123
    description: Review PR #123 for frontend performance issues
  - command: /review:frontend-performance worktree "src/components/**"
    description: Review component changes for rendering performance
