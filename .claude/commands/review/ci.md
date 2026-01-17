---
name: review:ci
description: Review CI/CD pipeline for correctness, determinism, security, and performance
usage: /review:ci [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., ".github/workflows/**", ".gitlab-ci.yml")'
    required: false
  - name: CONTEXT
    description: 'Additional context: CI platform (GitHub Actions/GitLab CI/CircleCI/Jenkins), expected runtime, caching strategy, secrets policy'
    required: false
examples:
  - command: /review:ci pr 123
    description: Review PR #123 for CI/CD issues
  - command: /review:ci worktree ".github/workflows/**"
    description: Review GitHub Actions workflow changes
