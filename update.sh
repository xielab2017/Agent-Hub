#!/usr/bin/env bash
# Safely update the current Agent Hub branch while preserving local changes.

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

log() {
  printf '%s\n' "$*"
}

fail() {
  log ""
  log "Update failed: $*"
  exit 1
}

if ! command -v git >/dev/null 2>&1; then
  fail "Git was not found. Install Git and try again."
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "This folder is not a Git clone. Downloaded ZIP folders cannot be updated with Git."
fi

BRANCH="$(git branch --show-current 2>/dev/null || true)"
if [[ -z "$BRANCH" ]]; then
  fail "The repository is in detached HEAD state. Switch to a branch before updating."
fi

REMOTE="origin"
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  fail "Git remote 'origin' is not configured."
fi

echo "=========================================="
echo "  Agent Hub - GitHub updater"
echo "=========================================="
echo
log "Folder : $ROOT"
log "Branch : $BRANCH"
log "Remote : $(git remote get-url "$REMOTE")"
log ""

STASHED=0
STASH_LABEL="agent-hub-auto-update-$(date '+%Y%m%d-%H%M%S')"

restore_stash() {
  if [[ "$STASHED" -ne 1 ]]; then
    return 0
  fi
  log "Restoring local changes..."
  if git stash pop --index; then
    STASHED=0
    return 0
  fi
  log ""
  log "Local changes could not be applied automatically."
  log "They are still preserved in git stash. Resolve the conflicts, then run:"
  log "  git stash list"
  log "  git stash pop"
  return 1
}

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  log "Saving local changes temporarily..."
  BEFORE_STASH="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
  if ! git stash push --include-untracked -m "$STASH_LABEL"; then
    fail "Could not preserve local changes. No update was performed."
  fi
  AFTER_STASH="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
  if [[ -n "$AFTER_STASH" && "$AFTER_STASH" != "$BEFORE_STASH" ]]; then
    STASHED=1
  fi
fi

log "Fetching updates from GitHub..."
if ! git fetch --prune "$REMOTE"; then
  restore_stash || true
  fail "Could not connect to GitHub or fetch the repository."
fi

log "Updating $BRANCH with fast-forward only..."
if ! git pull --ff-only "$REMOTE" "$BRANCH"; then
  restore_stash || true
  fail "The branch cannot be fast-forwarded. Local commits may need a manual rebase or merge."
fi

if ! restore_stash; then
  fail "GitHub was updated, but local changes need conflict resolution."
fi

echo
log "Update complete."
log "Commit : $(git rev-parse --short HEAD)"
log "Version: $(git log -1 --pretty=%s)"
log ""
log "Restart Agent Hub to load the new code:"
log "  macOS/Linux: ./ctl.sh restart"
log "  Windows: close the running Agent Hub process, then double-click start-agent-hub.bat"

