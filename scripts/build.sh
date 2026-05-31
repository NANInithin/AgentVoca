#!/usr/bin/env bash
# Build the AgentVoca standalone executable using PyInstaller.
#
# Usage:
#   bash scripts/build.sh [--clean]
#
# Options:
#   --clean   Remove dist/ and build/ before building.
#
# Output:
#   macOS:   dist/AgentVoca.app
#   Windows: dist/AgentVoca.exe  (run under Git Bash or WSL)
#   Linux:   dist/AgentVoca

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

# ── Parse arguments ──────────────────────────────────────────────────────────
CLEAN=false
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

# ── Clean previous build artifacts ───────────────────────────────────────────
if [ "$CLEAN" = true ]; then
  echo "Cleaning dist/ and build/..."
  rm -rf dist/ build/
fi

# ── Check PyInstaller is available ───────────────────────────────────────────
if ! uv run python -c "import PyInstaller" 2>/dev/null; then
  echo "PyInstaller not found. Adding to dev dependencies..."
  uv add --dev pyinstaller
fi

# ── Detect platform ──────────────────────────────────────────────────────────
PLATFORM="$(uname -s)"
case "$PLATFORM" in
  Darwin)  PLATFORM_NAME="macos"   ;;
  Linux)   PLATFORM_NAME="linux"   ;;
  MINGW*|MSYS*|CYGWIN*)
           PLATFORM_NAME="windows" ;;
  *)       PLATFORM_NAME="unknown" ;;
esac

VERSION="$(uv run python -c "
from importlib.metadata import version
try:
    print(version('agentvoca'))
except Exception:
    print('0.1.0-dev')
")"

echo "Building AgentVoca $VERSION for $PLATFORM_NAME..."

# ── Run PyInstaller ──────────────────────────────────────────────────────────
uv run pyinstaller AgentVoca.spec --noconfirm

# ── Report output ────────────────────────────────────────────────────────────
echo ""
echo "Build complete."
if [ "$PLATFORM_NAME" = "macos" ]; then
  echo "  Output: dist/AgentVoca.app"
elif [ "$PLATFORM_NAME" = "windows" ]; then
  echo "  Output: dist/AgentVoca.exe"
else
  echo "  Output: dist/AgentVoca"
fi
echo ""
echo "To test the build, run the executable directly."
echo "On macOS, grant Accessibility and Microphone permissions to dist/AgentVoca.app."
