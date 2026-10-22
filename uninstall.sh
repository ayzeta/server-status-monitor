#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# server-status-monitor — uninstall.  Run as root:  bash uninstall.sh
#
# Removes what install.sh created, and nothing else:
#   - the root cron line that runs the collector
#   - the collector and its state files in DATA_DIR
#   - index.php / config.php in the web directory
#   - ONLY the managed block inside the account's .htaccess (the rest is kept —
#     cPanel writes its own PHP handler block there and it must survive)
#   - the data files the collector drops in the account's home
#   - the probe caches in the temp directory
#   - the ssmon command
#
# Kept on purpose: this git checkout (delete it yourself if you want), the
# account itself, and anything you put in the web directory.
#
#   --purge    also delete config.php (branding/lang) and the saved answers
#   --yes      no questions
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
SRC="$(pwd)"
CONF="$SRC/.install.conf"

PURGE=0; AUTO=0
for a in "$@"; do
  case "$a" in
    --purge) PURGE=1 ;;
    --yes|-y) AUTO=1 ;;
    *) echo "Usage: bash uninstall.sh [--purge] [--yes]"; exit 1 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root (needs cron + file removal)."; exit 1; }

# Saved answers tell us WHERE everything went. Without them we cannot know the
# account or the collector directory, and guessing would risk deleting the wrong
# files — so we stop instead.
[ -f "$CONF" ] || { echo "ERROR: no saved config ($CONF) — nothing to remove from here."; exit 1; }
# shellcheck disable=SC1090
. "$CONF"
: "${WEB_USER:?missing WEB_USER in .install.conf}"
: "${DATA_DIR:?missing DATA_DIR in .install.conf}"
HOME_DIR="${HOME_DIR:-$(getent passwd "$WEB_USER" | cut -d: -f6)}"
[ -n "$HOME_DIR" ] || { echo "ERROR: cannot resolve home directory of $WEB_USER."; exit 1; }
WEB_DIR="$HOME_DIR/${WEB_SUBDIR:-public_html/status}"

echo "About to remove:"
echo "  cron         : * * * * * $DATA_DIR/collector.sh"
echo "  collector    : $DATA_DIR/collector.sh (+ state files)"
echo "  dashboard    : $WEB_DIR/index.php"
[ "$PURGE" = 1 ] && echo "  config       : $WEB_DIR/config.php  (--purge)"
echo "  htaccess     : only the managed block in $WEB_DIR/.htaccess"
echo "  feed files   : $HOME_DIR/.proc_snapshot, .metrics_history, .disk_history, .diskacct_history"
echo "  command      : /usr/local/bin/ssmon"
echo
if [ "$AUTO" != 1 ]; then
  printf 'Continue? [y/N] '
  read -r ans
  case "$ans" in y|Y|yes|YES) ;; *) echo "Cancelled."; exit 0 ;; esac
fi

# ── Cron first: stop new writes before deleting what they write to ───────────
if crontab -l >/dev/null 2>&1; then
  crontab -l 2>/dev/null | grep -vF "$DATA_DIR/collector.sh" | crontab - || true
  echo "  cron line removed"
fi

# ── Collector + its state ────────────────────────────────────────────────────
# Named one by one on purpose: DATA_DIR may be a directory the user also keeps
# other things in, so 'rm -rf $DATA_DIR' would be too blunt.
for f in collector.sh config.env \
         .act_state .act_matches .cpu_state .csf_state .diskacct_cache \
         .imunify_cache .io_state .ioproc_state .ioproc_state.ps .lve_io \
         .mailq_cache .net_state .smart_cache .upd_cache .upd_state \
         .upd_run .upd_run.lock .ver_cache; do
  rm -f "$DATA_DIR/$f"
done
echo "  collector and state files removed"
rmdir "$DATA_DIR" 2>/dev/null && echo "  $DATA_DIR was empty, removed" || true

# ── Web files ────────────────────────────────────────────────────────────────
rm -f "$WEB_DIR/index.php"
[ "$PURGE" = 1 ] && rm -f "$WEB_DIR/config.php"
echo "  dashboard removed"

# ── .htaccess: ONLY our managed block ────────────────────────────────────────
# cPanel keeps its PHP handler block in the same file; dropping the whole file
# would change how PHP runs for the account.
HTFILE="$WEB_DIR/.htaccess"; HTMARK="server-status-monitor access control"
if [ -f "$HTFILE" ] && grep -q "BEGIN $HTMARK" "$HTFILE"; then
  TMP="$HTFILE.tmp.$$"
  awk -v b="# BEGIN $HTMARK" -v e="# END $HTMARK" '
    $0 == b { skip = 1 } !skip { print } $0 == e { skip = 0 }' "$HTFILE" > "$TMP"
  if [ -s "$TMP" ]; then
    mv -f "$TMP" "$HTFILE"
    # Sahiplik/izin geri verilemezse KALDIRMA DURMAZ: dosya zaten yerinde ve
    # 'set -e' yüzünden bütün işlemi yarıda kesmek, yarım kaldırılmış bir kurulum
    # bırakırdı (besleme dosyaları, ssmon komutu silinmeden kalır).
    chown "$WEB_USER:$WEB_USER" "$HTFILE" 2>/dev/null || true
    chmod 644 "$HTFILE" 2>/dev/null || true
    echo "  managed .htaccess block removed (rest of the file kept)"
  else
    rm -f "$TMP" "$HTFILE"           # dosyada bizim bloktan baska bir sey yokmus
    echo "  .htaccess contained only our block, removed"
  fi
fi

# ── Feed files in the account's home ─────────────────────────────────────────
rm -f "$HOME_DIR/.proc_snapshot" "$HOME_DIR/.metrics_history" \
      "$HOME_DIR/.disk_history" "$HOME_DIR/.diskacct_history"
echo "  feed files removed"

# ── Probe caches (temp dir, named per account) ───────────────────────────────
# The page writes these as the web user; under CageFS they live in the account's
# own temp directory, so both locations are swept.
rm -f /tmp/az_*_*.json 2>/dev/null || true
rm -f "$HOME_DIR"/.cagefs/tmp/az_*_*.json 2>/dev/null || true
echo "  probe caches removed"

# ── Management command ───────────────────────────────────────────────────────
rm -f /usr/local/bin/ssmon
echo "  ssmon command removed"

if [ "$PURGE" = 1 ]; then
  rm -f "$CONF"
  echo "  saved answers removed ($CONF)"
fi

echo
echo "Done. This checkout is still here: $SRC"
echo "Remove it with:  rm -rf $SRC"
