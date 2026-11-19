#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Server Status Monitor — quick update.  Run as root:  bash update.sh
# Pulls ONLY if the GitHub remote is ahead, then redeploys with your
# saved settings (no prompts, config.php/branding/lang preserved).
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root (install step needs cron + chown)."; exit 1; }
[ -d .git ] || { echo "ERROR: not a git checkout — 'git clone' the repo and run from it."; exit 1; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "Checking for updates on '$BRANCH'…"
git fetch --quiet origin "$BRANCH"

# UZAGA BAKTIK — panonun "en son ne zaman bakildi" sayacini da tazele.
# Altbilgi o yasi $DATA_DIR/.upd_cache dosyasinin mtime'indan okuyor ve o dosyayi
# normalde toplayici GUNDE BIR yaziyor. Elle guncelleme de uzaga bakmaktir:
# yazmasaydik, "ssmon update" kostuktan hemen sonra bile altbilgi "17 saat once
# bakildi" demeye devam eder, kullanici bos yere tekrar guncellerdi.
# Sayi merge'den ONCE hesaplanir (o anki gercek fark); merge'den sonra toplayici
# zaten her turda yerelden yeniden sayip 0'a dusurur.
# Alt kabukta ve "|| true" ile: set -e altinda eksik DATA_DIR guncellemeyi
# durdurmasin — bu sayac guncellemenin kendisinden daha onemli degil.
if [ -f .install.conf ]; then
  ( . ./.install.conf
    [ -n "${DATA_DIR:-}" ] && [ -d "$DATA_DIR" ] || exit 0
    printf '%s %s\n' "$(git rev-parse --short "origin/$BRANCH")" \
                     "$(git rev-list --count "@..origin/$BRANCH")" \
      > "$DATA_DIR/.upd_cache.tmp" \
      && mv "$DATA_DIR/.upd_cache.tmp" "$DATA_DIR/.upd_cache" \
      && chmod 600 "$DATA_DIR/.upd_cache"
  ) || true
fi

LOCAL="$(git rev-parse @)"
REMOTE="$(git rev-parse "origin/$BRANCH")"
BASE="$(git merge-base @ "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "Already up to date ($(git rev-parse --short @))."
  exit 0
fi
if [ "$LOCAL" != "$BASE" ]; then
  echo "Local branch has diverged from origin/$BRANCH (local commits present)."
  echo "Resolve manually:  git status   /   git log --oneline @{u}..@"
  exit 1
fi

echo "Update available: $(git rev-parse --short @) → $(git rev-parse --short "origin/$BRANCH")"
git log --oneline "@..origin/$BRANCH" | sed 's/^/  /'
git merge --ff-only "origin/$BRANCH"

echo
bash install.sh --yes
echo
echo "Updated to commit $(git rev-parse --short @) (git revision; the release version shows in the dashboard footer/subtitle)."
