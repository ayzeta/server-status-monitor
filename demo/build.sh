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

mkdir -p docs
php src/index.php > docs/index.html          # pristine ürün, boş veriyle (EN)
cp demo/demo.js docs/demo.js

# Çıktıya demo enjeksiyonu (regex yok — php str_replace, güvenli)
php demo/inject.php docs/index.html

# Build makinesinin hostname'i statik HTML'e sızmasın
HN="$(hostname 2>/dev/null || true)"
[ -n "${HN:-}" ] && sed -i "s/$HN/demo.ayzeta.net/g" docs/index.html || true

touch docs/.nojekyll

echo "Built: docs/index.html ($(wc -c < docs/index.html) bytes) + docs/demo.js"
