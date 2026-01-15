#!/bin/bash
set -e

# Get host UID and GID or default to 1000
HOST_UID=${HOST_UID:-1000}
HOST_GID=${HOST_GID:-1000}

# Create group if it doesn't exist
if ! getent group "$HOST_GID" > /dev/null 2>&1; then
    groupadd -g "$HOST_GID" appgroup
fi
TARGET_GID="$HOST_GID"

# Create user if it doesn't exist
if ! id -u "$HOST_UID" > /dev/null 2>&1; then
    useradd -u "$HOST_UID" -g "$HOST_GID" -m -s /bin/bash appuser
    TARGET_USER="appuser"
else
    TARGET_USER=$(id -nu "$HOST_UID")
fi

# Add /app to safe.directory
git config --system --add safe.directory /app

# Handle SSH keys
USER_HOME=$(eval echo "~$TARGET_USER")
if [ -d "/root/.ssh" ]; then
    mkdir -p "$USER_HOME/.ssh"
    # Copy files
    cp -r /root/.ssh/* "$USER_HOME/.ssh/" 2>/dev/null || true
    chown -R "$TARGET_USER:$HOST_GID" "$USER_HOME/.ssh"
    chmod 700 "$USER_HOME/.ssh"
    chmod 600 "$USER_HOME/.ssh"/* 2>/dev/null || true
fi

# Setup Git credential helper
if [ -n "$GITHUB_TOKEN" ]; then
    # Use store helper system-wide, but put credentials in user's home
    git config --system credential.helper store
    echo "https://oauth2:${GITHUB_TOKEN}@github.com" > "$USER_HOME/.git-credentials"
    chown "$TARGET_USER:$HOST_GID" "$USER_HOME/.git-credentials"
    chmod 600 "$USER_HOME/.git-credentials"
fi

# Identity
git config --system user.name "${GIT_AUTHOR_NAME:-AC-CDD Agent}"
git config --system user.email "${GIT_AUTHOR_EMAIL:-ac-cdd-agent@localhost}"

# Execute command as the target user
exec gosu "$TARGET_USER" "$@"
