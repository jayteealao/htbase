---
description: Orchestrate complete release workflow for any project type with version bumping, changelog generation, and git operations
argument-hint: "[version-type] [--message \"Custom message\"] [--package \"name\"] [--config \"path\"]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
  - Skill
---

# Release Automation Command

Comprehensive release workflow automation for **any project type**: Node.js, Python, Rust, Go, Java, generic projects, Claude Code plugins, and monorepos. Handles version bumping, changelog generation, documentation synchronization, validation, and git operations with configurable patterns and hooks.

## Usage

```bash
# Auto-detect project type and version bump
/release

# Explicit version bump type
/release minor
/release major
/release patch

# Custom commit message
/release --message "Special release with custom message"

# Monorepo: release specific package
/release --package "my-lib"

# Custom configuration file
/release --config ".releaserc.json"

# Combine options
/release minor --package "my-lib" --message "Breaking changes"
```

## Arguments

- **version-type** (optional): "major" | "minor" | "patch" | "auto" (default)
  - Auto-detection uses conventional commits to determine bump type
  - Explicit type overrides auto-detection
- **--message** (optional): Custom commit message (overrides changelog generation)
- **--package** (optional): Package name for monorepo releases
- **--config** (optional): Path to custom configuration file (default: `.release-config.json`)

## Project Type Support

The command automatically detects and supports:

- **Node.js/npm**: `package.json` versioning
- **Python**: `pyproject.toml`, `setup.py`, `__version__.py`
- **Rust**: `Cargo.toml` versioning
- **Go**: Git tag-based versioning
- **Java/Gradle**: `build.gradle`, `gradle.properties`, `pom.xml`
- **Generic**: `VERSION`, `version.txt` files
- **Claude Code Plugins**: `.claude-plugin/plugin.json`
- **Monorepos**: Multiple packages with independent versions

## Release Workflow

The command executes through 7 orchestrated phases:

---

## Phase 1: Project Detection & Configuration

**Objective:** Detect project type, load configuration, and validate git state.

### Steps

1. **Parse Command Arguments**

   Extract version-type, package, config, and custom message from command line:
   ```
   args: [version-type] [--package "name"] [--config "path"] [--message "text"]
   ```

2. **Detect Project Type and Load Configuration**

   Use the Skill tool to invoke the `detect-project-type` skill. Pass any relevant arguments from the command line (--config path, --package name).

   The `detect-project-type` skill will:
   - Analyze the project directory structure
   - Detect the project type (nodejs/python/rust/go/java/generic/claude-plugin/monorepo)
   - Load or generate appropriate release configuration
   - Return the configuration including:
     - Project type
     - Version files and adapters
     - Changelog file path
     - Tag pattern
     - Documentation files
     - Validation settings

   Store the returned configuration for use in subsequent phases.

3. **Display Project Configuration**

   After the skill completes, summarize the detected configuration for the user:
   ```
   Detected project configuration:
   - Project type: {project_type}
   - Version files: {version_files}
   - Tag pattern: {tag_pattern}
   - Configuration source: {config_source}
   ```

4. **Handle Configuration Errors**

   If project type is "unknown" or configuration has errors:
   ```
   AskUserQuestion:
   - Question: "Could not detect project type. What would you like to do?"
   - Options:
     - Create .release-config.json manually
     - Specify project type
     - Cancel release
   ```

4. **Validate Git State**

   Check for clean git state:
   ```bash
   git status --porcelain
   ```

   If uncommitted changes exist:
   ```
   AskUserQuestion:
   - Question: "Uncommitted changes detected. How would you like to proceed?"
   - Options:
     - Include in release (recommended)
     - Show diff first
     - Cancel release
   ```

5. **Verify Branch**

   Check current branch:
   ```bash
   git branch --show-current
   ```

   If not on master/main, prompt:
   ```
   AskUserQuestion:
   - Question: "You're on branch '{branch}'. Releases are typically done from master. Continue anyway?"
   - Options:
     - Continue on current branch
     - Switch to master
     - Cancel
   ```

### Phase 1 Output

- Project type detected and configuration loaded
- Clean or handled git state
- Current branch validated
- Ready for version determination

---

## Phase 2: Version Determination

**Objective:** Calculate the appropriate semantic version bump and get user confirmation.

### Steps

1. **Invoke Version Bump Skill**

   Use the Skill tool to invoke the `version-bump` skill. Provide context about:
   - The project configuration obtained from Phase 1
   - The version type from command arguments (major/minor/patch) or "auto" for automatic detection

   The `version-bump` skill will:
   - Read the current version from version files
   - Analyze git commits since the last release tag
   - Calculate the appropriate semantic version bump
   - Return:
     - current_version
     - new_version
     - bump_type (major/minor/patch)
     - reasoning (commit analysis)
     - last_tag

2. **Display Version Bump**

   Show user the calculated version bump:
   ```
   Current version: {current_version}
   New version: {new_version}
   Bump type: {bump_type}

   Reasoning:
   - {reasoning[0]}
   - {reasoning[1]}
   ...
   ```

3. **Confirm or Customize Version**

   ```
   AskUserQuestion:
   - Question: "Proceed with version {new_version}?"
   - Options:
     - Yes, use {new_version} (Recommended)
     - No, enter custom version
     - Cancel release
   ```

   If custom version selected, validate format (X.Y.Z) and ensure > current_version.

### Phase 2 Output

- Confirmed new version number
- Version bump rationale

---

## Phase 3: Changelog Preparation

**Objective:** Generate or update changelog entry from commits.

### Steps

1. **Invoke Changelog Update Skill**

   Use the Skill tool to invoke the `changelog-update` skill. Provide context about:
   - The project configuration from Phase 1
   - The confirmed version from Phase 2
   - Any custom message from --message argument

   The `changelog-update` skill will:
   - Generate or update changelog entry from git commits
   - Format the entry appropriately
   - Return:
     - changelog_path
     - new_entry (formatted markdown)
     - commit_message (for git commit)
     - categories (added/changed/fixed counts)

2. **Display Generated Changelog**

   Show the changelog entry to user:
   ```
   Generated changelog entry for {changelog_path}:

   {new_entry}

   Categories: {added} added, {changed} changed, {fixed} fixed
   ```

3. **Allow Editing**

   ```
   AskUserQuestion:
   - Question: "Review the changelog entry. Would you like to:"
   - Options:
     - Use as-is (Recommended)
     - Edit entry manually
     - Regenerate with different commits
   ```

   If "Edit manually", use Write tool to save draft and prompt user to edit:
   ```
   Draft saved to: /tmp/release-changelog-draft.md
   Please edit and confirm when ready.
   ```

4. **Write Changelog**

   Update the changelog file with the finalized entry using Edit tool.

### Phase 3 Output

- Updated changelog file
- Finalized commit message
- Changelog entry approved

---

## Phase 4: Documentation Updates

**Objective:** Synchronize version numbers across all relevant files.

### Steps

1. **Invoke Documentation Sync Skill**

   Use the Skill tool to invoke the `documentation-sync` skill. Provide context about:
   - The project configuration from Phase 1
   - The old version (current_version)
   - The new version (confirmed version from Phase 2)

   The `documentation-sync` skill will:
   - Update version numbers in all configured version files
   - Update version references in documentation files
   - Return:
     - files_updated (list)
     - changes (detailed diff per file)
     - warnings (missing references, etc.)
     - git_diff (full diff output)

2. **Display Changes**

   Show all file updates:
   ```
   Documentation updates:

   Files modified:
   - {file1}
   - {file2}
   - {file3}

   Git diff:
   {git_diff}
   ```

3. **Confirm Updates**

   ```
   AskUserQuestion:
   - Question: "Review the documentation changes. Proceed?"
   - Options:
     - Yes, looks good (Recommended)
     - Show full diff for each file
     - Make manual adjustments
     - Cancel release
   ```

### Phase 4 Output

- All version references updated
- Documentation synchronized
- Changes reviewed and approved

---

## Phase 5: Pre-Release Validation

**Objective:** Run comprehensive validation checks before committing.

### Steps

1. **Invoke Pre-Release Validation Skill**

   Use the Skill tool to invoke the `pre-release-validation` skill. Provide context about:
   - The project configuration from Phase 1
   - The new version (confirmed version)
   - The changelog path
   - The list of modified files from Phase 4

   The `pre-release-validation` skill will:
   - Run comprehensive validation checks before committing
   - Check for common issues (duplicate versions, malformed files, etc.)
   - Return:
     - valid (true/false)
     - errors (blocking issues)
     - warnings (non-blocking issues)
     - checks_passed / checks_total

2. **Display Validation Results**

   If errors exist:
   ```
   ❌ Validation failed ({checks_passed}/{checks_total} checks passed)

   Blocking Errors:
   - {error.message}
     Suggestion: {error.suggestion}

   Warnings:
   - {warning.message}
   ```

   If only warnings:
   ```
   ⚠️  Validation passed with warnings ({checks_passed}/{checks_total} checks passed)

   Warnings:
   - {warning.message}
     Suggestion: {warning.suggestion}
   ```

   If all checks pass:
   ```
   ✅ All validation checks passed ({checks_total}/{checks_total})
   ```

3. **Handle Validation Failures**

   If `valid: false` (blocking errors):
   ```
   AskUserQuestion:
   - Question: "Validation failed. How would you like to proceed?"
   - Options:
     - Attempt auto-fix (if available)
     - Make manual fixes and retry
     - Cancel release
   ```

4. **Handle Warnings**

   If only warnings:
   ```
   AskUserQuestion:
   - Question: "Validation passed with warnings. Continue anyway?"
   - Options:
     - Yes, proceed with release (Recommended)
     - Fix warnings first
     - Cancel
   ```

### Phase 5 Output

- All validation checks passed
- No blocking errors
- Ready for git operations

---

## Phase 6: Git Workflow Execution

**Objective:** Execute git commit, tag, and push operations.

### Steps

1. **Invoke Git Release Workflow Skill**

   Use the Skill tool to invoke the `git-release-workflow` skill. Provide context about:
   - The project configuration from Phase 1
   - The confirmed version
   - The commit message from Phase 3
   - The files to stage from Phases 3 & 4

   The `git-release-workflow` skill will:
   - Stage the modified files
   - Create a commit with proper attribution
   - Create an annotated tag for the release
   - Return:
     - commit_hash
     - tag_name
     - files_committed
     - branch
     - remote_url
     - push_command
     - success

2. **Display Commit Results**

   ```
   ✅ Release commit created successfully

   Commit: {commit_hash}
   Tag: {tag_name}
   Branch: {branch}
   Files: {files_count} files committed

   Changes:
   - {file1}
   - {file2}
   - {file3}
   ```

3. **Prompt for Push**

   ```
   AskUserQuestion:
   - Question: "Ready to push release to remote?"
   - Options:
     - Yes, push now (Recommended)
     - No, I'll push manually later
     - Show what will be pushed
   ```

4. **Execute Push** (if confirmed)

   ```bash
   git push origin {branch} --follow-tags
   ```

   Capture output and verify success.

5. **Handle Push Failures**

   If push fails:
   ```
   Push failed: {error-message}

   The release commit and tag are created locally.
   You can push manually with:
     {push_command}

   Or troubleshoot the remote connection.
   ```

### Phase 6 Output

- Commit created with proper attribution
- Annotated tag created: {scope}-v{version}
- Pushed to remote (or pending manual push)

---

## Phase 7: Post-Release Verification

**Objective:** Verify release success and provide summary.

### Steps

1. **Verify Tag on Remote** (if pushed)

   ```bash
   git ls-remote --tags origin {tag_name}
   ```

2. **Verify Version in Files**

   Read scope-specific version file and confirm it contains new version:
   ```
   Read: {version-file}
   Verify: version == {confirmed-version}
   ```

3. **Generate Release Summary**

   ```
   ═══════════════════════════════════════════════════════════
   🎉 Release v{version} completed successfully!
   ═══════════════════════════════════════════════════════════

   Release Details:
   - Project: {project_type}
   - Version: {current_version} → {confirmed-version}
   - Bump: {bump_type}
   - Commit: {commit_hash}
   - Tag: {tag_name}
   - Branch: {branch}

   Files Updated:
   - {changelog_path}
   - {version_files...}
   - {documentation_files...}

   Next Steps:
   {if-github}
   - Create GitHub release: https://github.com/{owner}/{repo}/releases/new?tag={tag_name}
   {endif}
   - Verify release on remote
   - Publish package (if applicable): {publish_command}
   - Announce release to users
   ```

4. **Offer GitHub Release Creation** (if applicable)

   If remote URL is GitHub:
   ```
   AskUserQuestion:
   - Question: "Create GitHub release page?"
   - Options:
     - Yes, open GitHub release URL
     - No, I'll create it manually
   ```

   If yes, display URL and offer to generate release notes:
   ```
   GitHub Release URL:
   https://github.com/{owner}/{repo}/releases/new?tag={tag_name}

   Suggested release notes:
   {changelog_entry}
   ```

### Phase 7 Output

- Release verified on remote
- Summary displayed
- GitHub release URL provided (if applicable)

---

## Error Handling

### General Error Recovery

For each phase, if an error occurs:
1. Display detailed error message
2. Show what was completed successfully
3. Offer recovery options:
   - Retry current phase
   - Rollback changes (if applicable)
   - Continue to next phase (if non-blocking)
   - Cancel release

### Rollback Procedures

**After Phase 6 (Commit Created):**
- If push fails, commit and tag remain local (safe)
- If user wants to undo: `git reset --soft HEAD~1 && git tag -d {tag_name}`

**After Phase 4 (Files Modified):**
- If validation fails, files can be reverted with git checkout
- Prompt user before reverting

**After Phase 3 (Changelog Updated):**
- Changelog changes can be manually reverted via Edit tool

### Common Error Scenarios

1. **Version Already Released**
   - Detected in Phase 5 (validation)
   - Offer to choose different version
   - Return to Phase 2

2. **Git Push Authentication Failure**
   - Detected in Phase 6
   - Commit and tag created successfully (local)
   - Provide manual push command
   - User can push later after fixing auth

3. **Uncommitted Changes Conflict**
   - Detected in Phase 1
   - Prompt to include, stash, or show diff
   - User decides how to proceed

4. **Invalid JSON in Version Files**
   - Detected in Phase 5 (validation)
   - Show exact parse error
   - Prompt to fix and retry

## Examples

### Example 1: Node.js Package (Auto-Detected)

```bash
# In a Node.js project with package.json
/release

# Phase 1: Detects project_type = "nodejs"
# Phase 2: Calculates v1.5.0 → v1.6.0 (minor bump from feat: commits)
# Phase 3: Generates changelog from commits
# Phase 4: Updates package.json, package-lock.json, README.md
# Phase 5: All validations pass
# Phase 6: Runs pre-release hook (npm test), commits, tags "v1.6.0", pushes
# Phase 7: Runs post-release hook (npm publish), displays success
```

### Example 2: Python Package with Explicit Patch

```bash
# In a Python project with pyproject.toml
/release patch

# Phase 1: Detects project_type = "python"
# Phase 2: v2.1.0 → v2.1.1 (explicit patch bump)
# Phase 3: Updates CHANGELOG.md
# Phase 4: Updates pyproject.toml, src/mypackage/__version__.py, README.md
# Phase 5: Validates (all checks pass)
# Phase 6: Runs pre-release hook (python -m build), commits, tags "v2.1.1", pushes
# Phase 7: Success, runs post-release hook (twine upload dist/*)
```

### Example 3: Rust Crate with Custom Message

```bash
# In a Rust project with Cargo.toml
/release --message "Security fix for CVE-2026-XXXX"

# Phase 1: Detects project_type = "rust"
# Phase 2: v0.8.5 → v0.8.6 (auto-detected patch bump)
# Phase 3: Uses custom message for changelog
# Phase 4: Updates Cargo.toml, Cargo.lock, README.md
# Phase 5: Validates (cargo check passes)
# Phase 6: Runs pre-release hook (cargo test), commits, tags "v0.8.6", pushes
# Phase 7: Success, suggests cargo publish
```

### Example 4: Go Module

```bash
# In a Go project with go.mod
/release minor

# Phase 1: Detects project_type = "go"
# Phase 2: v1.3.0 → v1.4.0 (explicit minor bump)
# Phase 3: Updates CHANGELOG.md
# Phase 4: No version files to update (Go uses git tags)
#          Updates README.md with new version
# Phase 5: Validates (go mod verify passes)
# Phase 6: Commits, tags "v1.4.0", pushes
# Phase 7: Success
```

### Example 5: Monorepo Package

```bash
# In a monorepo with multiple packages
/release --package "my-lib"

# Phase 1: Detects project_type = "monorepo", selects package "my-lib"
# Phase 2: v2.0.0 → v2.1.0 (minor bump)
# Phase 3: Updates packages/my-lib/CHANGELOG.md
# Phase 4: Updates packages/my-lib/package.json, root README.md
# Phase 5: Validates package-specific checks
# Phase 6: Commits, tags "my-lib-v2.1.0", pushes
# Phase 7: Success
```

### Example 6: Generic Project with VERSION File

```bash
# In a generic project with VERSION file
/release

# Phase 1: Detects project_type = "generic", finds VERSION file
# Phase 2: 3.2.1 → 3.3.0 (minor bump from conventional commits)
# Phase 3: Updates CHANGELOG.md
# Phase 4: Updates VERSION file, README.md
# Phase 5: Runs custom validation script
# Phase 6: Commits, tags "v3.3.0", pushes
# Phase 7: Success
```

### Example 7: Claude Code Plugin (Backward Compatible)

```bash
# In a Claude Code plugin directory
/release

# Phase 1: Detects project_type = "claude-plugin"
# Phase 2: v1.1.0 → v1.2.0 (minor bump)
# Phase 3: Updates CHANGELOG.md
# Phase 4: Updates .claude-plugin/plugin.json, README.md, marketplace.json
# Phase 5: Validates (all checks pass)
# Phase 6: Commits, tags "my-plugin-v1.2.0", pushes
# Phase 7: Success
```

## Integration with Skills

This command orchestrates 6 skills (all marked `user-invocable: false`):

1. **detect-project-type** - Phase 1 (replaces detect-release-scope)
2. **version-bump** - Phase 2 (enhanced with adapters)
3. **changelog-update** - Phase 3 (configurable formats)
4. **documentation-sync** - Phase 4 (generic file updates)
5. **pre-release-validation** - Phase 5 (project-specific checks)
6. **git-release-workflow** - Phase 6 (configurable patterns + hooks)

Phase 7 is handled directly by the command (verification and summary).

## Requirements

- Git repository with configured remote
- Conventional commit format (recommended for auto-detection)
- Appropriate git push permissions
- Project-specific requirements:
  - Node.js: `jq` for JSON manipulation
  - Python: `python` for validation
  - Rust: `cargo` (optional, for validation)
  - Go: `go` (optional, for validation)

## Configuration

Optional `.release-config.json` file for customization:
- Version files and adapters
- Changelog format and location
- Tag pattern and message templates
- Pre/post release hooks
- Custom validations
- Skip specific validation checks

See [Configuration Reference](../../docs/configuration.md) for full schema.

## Notes

- **Breaking Changes from v1.x**: Scope argument removed, project type auto-detected
- All git operations follow safe practices (no force push unless explicit)
- Linear git history maintained (direct commits, no merge commits)
- Co-Authored-By attribution included in all commits
- Annotated tags used for rich metadata
- User confirmation required at critical decision points
- Backward compatible with Claude Code plugins
