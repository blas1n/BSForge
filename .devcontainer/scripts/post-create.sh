#!/bin/bash
set -e

echo "BSForge DevContainer Post-Create Setup"
echo "======================================"

# 0. Configure git safe directory (required for devcontainer)
echo "Configuring git safe directory..."
git config --global --add safe.directory /workspace
echo "[OK] Git safe directory configured"

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
    # Use copy mode to avoid hardlink warnings (host volume vs container filesystem)
    UV_LINK_MODE=copy uv pip install -e ".[dev]"
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

# 7. Install Korean fonts for video subtitle rendering
echo ""
echo "Installing Korean fonts (Noto Sans CJK KR)..."
FONT_DIR="$HOME/.local/share/fonts"
mkdir -p "$FONT_DIR"

# Download Noto Sans CJK KR fonts if not already installed
if [ ! -f "$FONT_DIR/NotoSansCJKkr-Bold.otf" ]; then
    echo "Downloading Noto Sans CJK KR Bold..."
    curl -fsSL -o "$FONT_DIR/NotoSansCJKkr-Bold.otf" \
        "https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf" || \
        echo "[WARN] Failed to download NotoSansCJKkr-Bold.otf"
fi

if [ ! -f "$FONT_DIR/NotoSansCJKkr-Regular.otf" ]; then
    echo "Downloading Noto Sans CJK KR Regular..."
    curl -fsSL -o "$FONT_DIR/NotoSansCJKkr-Regular.otf" \
        "https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf" || \
        echo "[WARN] Failed to download NotoSansCJKkr-Regular.otf"
fi

# Refresh font cache
if command -v fc-cache &> /dev/null; then
    fc-cache -fv "$FONT_DIR" > /dev/null 2>&1
    echo "[OK] Korean fonts installed and cache updated"
else
    echo "[WARN] fc-cache not available, fonts may not be recognized"
fi

# 8. Make sure scripts are executable
chmod +x .devcontainer/scripts/*.sh 2>/dev/null || true

# 9. Add venv activation to bashrc
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
