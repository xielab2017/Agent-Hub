#!/usr/bin/env bash
# Push <dir> to the current branch every <interval> seconds (live screenshots / logs / checkpoints of a CI run).
#   scripts/push_loop.sh outputs/skill_demo 90 &
# On a conflict in these files the run's own version wins (-X theirs = the commit being replayed).
DIR=${1:?dir}; EVERY=${2:-90}; BR=${GITHUB_REF_NAME:?branch}
while true; do
  sleep "$EVERY"
  git add "$DIR" >/dev/null 2>&1 || continue
  git diff --cached --quiet && continue
  git commit -qm "Skill demo live: $DIR (run ${GITHUB_RUN_ID:-local})" || continue
  for i in 1 2 3; do
    git pull -q --rebase -X theirs origin "$BR" && git push -q origin "HEAD:$BR" && break
    git rebase --abort 2>/dev/null || true
    sleep 3
  done
done
