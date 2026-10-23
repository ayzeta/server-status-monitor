"""PHP yorumundan SAYFAYA metin sizintisi denetimi.

Gercek olay (2026-10-20): sablondaki bir '//' yorumunun ICINDE '?>' gecince PHP
blogu orada kapandi ve yorumun geri kalani sayfaya duz metin olarak dokuldu —
uretimde basligin ustune Turkce yorum metni bindi. 'php -l' bunu YAKALAMAZ,
cunku sozdizimi gecerli.

Iki ayri denetim:
 1) Kaynakta: '//' ya da '#' yorumunun icinde '?>' var mi.
 2) Ciktida: derlenmis HTML'de yorum kirintisi gorunuyor mu (kaynaktaki yorum
    satirlarindan alinan belirgin parcalar <script>/<style> disinda aranir).
"""
import io
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
KAYNAK = sys.argv[1] if len(sys.argv) > 1 else KOK + "src/index.php"
src = io.open(KAYNAK, encoding="utf-8", errors="replace").read()

hata = 0

# ── 1) Yorum icinde kapanis etiketi ────────────────────────────
for no, satir in enumerate(src.split("\n"), 1):
    s = satir.strip()
    if not (s.startswith("//") or s.startswith("#") or " // " in satir):
        continue
    # Yorumun basladigi yerden sonrasinda '?>' arariz
    i = satir.find("//")
    if i < 0:
        i = satir.find("#")
    if i >= 0 and "?>" in satir[i:]:
        hata += 1
        print("  SIZINTI RISKI %s:%d — yorum icinde kapanis etiketi var:" % (KAYNAK, no))
        print("    " + s[:110])

# ── 2) Derlenmis ciktida yorum kirintisi ───────────────────────
# Kaynaktaki yorum satirlarindan yeterince ayirt edici parcalar cikar, sonra
# <script>/<style> DISINDAKI HTML'de ara. Yorumlar urune sizmamali.
yorumlar = []
for satir in src.split("\n"):
    s = satir.strip()
    if s.startswith("//") and len(s) > 40:
        metin = s[2:].strip()
        # Kod gibi gorunen parcalari ele (degisken/etiket icerenler yanlis alarm verir)
        if any(c in metin for c in "<>${}()"):
            continue
        yorumlar.append(metin[:38])

for yol in ("docs/index.html", "docs/tr/index.html"):
    ham = io.open(KOK + yol, encoding="utf-8", errors="replace").read()
    disi = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", ham, flags=re.S | re.I)
    for y in yorumlar:
        if y and y in disi:
            hata += 1
            print("  SIZINTI %s — sayfada yorum metni gorunuyor: %r" % (yol, y))

print()
print("SIZINTI: %d" % hata)
sys.exit(1 if hata else 0)
