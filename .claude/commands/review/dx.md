---
name: review:dx
description: Review developer experience - make the project easier to build, run, debug, and contribute to
usage: /review:dx [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "**/*.md", ".github/**")'
    required: false
  - name: CONTEXT
    description: 'Additional context: how devs run locally, CI setup, expected onboarding path'
    required: false
examples:
  - command: /review:dx pr 123
    description: Review PR #123 for DX issues
  - command: /review:dx repo
    description: Review entire repository for DX improvements
