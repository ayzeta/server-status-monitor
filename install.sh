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
# -y / --yes : non-interactive re-deploy using saved answers (for update.sh).
AUTO=0
case "${1:-}" in -y|--yes) AUTO=1;; esac

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root (needs cron + chown)."; exit 1; }
[ -f "$SRC/src/index.php" ] && [ -f "$SRC/src/collector.sh" ] || { echo "ERROR: run from the repo root (src/ not found)."; exit 1; }

command -v whmapi1 >/dev/null 2>&1 || echo "WARNING: whmapi1 not found — this build targets cPanel/CloudLinux. Core metrics will work; cPanel-specific panels may be empty."

# ── Defaults (overridden by a previous run) ─────────────────────
WEB_USER=""; WEB_SUBDIR="public_html/status"; DATA_DIR="/root/server-status-monitor"
SITE_TITLE="Infrastructure Monitor"; SITE_SUBTITLE=""; LOGO_URL=""; FAVICON_URL=""
ALLOW_IPS=""; ACCESS_KEY=""
[ -f "$CONF" ] && . "$CONF"

# Enter = kayıtlı cevabı koru; '-' = kayıtlı cevabı TEMİZLE (boş kaydet).
# (Boş girişle silmek imkânsızdı: Enter varsayılanı koruduğu için.)
ask() { local p="$1" d="$2" v; read -r -p "$p [$d]: " v || true; v="${v:-$d}"; [ "$v" = "-" ] && v=""; echo "$v"; }

if [ $AUTO -eq 1 ]; then
  # Non-interactive: reuse saved answers, no prompts, keep existing config.php.
  [ -f "$CONF" ] || { echo "ERROR: no saved config (.install.conf). Run 'bash install.sh' once interactively first."; exit 1; }
  [ -n "$WEB_USER" ] || { echo "ERROR: saved config has no web account."; exit 1; }
  id "$WEB_USER" >/dev/null 2>&1 || { echo "ERROR: saved user '$WEB_USER' does not exist."; exit 1; }
  HOME_DIR="$(getent passwd "$WEB_USER" | cut -d: -f6)"; HOME_DIR="${HOME_DIR:-/home/$WEB_USER}"
  [ -n "$SITE_SUBTITLE" ] || SITE_SUBTITLE="$(hostname) — Real-time server health"
  WEB_DIR="$HOME_DIR/$WEB_SUBDIR"
  echo "── Update (non-interactive, saved settings) ──"
  echo "  web account : $WEB_USER   dashboard: $WEB_DIR   collector: $DATA_DIR"
else
  echo "── Server Status Monitor install ──"
  echo "Tip: Enter keeps the saved answer shown in [brackets]; type '-' to clear it."
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
  # Erişim kısıtı (önerilir): panel sürüm/hesap adı/süreç komutu gösterir — herkese
  # açık kalmamalı. IP verilirse .htaccess allowlist yazılır; boş = atla.
  echo "Access restriction (recommended): the dashboard shows versions, account"
  echo "names and process commands. Enter your static IP(s) to write an .htaccess"
  echo "allowlist (server's own IP + loopback stay allowed for CSF/WHMCS fetches)."
  ALLOW_IPS="$(ask 'Allowed IPs, space-separated (blank = skip)' "$ALLOW_IPS")"
  # Sabit IP'si olmayanlar için alternatif/ek katman: erişim anahtarı (?key=...).
  echo "No static IP? An access key protects the page instead (or in addition):"
  echo "visitors need ?key=... once; CSF/WHMCS URLs carry it as a parameter."
  ACCESS_KEY="$(ask 'Access key, long random string (blank = none)' "$ACCESS_KEY")"

  WEB_DIR="$HOME_DIR/$WEB_SUBDIR"
  echo
  echo "  web account : $WEB_USER ($HOME_DIR)"
  echo "  dashboard   : $WEB_DIR"
  echo "  collector   : $DATA_DIR"
  read -r -p "Proceed? [y/N]: " ok; case "${ok:-N}" in y|Y) ;; *) echo "Aborted."; exit 0;; esac

  # Save answers for re-runs / updates
  cat > "$CONF" <<EOF
WEB_USER="$WEB_USER"; WEB_SUBDIR="$WEB_SUBDIR"; DATA_DIR="$DATA_DIR"
SITE_TITLE="$SITE_TITLE"; SITE_SUBTITLE="$SITE_SUBTITLE"; LOGO_URL="$LOGO_URL"; FAVICON_URL="$FAVICON_URL"
ALLOW_IPS="$ALLOW_IPS"; ACCESS_KEY="$ACCESS_KEY"
EOF
fi

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
# config.php: keep existing on non-interactive update (preserves any manual
# edits like 'lang' => 'tr'); write it on interactive install / first run.
if [ $AUTO -eq 1 ] && [ -f "$WEB_DIR/config.php" ]; then
  echo "Keeping existing config.php (branding/lang preserved)."
else
  cat > "$WEB_DIR/config.php" <<EOF
<?php return array(
  'web_user'      => '$WEB_USER',
  'site_title'    => '$(printf '%s' "$SITE_TITLE"    | sed "s/'/\\\\'/g")',
  'site_subtitle' => '$(printf '%s' "$SITE_SUBTITLE" | sed "s/'/\\\\'/g")',
  'logo_url'      => '$(printf '%s' "$LOGO_URL"      | sed "s/'/\\\\'/g")',
  'favicon_url'   => '$(printf '%s' "$FAVICON_URL"   | sed "s/'/\\\\'/g")',
  'access_key'    => '$(printf '%s' "$ACCESS_KEY"    | sed "s/'/\\\\'/g")',
);
EOF
  chown "$WEB_USER:$WEB_USER" "$WEB_DIR/config.php"
  chmod 644 "$WEB_DIR/config.php"
fi
chown "$WEB_USER:$WEB_USER" "$WEB_DIR/index.php"
chmod 644 "$WEB_DIR/index.php"

# ── Access control (.htaccess IP allowlist, optional) ───────────
# Marker'lı blok: bizim dosyamızı günceller, kullanıcının kendi .htaccess'ine
# (marker yoksa) DOKUNMAZ. Loopback + sunucunun kendi IP'si daima izinli kalır —
# CSF'nin PT_APACHESTATUS çekmesi sunucunun kendisinden gelir.
HTFILE="$WEB_DIR/.htaccess"; HTMARK="server-status-monitor access control"
# Dosya HER ZAMAN yazılır (allowlist verilmese de): içindeki yeniden yazma kuralı
# erişim değil İŞLEVSELLİK meselesi — CSF'nin eki onsuz boş geliyor. Allowlist
# temizlendiğinde eskiden dosya silinirdi; artık yalnızca Deny/Allow satırları
# düşer, kural kalır.
# Blok yalnızca MARKER'lar ARASINA yazılır, dosyanın geri kalanına dokunulmaz.
# Eskiden tüm dosya 'cat >' ile yeniden yazılıyordu; cPanel kendi PHP direktif
# bloğunu aynı dosyaya eklediği için her güncellemede onu siliyorduk.
HTNEW="$(mktemp)"
SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
{
  echo "# BEGIN $HTMARK (managed by install.sh — only this block is rewritten)"
  # Her yol panoyu versin: CSF 16.31+, cPanel'in /var/cpanel/whm_server_status_key
  # dosyası varsa PT_APACHESTATUS'teki YOLU o anahtarla değiştiriyor ve isteği
  # /<anahtar> adresine yapıyor. Bu kural olmadan yük uyarısının eki boş gelir.
  echo "# Serve the dashboard from ANY path under this directory: CSF 16.31+ replaces"
  echo "# the path in PT_APACHESTATUS with cPanel's server-status key, so its high-load"
  echo "# fetch asks for /<key>. Real files are served normally; the query string survives."
  echo "<IfModule mod_rewrite.c>"
  echo "RewriteEngine On"
  echo "RewriteCond %{REQUEST_FILENAME} !-f"
  echo "RewriteRule ^ index.php [L]"
  echo "</IfModule>"
  if [ -n "${ALLOW_IPS:-}" ]; then
    # 2.2 sözdizimi (Order/Deny/Allow): hem Apache'de (mod_access_compat, cPanel
    # EA4'te varsayılan açık) hem LiteSpeed'de uygulanır. 2.4 <RequireAny> blokları
    # LiteSpeed'in .htaccess işleyicisinde YOK SAYILIR — sayfa sessizce açık kalır.
    echo "# 2.2-style rules: LiteSpeed ignores 2.4 <RequireAny> in .htaccess."
    echo "# Loopback + the server's own IP stay allowed so CSF's high-load fetch works."
    echo "# Polling ?raw=1 from WHMCS? Add the WHMCS server's IP as another Allow line."
    echo "Order deny,allow"
    echo "Deny from all"
    echo "Allow from 127.0.0.1"
    echo "Allow from ::1"
    [ -n "${SERVER_IP:-}" ] && echo "Allow from $SERVER_IP"
    for ip in $ALLOW_IPS; do echo "Allow from $ip"; done
  fi
  echo "# END $HTMARK"
} > "$HTNEW"

if [ -f "$HTFILE" ] && grep -q "BEGIN $HTMARK" "$HTFILE"; then
  HTTMP="$(mktemp)"
  awk -v b="# BEGIN $HTMARK" -v e="# END $HTMARK" -v f="$HTNEW" '
    index($0, b) == 1 { inblk = 1; while ((getline l < f) > 0) print l; close(f); next }
    index($0, e) == 1 { inblk = 0; next }
    !inblk
  ' "$HTFILE" > "$HTTMP"
  cat "$HTTMP" > "$HTFILE"; rm -f "$HTTMP"
  echo "Updated the managed block in $HTFILE (rest of the file untouched)."
else
  [ -f "$HTFILE" ] && printf '\n' >> "$HTFILE"
  cat "$HTNEW" >> "$HTFILE"
  echo "Added the managed block to $HTFILE."
fi
rm -f "$HTNEW"
chown "$WEB_USER:$WEB_USER" "$HTFILE"; chmod 644 "$HTFILE"
if [ -n "${ALLOW_IPS:-}" ]; then
  echo "Access restricted to: $ALLOW_IPS  (+ ${SERVER_IP:-server IP} & loopback for CSF)"
else
  echo "No IP allowlist — page is open (managed block keeps only the rewrite)."
fi

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

# CSF 16.31+ ile cPanel'in server-status anahtarı varsa, lfd PT_APACHESTATUS'teki
# YOLU o anahtarla değiştirir (yalnızca şema + ana makine korunur). Yol içeren bir
# adres önermek bu sunucularda sessizce boş ek üretir — bu yüzden tespit edip
# doğru biçimi yazıyoruz.
CSF_KEY_FILE="/var/cpanel/whm_server_status_key"
KEYQ=""; [ -n "${ACCESS_KEY:-}" ] && KEYQ="?key=$ACCESS_KEY"
if [ -s "$CSF_KEY_FILE" ]; then
  echo
  echo "CSF: this server has $CSF_KEY_FILE, so CSF REPLACES the path in"
  echo "     PT_APACHESTATUS with that key — a path like /$URL_PATH is discarded and"
  echo "     the high-load mail attachment comes back empty."
  echo "     Point it at a host whose document root IS $WEB_DIR (e.g. a subdomain):"
  echo "       PT_APACHESTATUS = \"https://status.<your-domain>/$KEYQ\""
  echo "     The managed .htaccess already answers on any path, so whichever key"
  echo "     CSF appends lands on the dashboard."
fi
if [ -n "${ACCESS_KEY:-}" ]; then
  echo "Access key active — integration URLs must carry it:"
  [ -s "$CSF_KEY_FILE" ] || echo "  CSF:   PT_APACHESTATUS = \"https://<your-domain>/$URL_PATH$KEYQ\""
  echo "  WHMCS: https://<your-domain>/$URL_PATH?raw=1&key=$ACCESS_KEY"
fi
