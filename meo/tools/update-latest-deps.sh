#!/usr/bin/env bash
# Move Meo AI's own libraries (Rust crates, the web client's npm packages and
# the pinned Python requirements) to their newest releases, prove the result
# still builds, and keep the old versions if it does not.
#
# Matches the owner policy: update dependencies to the newest versions
# dynamically; only if a bug survives a real fix attempt, roll back and say so.
#
#   meo/tools/update-latest-deps.sh            update + verify all
#   meo/tools/update-latest-deps.sh rust web   only the named parts
#   meo/tools/update-latest-deps.sh --dry-run  show what would change
#
# Release builds must stay reproducible: set MEO_AI_SKIP_DEP_UPDATE=1 there
# (the signed meo-repo manifests pin exact commits and lockfiles).
set -uo pipefail

if [ "${MEO_AI_SKIP_DEP_UPDATE:-0}" = "1" ]; then
  echo "update-latest-deps: skipped (MEO_AI_SKIP_DEP_UPDATE=1)"
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
dry=0
parts=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry=1 ;;
    rust|web|python) parts+=("$arg") ;;
    *) echo "usage: $0 [--dry-run] [rust] [web] [python]" >&2; exit 64 ;;
  esac
done
[ "${#parts[@]}" -gt 0 ] || parts=(rust web python)

failed=()
changed=()

# backup FILE... -> $stash/<path>; restore puts them back.
stash="$(mktemp -d)"
trap 'rm -rf "$stash"' EXIT
backup() { for f in "$@"; do [ -f "$f" ] && { mkdir -p "$stash/$(dirname "${f#$root/}")"; cp -p "$f" "$stash/${f#$root/}"; }; done; }
restore() { for f in "$@"; do [ -f "$stash/${f#$root/}" ] && cp -p "$stash/${f#$root/}" "$f"; done; }
differs() { for f in "$@"; do [ -f "$stash/${f#$root/}" ] && ! cmp -s "$f" "$stash/${f#$root/}" && return 0; done; return 1; }

update_rust() {
  command -v cargo >/dev/null || { echo "rust: cargo not found, skipped"; return 0; }
  local dir manifest lock
  for dir in "$root/meo/core-rs" "$root/meo/desktop-rs"; do
    [ -f "$dir/Cargo.toml" ] || continue
    manifest="$dir/Cargo.toml"; lock="$dir/Cargo.lock"
    echo "rust: $dir"
    if [ "$dry" = 1 ]; then (cd "$dir" && cargo update --dry-run 2>&1 | tail -n 20); continue; fi
    backup "$manifest" "$lock"
    (
      cd "$dir" || exit 1
      # cargo-edit (if present) also lifts version requirements across majors.
      if cargo upgrade --help >/dev/null 2>&1; then cargo upgrade --incompatible >/dev/null 2>&1 || true; fi
      cargo update 2>&1 | tail -n 5
    )
    if ! (cd "$dir" && cargo check --all-targets 2>&1 | tail -n 3; exit "${PIPESTATUS[0]}"); then
      restore "$manifest" "$lock"; failed+=("rust:$(basename "$dir")")
    elif differs "$manifest" "$lock"; then changed+=("rust:$(basename "$dir")"); fi
  done
}

update_web() {
  local dir="$root/meo/web/client"
  command -v npm >/dev/null && [ -f "$dir/package.json" ] || { echo "web: npm or client missing, skipped"; return 0; }
  echo "web: $dir"
  if [ "$dry" = 1 ]; then (cd "$dir" && npx --yes npm-check-updates 2>&1 | tail -n 25); return 0; fi
  backup "$dir/package.json" "$dir/package-lock.json"
  if (cd "$dir" \
      && npx --yes npm-check-updates -u >/dev/null 2>&1 \
      && npm install --no-audit --no-fund >/dev/null 2>&1 \
      && npm run typecheck >/dev/null 2>&1 \
      && npm test >/dev/null 2>&1); then
    differs "$dir/package.json" "$dir/package-lock.json" && changed+=("web")
  else
    restore "$dir/package.json" "$dir/package-lock.json"
    (cd "$dir" && npm install --no-audit --no-fund >/dev/null 2>&1) || true
    failed+=("web")
  fi
}

update_python() {
  command -v python3 >/dev/null || { echo "python: python3 not found, skipped"; return 0; }
  local file line name current latest tmp
  for file in "$root/meo/cloud/requirements.txt" "$root/meo/device/requirements.txt" "$root/modules/requirements.txt"; do
    [ -f "$file" ] || continue
    echo "python: $file"
    backup "$file"
    tmp="$(mktemp)"
    while IFS= read -r line || [ -n "$line" ]; do
      if [[ "$line" =~ ^([A-Za-z0-9_.-]+(\[[A-Za-z0-9_,-]+\])?)==([0-9][^[:space:];]*)(.*)$ ]]; then
        name="${BASH_REMATCH[1]}"; current="${BASH_REMATCH[3]}"
        latest="$(python3 -m pip index versions "${name%%[*}" 2>/dev/null | sed -n 's/^LATEST: *//p;s/^[^(]*(\([^)]*\)).*/\1/p' | head -n 1)"
        if [ -n "$latest" ] && [ "$latest" != "$current" ]; then
          echo "  ${name}: $current -> $latest"
          line="${name}==${latest}${BASH_REMATCH[4]}"
        fi
      fi
      printf '%s\n' "$line" >>"$tmp"
    done <"$file"
    if [ "$dry" = 1 ]; then rm -f "$tmp"; continue; fi
    cp "$tmp" "$file"; rm -f "$tmp"
    # Resolution check without installing anything.
    if python3 -m pip install --dry-run -r "$file" >/dev/null 2>&1; then
      differs "$file" && changed+=("python:$(basename "$(dirname "$file")")")
    else
      restore "$file"; failed+=("python:$(basename "$(dirname "$file")")")
    fi
  done
}

for part in "${parts[@]}"; do "update_$part"; done

echo
[ "${#changed[@]}" -eq 0 ] || echo "updated: ${changed[*]}"
if [ "${#failed[@]}" -gt 0 ]; then
  echo "kept previous versions (newest did not build/resolve): ${failed[*]}" >&2
  exit 1
fi
echo "update-latest-deps: done"
