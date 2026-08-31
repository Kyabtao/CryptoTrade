#!/usr/bin/env bash
# Activate the GitHub Actions workflows.
#
# The workflow files are checked in under ci/workflows/ because committing
# directly to .github/workflows/ requires the `workflows` scope, which
# automated GitHub App tokens usually do not have. Run this once, locally,
# with a token that does.
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p .github/workflows
cp ci/workflows/paper-trade.yml .github/workflows/paper-trade.yml
cp ci/workflows/tests.yml       .github/workflows/tests.yml

echo "Installed:"
echo "  .github/workflows/paper-trade.yml  (every 15 min + manual dispatch)"
echo "  .github/workflows/tests.yml        (pytest on push / PR)"
echo
echo "Next:"
echo "  git add .github/workflows && git commit -m 'ci: enable workflows' && git push"
echo
echo "Then allow Actions to commit the state file:"
echo "  Settings -> Actions -> General -> Workflow permissions -> Read and write"
