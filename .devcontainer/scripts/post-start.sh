#!/bin/bash
# post-start.sh - Runs every time the container starts

set -e

echo "🔄 BSForge Dev Container - postStart"
echo "=================================="

# Verify services are healthy
echo "🏥 Health checks..."

# Check PostgreSQL
if pg_isready -h postgres -U postgres -d bsforge > /dev/null 2>&1; then
  echo "  ✅ PostgreSQL: healthy"
else
  echo "  ❌ PostgreSQL: unhealthy"
fi

# Check Redis
if redis-cli -h redis ping > /dev/null 2>&1; then
  echo "  ✅ Redis: healthy"
else
  echo "  ❌ Redis: unhealthy"
fi

# Initialize firewall (for Claude Code)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
  echo "🔒 Initializing firewall..."
  sudo /usr/local/bin/init-firewall.sh || echo "⚠️  Firewall initialization failed (non-critical)"
fi

echo ""
echo "✅ Container ready for development"
echo "=================================="