#!/usr/bin/env bash
# Publish chat.meoarch.org from a workstation (CI only builds and stages; see README "Deploying").
#
#   MEO_UI_ROOT=<MeoUI checkout at the ref in .github/workflows/meo-web-client.yml> \
#     scripts/deploy-local.sh [--dry-run]
#
# Needs: node, npm, cargo + wasm-bindgen-cli (see README), and `wrangler login` done once.
# Steps: test and typecheck, build, stage like CI, print the current production deployment (the
# rollback target), upload, then smoke-check the live site.
set -euo pipefail

: "${MEO_UI_ROOT:?Set MEO_UI_ROOT to a MeoUI checkout at the ref CI uses.}"
project="meo-ai-web"
site="https://chat.meoarch.org"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
dry=false
[ "${1:-}" = "--dry-run" ] && dry=true

cd "$here"
npm ci
npm run typecheck
npm test

MEO_OUTPUT_ROOT="$work" MEO_UI_ROOT="$MEO_UI_ROOT" npm run build
mkdir -p "$work/stage"
cp -r "$work/meo-ai/build/web" "$work/stage/site"
cp -r "$here/functions" "$work/stage/functions"

echo "Current production deployment (rollback target):"
npx --yes wrangler pages deployment list --project-name="$project" --environment=production | sed -n '1,6p'

if $dry; then
  echo "Dry run: built and staged at $work/stage, nothing uploaded."
  trap - EXIT
  exit 0
fi

(cd "$work/stage" && npx --yes wrangler pages deploy site --project-name="$project" --branch=main --commit-dirty=true)

echo "Smoke checks:"
home=$(curl -s -o /dev/null -w '%{http_code}' "$site/")
session=$(curl -s -o /dev/null -w '%{http_code}' "$site/api/meo/session")
xsite=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Origin: https://evil.example' "$site/api/meo/x")
live=$(curl -s "$site/" | grep -o 'assets/index-[^"]*\.js' | head -1)
built=$(ls "$work/stage/site/assets" | grep -o '^index-[^ ]*\.js' | head -1)
echo "  home=$home (want 200)  session=$session (want 401)  cross-site POST=$xsite (want 403)"
echo "  live script=$live  built script=assets/$built"
[ "$home" = 200 ] && [ "$session" = 401 ] && [ "$xsite" = 403 ] && [ "$live" = "assets/$built" ] \
  || { echo "Smoke check failed: compare with the rollback target above." >&2; exit 1; }
echo "Deployed and verified."
