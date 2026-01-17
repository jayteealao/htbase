---
name: review:migrations
description: Review database migrations for safety, compatibility, and operability in production
usage: /review:migrations [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter migration files (e.g., "migrations/**/*.sql")'
    required: false
  - name: CONTEXT
    description: 'Additional context: DB type, deployment style, online migration requirements, table sizes'
    required: false
examples:
  - command: /review:migrations pr 123
    description: Review PR #123 for migration safety issues
  - command: /review:migrations worktree "migrations/**"
    description: Review migration files for production safety
