#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Server Status Monitor — quick update.  Run as root:  bash update.sh
# Pulls ONLY if the GitHub remote is ahead, then redeploys with your
# saved settings (no prompts, config.php/branding/lang preserved).
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

# ── ONCE KENDINI /tmp'YE KOPYALA, ORADAN KOS ────────────────────
# Bu betik asagida "git merge" ile KENDINI diskte yeniden yaziyor. Bash ise
# betigi bayt konumuna gore parca parca okuyor: her dis komuttan once okudugu
# yere geri sariyor. Dosya bu arada degisirse kalan kisim KAYMIS konumdan
# okunur.
#
# 2026-11-19'da olculdu (bash 5.1.8, CloudLinux 8 ile ayni surum):
#   dosya UZARSA  -> eski konumdan devam etti, cop bir parca "command not found"
#                    verdi, sonra YENI dosyanin satirlari bastan kostu;
#   dosya KISALIRSA -> kalan satirlarin HICBIRI calismadi ve cikis kodu 0 kaldi.
# Ikincisi bizim icin sessiz felaket: merge'den sonraki "bash install.sh --yes"
# hic kosmaz, update.sh basariyla bitmis gorunur, git "guncelim" der ama panonun
# dosyalari eski kalir. Hata mesaji da yoktur.
#
# Cozum: betik kendini /tmp'ye kopyalayip oradan kosar. Merge artik CALISAN
# kopyaya dokunamaz. mktemp basarisiz olursa yerinde kosmaya devam eder —
# eski davranis, yani bu koruma hicbir seyi KOTULESTIRMEZ.
SSM_KOK="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${SSM_UPD_KOPYA:-}" ] \
   && KOPYA="$(mktemp /tmp/ssm_update.XXXXXX 2>/dev/null)" \
   && cat "$0" > "$KOPYA" 2>/dev/null && [ -s "$KOPYA" ]; then
  rc=0
  SSM_UPD_KOPYA=1 SSM_UPD_KOK="$SSM_KOK" bash "$KOPYA" "$@" || rc=$?
  rm -f "$KOPYA"
  exit $rc
fi
cd "${SSM_UPD_KOK:-$SSM_KOK}"

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
