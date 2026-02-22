FROM python:3.12-slim

# Install system dependencies
# git and gh (GitHub CLI) are required
RUN apt-get update && apt-get install -y \
    git \
    curl \
    gnupg \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh gosu \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory for the tool installation
# We install the tool into /opt/ac_cdd/ac_cdd_core
WORKDIR /opt/ac_cdd/ac_cdd_core

# Copy project files for the tool
COPY pyproject.toml .
COPY README.md .
COPY dev_src/ ./dev_src/

# Install the tool and its dependencies into the system python environment
RUN uv pip install --system .

# Copy system prompts to internal template directory
RUN mkdir -p /opt/ac_cdd/templates
COPY dev_src/ac_cdd_core/templates/*.md /opt/ac_cdd/templates/

# Create /app for user mount
WORKDIR /app

# Copy entrypoint
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV AC_CDD_TEMPLATE_PATH=/opt/ac_cdd/templates
# AC_CDD_CONFIG_PATH is no longer needed

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["ac-cdd"]
