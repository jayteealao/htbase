---
description: Orchestrate OtterStack deployment with preparation, setup, and debugging
argument-hint: [project-name]
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - Skill
---

# Deploy OtterStack Command

This command orchestrates a complete OtterStack deployment workflow by combining three skills:
- **prepare-otterstack-deployment** - Validates Docker Compose compatibility and scans for issues
- **otterstack-usage** - Provides OtterStack command reference and setup guidance
- **debug-vps-deployment** - Iteratively debugs VPS deployment failures

## Usage

```bash
/deploy-otterstack [project-name]
```

## Arguments

- `project-name` (optional): Name of the project to deploy. If not provided, auto-detects from current directory.

## Workflow

This command follows a 7-phase semi-automated workflow:

1. **Initialization** - Detect project name and validate docker-compose.yml
2. **Preparation** - Run compatibility checks and scan for issues
3. **Target Selection** - Choose local or VPS deployment
4. **Setup** - Configure project and environment variables
5. **Deployment** - Execute deployment with monitoring
6. **Debug Loop** - Automatically fix issues if deployment fails (max 6 attempts)
7. **Verification** - Confirm containers are healthy and endpoints work

## Implementation

When invoked, this command performs the following steps:

### Phase 1: Initialization

First, detect the project name and validate the environment:

```markdown
If the user provided a project name via arguments, use it. Otherwise, check if docker-compose.yml exists in the current directory and use the directory name as the project name.

Validate that docker-compose.yml exists. If not, display an error:
"Error: docker-compose.yml not found. Please run this command from a Docker Compose project directory."

Set the repository path to the current working directory.
```

### Phase 2: Preparation

Invoke the **prepare-otterstack-deployment** skill to analyze the project:

```markdown
Invoke the prepare-otterstack-deployment skill on the current directory.

The skill will:
- Scan for environment variables in the compose file, Dockerfile, and application code
- Detect Docker networks and identify the default network
- Detect Traefik-exposed services and required configuration
- Check 6 critical OtterStack requirements:
  1. No hardcoded container names
  2. Uses environment: section (not env_file:)
  3. No static Traefik priority labels
  4. Health checks defined
  5. Docker Compose syntax validation
  6. Network configuration (explicit or default)
- Detect common failure patterns:
  1. Native module bindings (Node.js)
  2. Database path permissions
  3. Migration file paths
  4. IPv6/IPv4 health check conflicts
  5. Missing build context
  6. Missing network definition

After the skill completes:
1. Review the readiness report for blocking issues
2. Parse the "Networks Detected" section:
   - Extract the default network name
   - Store detected networks list
   - Note services attached to each network
3. Parse the "Traefik Exposure" section:
   - Extract list of exposed services (if any)
   - For each exposed service, note:
     - Service name
     - Router name
     - Port number
     - Required domain variable name (e.g., API_DOMAIN)
   - Check if CROWDSEC_API_KEY is required
```

Present the results to the user with an interactive prompt:

```markdown
Use AskUserQuestion to prompt the user:

Question: "Found [X] blocking issues that must be fixed before deployment. How would you like to proceed?"
Header: "Next Step"
Options:
  1. "Review detailed fixes" - Show the full readiness report with fix instructions
  2. "Continue anyway" - Proceed to deployment (only if no critical blocking issues)
  3. "Cancel deployment" - Exit the command

If the user selects "Review detailed fixes":
- Display the full readiness report from prepare-otterstack-deployment
- Show all blocking issues with file locations and fix instructions
- Ask again: "Apply fixes manually, then type 'ready' to continue, or 'cancel' to abort."

If the user selects "Cancel deployment":
- Exit gracefully with message: "Deployment cancelled. Fix the issues listed above and try again."
```

### Phase 3: Target Selection

Ask the user where to deploy:

```markdown
Use AskUserQuestion to prompt:

Question: "Where would you like to deploy this project?"
Header: "Target"
Options:
  1. "Local OtterStack" - Deploy using local otterstack command
  2. "VPS (194.163.189.144)" - Deploy to remote VPS via SSH
  3. "Cancel" - Abort deployment

Store the user's choice in a variable.

If "VPS" was selected:
- Test SSH connectivity:
  ```bash
  ssh -o ConnectTimeout=5 archivist@194.163.189.144 "echo 'SSH OK'"
  ```
- If SSH fails, display error: "Cannot connect to VPS at 194.163.189.144. Please check SSH configuration."
- Set command prefix: SSH_PREFIX="ssh archivist@194.163.189.144" and OTTERSTACK_CMD="~/OtterStack/otterstack"

If "Local" was selected:
- Verify otterstack is installed:
  ```bash
  which otterstack || command -v otterstack
  ```
- If not found, display error: "OtterStack not found. Please install it first."
- Set command prefix: SSH_PREFIX="" and OTTERSTACK_CMD="otterstack"
```

**Traefik Exposure Configuration** (if exposed services detected in Phase 2):

```markdown
If the "Traefik Exposure" section from Phase 2 contains exposed services:

For each exposed service:
  Use AskUserQuestion to prompt:

  Question: "What domain should the ${SERVICE_NAME} service use?"
  Header: "Domain for ${SERVICE_NAME}"
  Options: (text input)

  Validate the input:
  - Must be a valid domain format (e.g., api.example.com)
  - Must not include protocol (http:// or https://)
  - Must not be empty

  Store domain in: ${SERVICE_NAME}_DOMAIN variable
  Example: For "api" service, store in API_DOMAIN

After collecting all domains, prompt for CrowdSec:

Use AskUserQuestion to prompt:

Question: "Enter your CrowdSec API key for the bouncer"
Header: "Security"
Options: (text input with password masking if possible)

Note: "CrowdSec provides DDoS protection and bot blocking for your exposed services. Get your API key from CrowdSec dashboard → Bouncers → Add bouncer"

Validate the input:
- Must not be empty
- Store in: CROWDSEC_API_KEY variable

Display summary:
```
Traefik Configuration Summary:
- Exposed services: ${EXPOSED_SERVICE_COUNT}
${for each service}
  - ${SERVICE_NAME}: ${DOMAIN}
${end for}
- CrowdSec protection: Enabled
- TLS/HTTPS: Enabled (Let's Encrypt)
```
```

### Phase 4: Setup

Configure the OtterStack project and environment variables:

```markdown
Check if the project already exists in OtterStack:

```bash
${SSH_PREFIX} ${OTTERSTACK_CMD} project list | grep -q "^${PROJECT_NAME}$"
```

If the project does NOT exist:
- Display: "Project ${PROJECT_NAME} not found. Adding to OtterStack..."
- For VPS deployments:
  - Check if the current directory is a git repository
  - Get the remote URL: `git config --get remote.origin.url`
  - If no remote, prompt user: "Enter git repository URL for VPS deployment:"
  - Add project: `${SSH_PREFIX} ${OTTERSTACK_CMD} project add ${PROJECT_NAME} ${REPO_URL} --traefik-routing`
- For local deployments:
  - Add project using local path: `${OTTERSTACK_CMD} project add ${PROJECT_NAME} ${REPO_PATH} --traefik-routing`

Configure environment variables:
- Check if .env.${PROJECT_NAME} file exists in current directory
- If it exists:
  - Display: "Found .env.${PROJECT_NAME} file. Loading environment variables..."
  - For VPS: Copy file to VPS and load:
    ```bash
    scp .env.${PROJECT_NAME} archivist@194.163.189.144:/tmp/
    ssh archivist@194.163.189.144 "${OTTERSTACK_CMD} env load ${PROJECT_NAME} /tmp/.env.${PROJECT_NAME}"
    ```
  - For local: Load directly:
    ```bash
    ${OTTERSTACK_CMD} env load ${PROJECT_NAME} .env.${PROJECT_NAME}
    ```
- If .env file doesn't exist:
  - Display: "No .env file found. Starting interactive environment variable scan..."
  - Run: `${SSH_PREFIX} ${OTTERSTACK_CMD} env scan ${PROJECT_NAME}`
  - This will interactively prompt for missing variables

Add network configuration:
- Set the NETWORK_NAME variable using the default network detected in Phase 2:
  ```bash
  ${SSH_PREFIX} ${OTTERSTACK_CMD} env set ${PROJECT_NAME} NETWORK_NAME="${DEFAULT_NETWORK}"
  ```
- Display: "Network configured: ${DEFAULT_NETWORK}"

Add domain variables (if Traefik exposure was configured in Phase 3):
- For each exposed service, set the domain variable collected in Phase 3:
  ```bash
  ${SSH_PREFIX} ${OTTERSTACK_CMD} env set ${PROJECT_NAME} API_DOMAIN="${API_DOMAIN}"
  ${SSH_PREFIX} ${OTTERSTACK_CMD} env set ${PROJECT_NAME} WEB_DOMAIN="${WEB_DOMAIN}"
  # ... repeat for each service
  ```
- Set the CrowdSec API key:
  ```bash
  ${SSH_PREFIX} ${OTTERSTACK_CMD} env set ${PROJECT_NAME} CROWDSEC_API_KEY="${CROWDSEC_API_KEY}"
  ```
- Display: "Traefik domains and security configured"

List configured environment variables:
```bash
${SSH_PREFIX} ${OTTERSTACK_CMD} env list ${PROJECT_NAME}
```

Display the list to the user and use AskUserQuestion:

Question: "Environment variables configured. Ready to deploy?"
Header: "Confirm"
Options:
  1. "Deploy now (Recommended)" - Proceed to deployment
  2. "Edit variables first" - Open env set command for editing
  3. "Cancel" - Abort deployment

If "Edit variables first":
- Display: "Use this command to edit variables: ${SSH_PREFIX} ${OTTERSTACK_CMD} env set ${PROJECT_NAME} KEY=VALUE"
- Prompt: "Type 'ready' when done, or 'cancel' to abort."
```

### Phase 4.5: Traefik Label Preparation

Generate and apply comprehensive Traefik labels for exposed services (only if services were marked for exposure in Phase 3):

```markdown
If Traefik exposure was configured in Phase 3:

Display: "Preparing Traefik labels with CrowdSec security..."

For each exposed service, generate labels using this template:
```yaml
labels:
  - "traefik.enable=true"
  # Routing
  - "traefik.http.routers.{router-name}.rule=Host(\`\${SERVICE_DOMAIN}\`)"
  - "traefik.http.routers.{router-name}.entrypoints=web,websecure"
  # TLS with Let's Encrypt
  - "traefik.http.routers.{router-name}.tls=true"
  - "traefik.http.routers.{router-name}.tls.certresolver=myresolver"
  # Load balancer
  - "traefik.http.services.{router-name}.loadbalancer.server.port={PORT}"
  # CrowdSec middleware for DDoS protection
  - "traefik.http.routers.{router-name}.middlewares=crowdsec-{router-name}@docker"
  - "traefik.http.middlewares.crowdsec-{router-name}.plugin.crowdsec-bouncer.enabled=true"
  - "traefik.http.middlewares.crowdsec-{router-name}.plugin.crowdsec-bouncer.crowdseclapikey=\${CROWDSEC_API_KEY}"
```

Replace {router-name}, {SERVICE_DOMAIN}, and {PORT} with actual values from Phase 2 and Phase 3.

Example for API service:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.aperture-api.rule=Host(\`\${API_DOMAIN}\`)"
  - "traefik.http.routers.aperture-api.entrypoints=web,websecure"
  - "traefik.http.routers.aperture-api.tls=true"
  - "traefik.http.routers.aperture-api.tls.certresolver=myresolver"
  - "traefik.http.services.aperture-api.loadbalancer.server.port=8080"
  - "traefik.http.routers.aperture-api.middlewares=crowdsec-aperture-api@docker"
  - "traefik.http.middlewares.crowdsec-aperture-api.plugin.crowdsec-bouncer.enabled=true"
  - "traefik.http.middlewares.crowdsec-aperture-api.plugin.crowdsec-bouncer.crowdseclapikey=\${CROWDSEC_API_KEY}"
```

Display the generated labels to the user:
```
Generated Traefik Labels:
========================

Service: api
Router: aperture-api
Domain: ${API_DOMAIN}
Port: 8080
Security: CrowdSec enabled

[Show complete label configuration above]
```

Use AskUserQuestion to confirm:

Question: "Review the generated Traefik labels. These will be applied to your docker-compose.yml. Proceed?"
Header: "Labels"
Options:
  1. "Apply labels (Recommended)" - Update compose file with generated labels
  2. "Show full configuration" - Display complete docker-compose.yml section
  3. "Skip (use existing)" - Continue with existing labels in compose file
  4. "Cancel deployment" - Abort

If "Apply labels" selected:
  - Use the Edit tool to update docker-compose.yml
  - Add the generated labels to each exposed service's labels section
  - Preserve existing labels that don't conflict
  - Ensure service has `networks: - ${NETWORK_NAME}` configuration
  - Display: "Updated docker-compose.yml with Traefik labels"

If "Show full configuration" selected:
  - Display the complete service section from docker-compose.yml with new labels
  - Ask again: "Apply these labels?"

If "Skip" selected:
  - Display warning: "Using existing labels. Ensure they include CrowdSec middleware and correct domain variables."
  - Continue to deployment

Note: The updated docker-compose.yml will be committed after successful deployment in Phase 7.
```

### Phase 5: Deployment

Execute the deployment with verbose monitoring:

```markdown
Display: "Starting deployment to ${DEPLOYMENT_TARGET}..."
Display progress indicator: "Phase 5/7: Deploying..."

Run deployment command:
```bash
${SSH_PREFIX} ${OTTERSTACK_CMD} deploy ${PROJECT_NAME} -v
```

Capture both stdout and stderr.

Monitor the output for these deployment stages:
1. "Fetching latest changes..." (for remote repos)
2. "Validating compose file..."
3. "Pulling images..."
4. "Starting services..."
5. "Waiting for containers to be healthy..."
6. "Applying Traefik priority labels..." (if Traefik enabled)
7. "Deployment successful!"

If the deployment command exits with code 0:
- Display: "✅ Deployment successful!"
- Proceed to Phase 7: Verification

If the deployment command exits with non-zero code:
- Capture the error output
- Parse the error to determine which stage failed:
  - If error contains "compose validation failed" → stage = "validation"
  - If error contains "failed to start services" → stage = "startup"
  - If error contains "health check failed" or "unhealthy" → stage = "health_check"
  - If error contains "deployment in progress" → stage = "lock_conflict"
  - If error contains "Traefik" or "routing" → stage = "traefik"
  - Otherwise → stage = "unknown"
- Display: "❌ Deployment failed at stage: ${stage}"
- Proceed to Phase 6: Debug Loop
```

### Phase 6: Debug Loop

Automatically diagnose and fix deployment failures:

```markdown
Initialize debug loop:
- Set ATTEMPT_COUNT = 0
- Set MAX_ATTEMPTS = 6

While ATTEMPT_COUNT < MAX_ATTEMPTS:
  Increment ATTEMPT_COUNT
  Display: "Debug iteration ${ATTEMPT_COUNT}/${MAX_ATTEMPTS}..."

  If DEPLOYMENT_TARGET is "VPS":
    Invoke the **debug-vps-deployment** skill with context:
    - Provide ERROR_MESSAGE from deployment output
    - Provide DEPLOYMENT_STAGE that failed
    - Provide PROJECT_NAME
    - Provide ATTEMPT_NUMBER = ATTEMPT_COUNT

    The debug-vps-deployment skill will:
    - Use the failure diagnosis decision tree to identify the root cause
    - Determine the appropriate fix based on the failure type:
      * Validation failures → Fix env vars or compose file
      * Startup failures → Fix code, Dockerfile, or permissions
      * Health check failures → Fix health check endpoint or timing
      * Lock conflicts → Remove stale lock file
      * Traefik issues → Fix labels or network configuration
    - Apply the fix (either automatically or guide user)
    - Return whether a fix was applied and if retry is recommended

  Else (local deployment):
    Display the error output
    Analyze the error manually:
    - For validation errors: Check env vars and compose syntax
    - For startup errors: Check container logs
    - For health check errors: Test health endpoint manually

    Use AskUserQuestion to prompt:
    Question: "Deployment failed: ${ERROR_SUMMARY}. What would you like to do?"
    Header: "Fix"
    Options:
      1. "I fixed it, retry deployment" - Retry the deployment
      2. "Show detailed error" - Display full error output
      3. "Abort deployment" - Exit debug loop

  After fix is applied:
    Display: "Fix applied. Retrying deployment..."

    Retry deployment:
    ```bash
    ${SSH_PREFIX} ${OTTERSTACK_CMD} deploy ${PROJECT_NAME} -v
    ```

    If retry exits with code 0:
      Display: "✅ Deployment successful after ${ATTEMPT_COUNT} attempts!"
      Break out of debug loop
      Proceed to Phase 7: Verification

    Else:
      Capture new error output
      Parse new deployment stage
      Display: "Deployment still failing. Analyzing..."
      Continue loop

If MAX_ATTEMPTS reached without success:
  Use AskUserQuestion:
  Question: "Maximum retry attempts (${MAX_ATTEMPTS}) reached. Deployment is still failing."
  Header: "Continue?"
  Options:
    1. "Continue debugging (6 more attempts)" - Increase MAX_ATTEMPTS by 6 and continue loop
    2. "Manual intervention" - Display full error and exit
    3. "Rollback to previous version" - Trigger rollback procedure

  If "Rollback" selected:
    Get previous deployment SHA:
    ```bash
    PREVIOUS_SHA=$(${SSH_PREFIX} ${OTTERSTACK_CMD} deployments ${PROJECT_NAME} | tail -2 | head -1 | awk '{print $2}')
    ```

    Deploy previous version:
    ```bash
    ${SSH_PREFIX} ${OTTERSTACK_CMD} deploy ${PROJECT_NAME} --ref ${PREVIOUS_SHA} -v
    ```

    Display: "Rolled back to previous version: ${PREVIOUS_SHA}"
```

### Phase 7: Verification

Verify the deployment was successful:

```markdown
Display: "Verifying deployment..."
Display progress: "Phase 7/7: Verification..."

1. Check deployment status:
```bash
${SSH_PREFIX} ${OTTERSTACK_CMD} status ${PROJECT_NAME}
```

Parse the output:
- Extract Status (should be "active")
- Extract Commit SHA
- Extract Started timestamp

If status is not "active":
  Display warning: "⚠️  Warning: Deployment status is not 'active'"

2. Check container health:
```bash
if [ "${DEPLOYMENT_TARGET}" == "vps" ]; then
  ssh archivist@194.163.189.144 "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep ${PROJECT_NAME}"
else
  docker ps --format 'table {{.Names}}\t{{.Status}}' | grep ${PROJECT_NAME}
fi
```

Parse the output to count healthy containers:
- Count lines with "(healthy)" status
- Count total containers

If not all containers are healthy:
  Display warning: "⚠️  Warning: Not all containers are reporting healthy status"
  Display container status table

3. Generate success report:

Display:
```
========================================
🎉 DEPLOYMENT SUCCESSFUL
========================================

Project: ${PROJECT_NAME}
Target: ${DEPLOYMENT_TARGET}
Commit: ${COMMIT_SHA}
Deployment Attempts: ${ATTEMPT_COUNT}

Containers: ${HEALTHY_COUNT}/${TOTAL_COUNT} healthy

Next Steps:
• Monitor logs: ${SSH_PREFIX} docker logs <container-name>
• Check status: ${OTTERSTACK_CMD} status ${PROJECT_NAME}
• View history: ${OTTERSTACK_CMD} deployments ${PROJECT_NAME}

========================================
```

If any warnings were encountered:
  Display: "⚠️  Deployment completed with warnings. Please review container health and logs."
```

## Error Handling

The command handles errors in these categories:

1. **User Cancellation** - Exits gracefully at any prompt point
2. **Missing Prerequisites** - docker-compose.yml, OtterStack, SSH access
3. **Validation Failures** - Compose file issues, missing env vars
4. **Deployment Failures** - Container startup, health checks, Traefik routing
5. **Debug Loop Exhaustion** - Max retries reached, offers rollback

## Examples

### Deploy current directory to local OtterStack

```bash
cd /path/to/my-project
/deploy-otterstack
# Choose: Local OtterStack
# Confirm environment variables
# Wait for deployment to complete
```

### Deploy specific project to VPS

```bash
cd /path/to/my-api
/deploy-otterstack my-api
# Choose: VPS (194.163.189.144)
# Provide git repository URL if needed
# Monitor deployment progress
# Auto-debug any failures
```

### Deploy with environment file

```bash
# Create .env file first
echo "DATABASE_URL=postgres://localhost/mydb" > .env.my-project
echo "API_KEY=secret123" >> .env.my-project

cd /path/to/my-project
/deploy-otterstack my-project
# Choose deployment target
# Environment variables auto-loaded from .env.my-project
```

## Related Skills

- **prepare-otterstack-deployment** - Used in Phase 2 to validate project readiness
- **otterstack-usage** - Referenced for OtterStack command syntax and usage
- **debug-vps-deployment** - Used in Phase 6 for VPS deployment debugging

## Requirements

- Docker Compose project with `docker-compose.yml` in the current directory
- OtterStack installed (local deployments) or SSH access to VPS (VPS deployments)
- For VPS deployments: Git repository with remote URL
- For zero-downtime deployments: Traefik running and compose file has Traefik labels

## Tips

- Run `/deploy-otterstack` from your project directory for auto-detection
- Create `.env.<project-name>` files for automatic environment variable loading
- Fix blocking issues from the preparation phase before deploying
- Use the debug loop to automatically resolve common deployment failures
- Monitor the deployment output to understand which stage is executing
- The command supports up to 6 automatic retry attempts for failed deployments
