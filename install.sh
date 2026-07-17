#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Server Status Monitor — installer (cPanel / CloudLinux)
# Run as root:   bash install.sh
# Deploys the collector (root cron) + dashboard (web account) and wires the
# root→web-user feed. Re-runnable; remembers answers in .install.conf.
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
CONF="$SRC/.install.conf"

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root (needs cron + chown)."; exit 1; }
[ -f "$SRC/src/index.php" ] && [ -f "$SRC/src/collector.sh" ] || { echo "ERROR: run from the repo root (src/ not found)."; exit 1; }

command -v whmapi1 >/dev/null 2>&1 || echo "WARNING: whmapi1 not found — this build targets cPanel/CloudLinux. Core metrics will work; cPanel-specific panels may be empty."

# ── Defaults (overridden by a previous run) ─────────────────────
WEB_USER=""; WEB_SUBDIR="public_html/status"; DATA_DIR="/root/server-status-monitor"
SITE_TITLE="Infrastructure Monitor"; SITE_SUBTITLE=""; LOGO_URL=""; FAVICON_URL=""
[ -f "$CONF" ] && . "$CONF"

ask() { local p="$1" d="$2" v; read -r -p "$p [$d]: " v || true; echo "${v:-$d}"; }

echo "── Server Status Monitor install ──"
WEB_USER="$(ask 'Web account (cPanel user that hosts the dashboard)' "$WEB_USER")"
[ -n "$WEB_USER" ] || { echo "ERROR: web account is required."; exit 1; }
id "$WEB_USER" >/dev/null 2>&1 || { echo "ERROR: user '$WEB_USER' does not exist."; exit 1; }
HOME_DIR="$(getent passwd "$WEB_USER" | cut -d: -f6)"; HOME_DIR="${HOME_DIR:-/home/$WEB_USER}"

WEB_SUBDIR="$(ask 'Dashboard sub-path under the account home' "$WEB_SUBDIR")"
DATA_DIR="$(ask 'Collector directory (root-owned)' "$DATA_DIR")"
[ -n "$SITE_SUBTITLE" ] || SITE_SUBTITLE="$(hostname) — Real-time server health"
SITE_TITLE="$(ask 'Site title' "$SITE_TITLE")"
SITE_SUBTITLE="$(ask 'Site subtitle' "$SITE_SUBTITLE")"
LOGO_URL="$(ask 'Logo URL (blank = initials)' "$LOGO_URL")"
FAVICON_URL="$(ask 'Favicon URL, same-origin (blank = generated tile)' "$FAVICON_URL")"

WEB_DIR="$HOME_DIR/$WEB_SUBDIR"
echo
echo "  web account : $WEB_USER ($HOME_DIR)"
echo "  dashboard   : $WEB_DIR"
echo "  collector   : $DATA_DIR"
read -r -p "Proceed? [y/N]: " ok; case "${ok:-N}" in y|Y) ;; *) echo "Aborted."; exit 0;; esac

# ── Save answers for re-runs ────────────────────────────────────
cat > "$CONF" <<EOF
WEB_USER="$WEB_USER"; WEB_SUBDIR="$WEB_SUBDIR"; DATA_DIR="$DATA_DIR"
SITE_TITLE="$SITE_TITLE"; SITE_SUBTITLE="$SITE_SUBTITLE"; LOGO_URL="$LOGO_URL"; FAVICON_URL="$FAVICON_URL"
EOF

# ── Collector (root) ────────────────────────────────────────────
mkdir -p "$DATA_DIR"
install -m 700 "$SRC/src/collector.sh" "$DATA_DIR/collector.sh"
cat > "$DATA_DIR/config.env" <<EOF
WEB_USER=$WEB_USER
DATA_DIR=$DATA_DIR
EOF
chmod 600 "$DATA_DIR/config.env"

# ── Dashboard (web account) ─────────────────────────────────────
mkdir -p "$WEB_DIR"
install -m 644 "$SRC/src/index.php" "$WEB_DIR/index.php"
# config.php via PHP so escaping is correct
cat > "$WEB_DIR/config.php" <<EOF
<?php return array(
  'web_user'      => '$WEB_USER',
  'site_title'    => '$(printf '%s' "$SITE_TITLE"    | sed "s/'/\\\\'/g")',
  'site_subtitle' => '$(printf '%s' "$SITE_SUBTITLE" | sed "s/'/\\\\'/g")',
  'logo_url'      => '$(printf '%s' "$LOGO_URL"      | sed "s/'/\\\\'/g")',
  'favicon_url'   => '$(printf '%s' "$FAVICON_URL"   | sed "s/'/\\\\'/g")',
);
EOF
chown -R "$WEB_USER:$WEB_USER" "$WEB_DIR/index.php" "$WEB_DIR/config.php"
chmod 644 "$WEB_DIR/index.php" "$WEB_DIR/config.php"

# ── Cron (idempotent; safe under set -e) ────────────────────────
CRON_LINE="* * * * * $DATA_DIR/collector.sh >/dev/null 2>&1"
EXISTING="$(crontab -l 2>/dev/null | grep -vF "$DATA_DIR/collector.sh" || true)"
printf '%s\n%s\n' "$EXISTING" "$CRON_LINE" | crontab -

# ── Prime + verify ──────────────────────────────────────────────
echo "Priming the collector (takes ~20s, it waits out the cron-storm offset)…"
bash "$DATA_DIR/collector.sh" || true
if [ -f "$HOME_DIR/.proc_snapshot" ]; then
  echo "OK: snapshot written to $HOME_DIR/.proc_snapshot"
else
  echo "WARNING: snapshot not found yet — the cron will produce it within ~1 minute."
fi

echo
echo "── Done ──"
# Docroot (public_html) isn't part of the URL — strip it for display.
URL_PATH="${WEB_SUBDIR#public_html}"; URL_PATH="${URL_PATH#/}"
echo "Dashboard: https://<your-domain>/$URL_PATH   (files at $WEB_DIR)"
echo "Collector: $DATA_DIR/collector.sh  (cron: every minute)"
echo "Edit branding later in $WEB_DIR/config.php, or re-run this installer."
