---
name: review:accessibility
description: Review UI changes for keyboard and assistive technology usability, avoid ARIA misuse
usage: /review:accessibility [SCOPE] [TARGET] [PATHS] [CONTEXT]
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
    description: 'Additional context: UI framework, target compliance level (WCAG 2.1 A/AA/AAA), supported browsers'
    required: false
examples:
  - command: /review:accessibility pr 123
    description: Review PR #123 for accessibility issues
  - command: /review:accessibility worktree "src/components/**"
    description: Review components for a11y violations
