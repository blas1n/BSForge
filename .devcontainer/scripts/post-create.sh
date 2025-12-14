#!/bin/bash
set -e

echo "BSForge DevContainer Post-Create Setup"
echo "======================================"

# 1. Install uv (fast Python package installer)
echo "Installing uv..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH immediately
    export PATH="$HOME/.local/bin:$PATH"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    echo "[OK] uv installed successfully"
else
    echo "[OK] uv already installed"
fi

# 2. Ensure uv is in PATH for current session
export PATH="$HOME/.local/bin:$PATH"

# 3. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    uv venv .venv
    echo "[OK] Virtual environment created"
fi

# 4. Activate virtual environment
source .venv/bin/activate

# 5. Install Python dependencies
echo ""
echo "Installing Python dependencies..."
if [ -f "pyproject.toml" ]; then
    uv pip install -e ".[dev]"
    echo "[OK] Dependencies installed successfully"

    # 6. Set up pre-commit hooks (after dependencies are installed)
    echo ""
    echo "Setting up pre-commit hooks..."
    if [ -f ".pre-commit-config.yaml" ]; then
        pre-commit install
        echo "[OK] Pre-commit hooks installed"
    else
        echo "[SKIP] .pre-commit-config.yaml not found"
    fi
else
    echo "[SKIP] pyproject.toml not found - will be created in Phase 1"
fi

# 7. Make sure scripts are executable
chmod +x .devcontainer/scripts/*.sh 2>/dev/null || true

# 8. Add venv activation to bashrc
if ! grep -q "source /workspace/.venv/bin/activate" ~/.bashrc; then
    echo 'source /workspace/.venv/bin/activate' >> ~/.bashrc
    echo "[OK] Auto-activation added to bashrc"
fi

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
