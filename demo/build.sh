#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# demo/build.sh — CANLI DEMO'yu GitHub Pages için statik HTML'e döker.
#
# ÜRÜNE DOKUNMAZ: src/index.php'yi olduğu gibi (demo bayrağı YOK) render eder,
# ardından ÇIKTIYA iki şey enjekte eder:
#   1) <head>'e küçük bir shim — canlı ?json=1 fetch'ini yutar (Pages'te backend yok)
#   2) </body> öncesine <script src="demo.js"> — simülasyon motoru
# Sonuç: docs/index.html + docs/demo.js. Kurulan sunuculara demo kodu GİTMEZ.
#
# Pages: Settings → Pages → Deploy from branch → main → /docs
# ════════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/.."          # repo kökü

command -v php >/dev/null || { echo "php gerekli (statik export için)"; exit 1; }

mkdir -p docs docs/tr

# ── Render için sahte besleme ────────────────────────────────────────────
# index.php süreç bölümünü yalnızca anlık görüntü varsa basar. Demo boş veriyle
# render edilince o bölüm hiç oluşmuyor, demo.js de kartları kendi iskeletiyle
# kuruyordu — demo üründen sapıyordu (I/O kartı demoda hiç yoktu). Artık ürünün
# KENDİ işaretlemesi çıktıya giriyor; demo.js yalnız veri besliyor.
# mktemp -d DEGIL: Git Bash'te /tmp/... POSIX yolu doner ve Windows'taki PHP onu
# acamaz — besleme sessizce okunmaz, surec bolumu hic basilmazdi. Depo ici yol
# her iki isletim sisteminde de calisir.
SEED="demo/.seedtmp"
rm -rf "$SEED"; mkdir -p "$SEED"
cp demo/seed.snapshot "$SEED/.proc_snapshot"
# Artış görünümü için iki günlük kayıt: dünkü ve bugünkü.
{ printf "%s" "$(date -d yesterday +%F 2>/dev/null || date +%F)"
  printf " bluewave:21.300 shopfast:13.050 zencache:10.200 harborlab:8.550 acmeco:8.400\n"
  printf "%s" "$(date +%F)"
  printf " bluewave:22.635 shopfast:13.068 zencache:10.342 harborlab:8.573 acmeco:8.400\n"
} > "$SEED/.diskacct_history"
printf "<?php\nreturn ['home_dir' => '%s'];\n" "$SEED" > src/config.php
temizle(){ rm -rf "$SEED"; rm -f src/config.php; }
trap temizle EXIT


# ── EN (varsayılan) ──────────────────────────────────────────────────────
php src/index.php > docs/index.html          # pristine ürün, boş veriyle (EN)
php demo/inject.php docs/index.html
cp demo/demo.js docs/demo.js

# ── TR — statik demo dil değiştiremez (PHP yok); ayrı bir sayfa üretilir.
#    Dil düğmesi demo.js içinde EN(/) ↔ TR(/tr/) arası gezinir. ─────────────
php -r '$_COOKIE["lang"]="tr"; include "src/index.php";' > docs/tr/index.html
php demo/inject.php docs/tr/index.html
cp demo/demo.js docs/tr/demo.js

# Build makinesinin hostname'i statik HTML'e sızmasın (her iki sayfa)
HN="$(hostname 2>/dev/null || true)"
if [ -n "${HN:-}" ]; then
  sed -i "s/$HN/demo.ayzeta.net/g" docs/index.html docs/tr/index.html || true
fi

touch docs/.nojekyll

echo "Built: docs/index.html + docs/tr/index.html + demo.js ($(wc -c < docs/index.html) bytes EN)"
