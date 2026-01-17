---
name: review:infra
description: Review infrastructure and deployment config for safety, least privilege, and operational clarity
usage: /review:infra [SCOPE] [TARGET] [PATHS] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo | file'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or file path'
    required: false
  - name: PATHS
    description: 'Optional glob patterns to filter files (e.g., "terraform/**", "k8s/**")'
    required: false
  - name: CONTEXT
    description: 'Additional context: IaC tool (Terraform/K8s/Helm/CDK), environments, blast radius concerns, compliance requirements'
    required: false
examples:
  - command: /review:infra pr 123
    description: Review PR #123 for infrastructure safety issues
  - command: /review:infra worktree "terraform/**"
    description: Review Terraform changes for IAM and network issues
