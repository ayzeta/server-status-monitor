"""Mail eki kisitlari: 900 bayt/satir siniri ve <script> DISINDA ASCII-disi yok.

SMTP satirlari boldugu icin uzun satir eki bozar; ASCII-disi karakterler de
script disinda sayisal varlik olmali (demo/build.sh bunu yapiyor).
"""
import io
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
hata = 0

for yol in ("docs/index.html", "docs/tr/index.html"):
    ham = io.open(KOK + yol, encoding="utf-8", errors="replace").read()
    uzun = [(i + 1, len(s.encode("utf-8")))
            for i, s in enumerate(ham.split("\n"))
            if len(s.encode("utf-8")) > 900]
    # <script> bloklarini cikar, kalan metinde ASCII-disi ara
    disi = re.sub(r"<script[^>]*>.*?</script>", "", ham, flags=re.S | re.I)
    ascii_disi = sorted({c for c in disi if ord(c) > 127})
    print("%-22s 900+bayt=%-3d scriptdisi-ascii-disi=%d %s" % (
        yol, len(uzun), len(ascii_disi), ascii_disi[:8]))
    if uzun:
        print("   ilk uzun satirlar:", uzun[:5])
    hata += len(uzun) + len(ascii_disi)

print()
print("TOPLAM SORUN: %d" % hata)
sys.exit(1 if hata else 0)
