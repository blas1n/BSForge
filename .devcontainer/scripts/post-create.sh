#!/bin/bash
set -e

echo "BSForge DevContainer Post-Create Setup"
echo "======================================"

# 1. Install uv (fast Python package installer)
echo "Installing uv..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
    echo "[OK] uv installed successfully"
else
    echo "[OK] uv already installed"
fi

# 2. Ensure uv is in PATH for current session
export PATH="$HOME/.cargo/bin:$PATH"

# 3. Install Python dependencies
echo ""
echo "Installing Python dependencies..."
if [ -f "pyproject.toml" ]; then
    uv pip install -e ".[dev]"
    echo "[OK] Dependencies installed successfully"
else
    echo "[SKIP] pyproject.toml not found - will be created in Phase 1"
fi

# 4. Set up pre-commit hooks (if available)
echo ""
echo "Setting up pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    echo "[OK] Pre-commit hooks installed"
else
    echo "[SKIP] pre-commit not found - will be installed with dev dependencies"
fi

# 5. Make sure scripts are executable
chmod +x .devcontainer/scripts/*.sh 2>/dev/null || true

echo ""
echo "======================================"
echo "[DONE] DevContainer setup complete!"
echo "======================================"
echo ""
echo "Available services:"
echo "  - PostgreSQL 16: localhost:5432"
echo "  - Redis 7:       localhost:6379"
echo "  - FFmpeg:        pre-installed"
echo ""
echo "Quick start:"
echo "  make dev     # Start FastAPI server"
echo "  make worker  # Start Celery worker"
echo "  make test    # Run tests"
echo ""
