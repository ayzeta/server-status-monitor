#!/usr/bin/env python3
"""README ekran goruntulerini DEMO SAYFASINDAN yeniden uretir.

    python demo/screenshots.py            dort kareyi de uret
    python demo/screenshots.py light-tr   yalniz adi eslesenleri

Neden boyle: README'deki dort gorsel urunun kendi arayuzu. Elle alinirsa her
seferinde baska genislik, baska an, baska tema cikiyor ve goruntuler sessizce
surumden geri kaliyor. Bu betik demo sayfasini sabit olculerde, sabit sahnede
(?snap=) ve sabit temada (?theme=) cekiyor — yani ayni girdi ayni gorseli verir.

ONCE "bash demo/build.sh" calistirilmali: goruntuler docs/ altindaki statik
demo sayfalarindan alinir, src/index.php'den degil.

Gerekenler: Chrome ya da Chromium (headless) ve Pillow (PNG -> JPEG).
Chrome yolu bulunamazsa CHROME ortam degiskeniyle verilebilir.
"""
import os
import shutil
import subprocess
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEDEF = os.path.join(KOK, "docs", "screenshots")

# (dosya adi, demo sayfasi, sorgu, yukseklik) — genislik hepsinde 1200.
# Yukseklikler sayfanin o sahnedeki boyuna gore secildi; karti yarida kesmesin.
KARELER = [
    ("dark-issues",   "docs/index.html",    "theme=dark&snap=issues",   2392),
    ("dark-recovery", "docs/index.html",    "theme=dark&snap=recovery", 2392),
    ("light-en",      "docs/index.html",    "theme=light&snap=calm",    1954),
    ("light-tr",      "docs/tr/index.html", "theme=light&snap=calm",    1954),
]
GENISLIK = 1200
KALITE = 86


def chrome_bul():
    """Once CHROME ortam degiskeni, sonra PATH, sonra bilinen kurulum yerleri."""
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for ad in ("google-chrome", "google-chrome-stable", "chromium",
               "chromium-browser", "chrome"):
        yol = shutil.which(ad)
        if yol:
            return yol
    adaylar = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/snap/bin/chromium",
    ]
    for y in adaylar:
        if y and os.path.exists(y):
            return y
    return None


def main():
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow gerekli:  pip install Pillow")
    chrome = chrome_bul()
    if not chrome:
        sys.exit("Chrome/Chromium bulunamadi. CHROME=/yol/chrome ile verebilirsin.")

    secim = [a.lower() for a in sys.argv[1:]]
    os.makedirs(HEDEF, exist_ok=True)
    uretilen = 0
    for ad, sayfa, sorgu, yukseklik in KARELER:
        if secim and not any(s in ad.lower() for s in secim):
            continue
        kaynak = os.path.join(KOK, sayfa.replace("/", os.sep))
        if not os.path.exists(kaynak):
            sys.exit("%s yok — once 'bash demo/build.sh' calistir." % sayfa)
        url = "file:///" + kaynak.replace(os.sep, "/") + "?" + sorgu
        png = os.path.join(HEDEF, ad + ".png")
        # virtual-time-budget: demo once sayfanin kendi ilk tikini basiyor, sonra
        # demo.js kareyi kuruyor. Erken cekilen goruntu yarim kalirdi.
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--virtual-time-budget=9000",
                        "--window-size=%d,%d" % (GENISLIK, yukseklik),
                        "--screenshot=" + png, url],
                       capture_output=True, timeout=180)
        if not os.path.exists(png):
            sys.exit("cekilemedi: %s" % ad)
        jpg = os.path.join(HEDEF, ad + ".jpg")
        im = Image.open(png).convert("RGB")
        im.save(jpg, "JPEG", quality=KALITE, optimize=True)
        os.remove(png)
        print("%-14s %dx%d  %s" % (ad, im.size[0], im.size[1],
                                   os.path.relpath(jpg, KOK).replace(os.sep, "/")))
        uretilen += 1
    if not uretilen:
        sys.exit("eslesen kare yok. Adlar: " + ", ".join(k[0] for k in KARELER))


if __name__ == "__main__":
    main()
