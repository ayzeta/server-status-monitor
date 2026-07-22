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
