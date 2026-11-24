"""DONMUS KARE: ekran goruntusu dogru temada mi, yoksa gecisin ortasinda mi?

URETIMDE GORULDU (2026-11-25): "bash demo/build.sh && python demo/screenshots.py"
calistirildi ve dark-issues/dark-recovery kareleri ACIK temada cikti. Sebep
olculdu: urunun tema gecisi 0,3 s suruyor (body'de transition:background) ve
yakalama ani onunla yarisiyor. Ayni komut ayni girdiyle uc ayri sonuc verdi --
koyu (16,14,27), yari yolda gri (135,135,145; 20 Kasim'da depoya boyle bir kare
girmisti) ve tamamen acik (238,241,248).

KURAL: ?snap= / ?theme= ile dondurulmus karede GECIS OLMAZ -- demo.js butun
transition/animation'lari kapatir. Boylece ayni girdi ayni gorseli verir.

Test iki yerden bakar:
  1. demo.js kaynagi: donduran kosul ve kapatma var mi (kural kaynakta mi),
  2. depodaki JPEG'lerin kendi pikselleri: dark-* gercekten koyu mu, light-*
     gercekten acik mi (Pillow varsa; yoksa o kisim atlanir ve yazar).
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NL = chr(10)
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"
js = io.open(KOK + "demo/demo.js", encoding="utf-8", errors="replace").read()

gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-50s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, beklenen, NL, gelen))


# ── 1) Kural kaynakta mi ───────────────────────────────────────────────
b = js.find("if (SNAP || P.get('theme')) {")
ck("donmus kare kosulu demo.js'te", b > 0, True)
blok = js[b:b + 420] if b > 0 else ""
ck("  gecisler kapatiliyor", "transition:none !important" in blok, True)
ck("  animasyonlar da kapatiliyor", "animation:none !important" in blok, True)
ck("  her ogeye (::before/::after dahil)",
   "*,*::before,*::after" in blok, True)
# Tema ATAMASI kapatmadan ONCE olmali: once koyuya gec, sonra gecisi kaldir
# (tersi olsa ilk kare yine acik temada donardi).
ck("tema atamasi kapatmadan once",
   js.index("setAttribute('data-theme'") < b, True)

# ── 2) Depodaki kareler gercekten o temada mi ──────────────────────────
try:
    from PIL import Image
except ImportError:
    print("  (Pillow yok — piksel kontrolu atlandi)")
    Image = None

if Image is not None:
    for ad, koyu in [("dark-issues", True), ("dark-recovery", True),
                     ("light-en", False), ("light-tr", False)]:
        yol = KOK + "docs/screenshots/" + ad + ".jpg"
        if not os.path.exists(yol):
            ck(ad + ": dosya yok", False, True)
            continue
        im = Image.open(yol).convert("RGB")
        # Sol kenar, kartlarin disi: sayfa arka plani (--bg).
        r, g, bl = im.getpixel((6, 600))
        parlak = (r + g + bl) / 3
        ck("%s arka plani %s" % (ad, "koyu" if koyu else "acik"),
           parlak < 60 if koyu else parlak > 200, True)
        # Gecisin ortasinda yakalanan kare ne koyu ne acik olur (gri).
        ck("  %s gecis ortasinda degil" % ad, 90 < parlak < 190, False)

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
