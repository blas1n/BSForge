FROM python:3.11-slim

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install basic development tools and iptables/ipset
RUN apt-get update && apt-get install -y --no-install-recommends \
    less \
    git \
    procps \
    sudo \
    fzf \
    curl \
    zsh \
    man-db \
    unzip \
    gnupg2 \
    gh \
    iptables \
    ipset \
    iproute2 \
    dnsutils \
    aggregate \
    jq \
    vim \
    nodejs \
    npm \
    postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG USERNAME=vscode
ARG GROUPNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd -g $USER_GID $USERNAME \
    && useradd -m -u $USER_UID -g $USER_GID -d /home/$USERNAME -s /bin/bash $USERNAME

# Persist bash history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R $USER_UID:$USER_GID /commandhistory \
    && echo $SNIPPET >> /home/$USERNAME/.bashrc

# Set up npm global directory
RUN mkdir -p /usr/local/share/npm-global && \
    chown -R $USER_UID:$USER_GID /usr/local/share
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Create workspace and config directories
RUN mkdir -p /workspace /home/$USERNAME/.claude && \
    chown -R $USER_UID:$USER_GID /workspace /home/$USERNAME/.claude

# Set up non-root user
USER $USERNAME

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Install homebrew (for dotfiles)
RUN mkdir -p $HOME/.linuxbrew \
    && git clone https://github.com/Homebrew/brew $HOME/.linuxbrew/Homebrew \
    && mkdir -p $HOME/.linuxbrew/bin \
    && ln -s $HOME/.linuxbrew/Homebrew/bin/brew $HOME/.linuxbrew/bin/brew \
    && eval "$($HOME/.linuxbrew/bin/brew shellenv)"

ENV PATH=/home/$USERNAME/.linuxbrew/bin:/home/$USERNAME/.linuxbrew/sbin:$PATH

RUN brew install openssl@3 --force-bottle
RUN brew install git-delta --force-bottle

# Copy and set up firewall script (for Claude Code)
COPY scripts/init-firewall.sh /usr/local/bin/
USER root
RUN chmod +x /usr/local/bin/init-firewall.sh && \
    echo "$USERNAME ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/firewall && \
    chmod 0440 /etc/sudoers.d/firewall

USER $USERNAME
