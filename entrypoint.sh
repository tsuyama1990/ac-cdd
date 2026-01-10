#!/bin/bash
set -e

# Add /app to safe.directory to allow git operations regardless of owner
git config --system --add safe.directory /app

# Setup Git credential helper using GITHUB_TOKEN if available
if [ -n "$GITHUB_TOKEN" ]; then
    # Configure git to use the token for HTTPS authentication
    git config --system credential.helper store
    echo "https://oauth2:${GITHUB_TOKEN}@github.com" > /root/.git-credentials
    chmod 600 /root/.git-credentials
    
    # Also set it as GH_TOKEN for gh CLI compatibility
    export GH_TOKEN="$GITHUB_TOKEN"
fi

# Setup Git user identity (required for commits)
# Use environment variables if provided, otherwise use defaults
git config --system user.name "${GIT_AUTHOR_NAME:-AC-CDD Agent}"
git config --system user.email "${GIT_AUTHOR_EMAIL:-ac-cdd-agent@localhost}"

# entrypoint.sh - Handle user permissions and execute command

# Note: For simplicity and to avoid Git credential issues, we run as root.
# Files created in /app (mounted volume) will have host permissions preserved.

# Run as root (or current user if -u flag is used with docker run)
exec "$@"
