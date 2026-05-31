#!/usr/bin/env bash
# Cut a new AgentVoca release.
#
# Usage:
#   bash scripts/release.sh <version>
#
# Example:
#   bash scripts/release.sh 0.2.0
#
# This script:
#   1. Validates the working tree is clean.
#   2. Bumps the version in pyproject.toml.
#   3. Commits the version bump.
#   4. Creates an annotated git tag.
#   5. Builds the platform executable.
#   6. Prints instructions for pushing and creating a GitHub release.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

# ── Validate arguments ───────────────────────────────────────────────────────
if [ $# -ne 1 ]; then
  echo "Usage: bash scripts/release.sh <version>" >&2
  echo "Example: bash scripts/release.sh 0.2.0" >&2
  exit 1
fi

VERSION="$1"

# Basic semver validation
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Error: version must be in MAJOR.MINOR.PATCH format (e.g. 0.2.0)" >&2
  exit 1
fi

# ── Require clean working tree ───────────────────────────────────────────────
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: working tree is not clean. Commit or stash changes before releasing." >&2
  git status --short
  exit 1
fi

# ── Confirm ──────────────────────────────────────────────────────────────────
echo "Releasing AgentVoca v$VERSION"
echo ""
read -r -p "Continue? [y/N] " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "Aborted."
  exit 0
fi

# ── Bump version in pyproject.toml ───────────────────────────────────────────
echo "Bumping version to $VERSION..."
sed -i.bak "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
rm -f pyproject.toml.bak

# ── Run tests ────────────────────────────────────────────────────────────────
echo "Running tests..."
uv run pytest tests/ -q

# ── Run lint ─────────────────────────────────────────────────────────────────
echo "Running lint..."
uv run ruff check src/ tests/

# ── Commit version bump ───────────────────────────────────────────────────────
echo "Committing version bump..."
git add pyproject.toml
git commit -m "Release v$VERSION"

# ── Create annotated tag ─────────────────────────────────────────────────────
echo "Creating git tag v$VERSION..."
git tag -a "v$VERSION" -m "AgentVoca v$VERSION"

# ── Build ────────────────────────────────────────────────────────────────────
echo "Building release artifact..."
bash scripts/build.sh --clean

# ── Done — print next steps ──────────────────────────────────────────────────
echo ""
echo "Release v$VERSION prepared."
echo ""
echo "Next steps:"
echo "  1. Review the changes:"
echo "       git log --oneline -5"
echo "       git show v$VERSION"
echo ""
echo "  2. Push the commit and tag:"
echo "       git push origin main"
echo "       git push origin v$VERSION"
echo ""
echo "  3. Create a GitHub release:"
echo "       gh release create v$VERSION dist/AgentVoca* \\"
echo "         --title \"AgentVoca v$VERSION\" \\"
echo "         --notes \"See CHANGELOG or commits for details.\""
echo ""
echo "  To undo this release before pushing:"
echo "       git tag -d v$VERSION"
echo "       git reset --soft HEAD~1"
