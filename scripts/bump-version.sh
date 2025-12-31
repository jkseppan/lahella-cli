#!/bin/bash
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.1.2"
    exit 1
fi

VERSION="$1"

# Validate version format
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format X.Y.Z (e.g., 0.1.2)"
    exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Error: You have uncommitted changes. Please commit or stash them first."
    exit 1
fi

echo "Bumping version to $VERSION..."

# Update pyproject.toml
sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml

# Update __init__.py
sed -i '' "s/^__version__ = \".*\"/__version__ = \"$VERSION\"/" src/lahella_cli/__init__.py

# Update uv.lock
uv sync

# Commit and tag
git add pyproject.toml src/lahella_cli/__init__.py uv.lock
git commit -m "Release v$VERSION"
git tag "v$VERSION"

echo "🔼  Done! Created commit and tag v$VERSION"
echo "To publish: git push && git push --tags"
