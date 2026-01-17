---
name: review:ux-copy
description: Review user-facing text for clarity, consistency, actionability, and helpful error recovery
usage: /review:ux-copy [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "src/components/**", "locales/**")'
    required: false
  - name: CONTEXT
    description: 'Additional context: product tone (professional/friendly/playful), target user (developers/consumers/business), error-handling philosophy'
    required: false
examples:
  - command: /review:ux-copy pr 123
    description: Review PR #123 for UX copy issues
  - command: /review:ux-copy worktree "src/components/**"
    description: Review component copy changes
