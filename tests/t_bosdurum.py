"""Bos durum cumleleri DOGRU AYRILIYOR mu — urunu gercekten render ederek.

Dort durum:
  olcum var + satir var   -> satirlar
  olcum var + satir yok   -> "su an ... yapan yok"
  olcum yok (isaret yok)  -> "veri bekleniyor" / "olculemedi"
Hem hesap hem surec tarafi, hem TR hem EN.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
IS = os.path.join(BURASI, "bosdurum")
NL = chr(10)

# Taban olarak URUNUN kendi demo tohumu kullanilir: kartlar ancak gecerli bir
# anlik goruntuyle olusuyor, elde uydurulmus minik dosya satiri hic basmiyordu.
TABAN = io.open(KOK + "demo/seed.snapshot", encoding="utf-8", errors="replace").read()
IO_BOLUM = {
    "dolu": "io_src lve 1m" + NL + "ioacct makinem 45.0 12" + NL,
    "olctuk_yok": "io_src lve 1m" + NL,
    "olcum_yok": "",
}
PROC_BOLUM = {
    "dolu": "ioproc_ok 1m" + NL + "ioproc 42 mysql 2048.0 /usr/sbin/mariadbd" + NL,
    "olctuk_yok": "ioproc_ok 1m" + NL,
    "olcum_yok": "",
}


def tohum(ad):
    s = re.sub(r"io_src lve 1m\n(ioacct .*\n)*", IO_BOLUM[ad], TABAN, count=1)
    return re.sub(r"ioproc_ok 1m\n(ioproc .*\n?)*", PROC_BOLUM[ad], s, count=1)


def render(ad, lang):
    shutil.rmtree(IS, ignore_errors=True)
    seed = os.path.join(IS, "seed")
    os.makedirs(seed)
    io.open(os.path.join(seed, ".proc_snapshot"), "w", encoding="utf-8",
            newline=NL).write(tohum(ad))
    cfg = KOK + "src/config.php"
    io.open(cfg, "w", encoding="utf-8", newline=NL).write(
        "<?php" + NL + "return ['home_dir' => " + json.dumps(seed.replace("\\", "/")) + "];" + NL)
    try:
        kod = ('$_COOKIE["lang"]="tr"; include "src/index.php";' if lang == "tr"
               else 'include "src/index.php";')
        r = subprocess.run(["php", "-r", kod], capture_output=True, timeout=120, cwd=KOK)
    finally:
        os.remove(cfg)
    if r.returncode:
        sys.exit("php hatasi: " + r.stderr.decode("utf-8", "replace")[:400])
    govde = r.stdout.decode("utf-8", "replace")
    # YALNIZ KARTIN kendisine bak: ceviri sozlugu sayfaya JSON olarak gomuluyor,
    # tum metinler her sayfada gecer — tum govdede aramak testi anlamsiz kilar.
    i = govde.index('id="io-card"')
    # ASCII disi karakterler sayfaya HTML varligi olarak basiliyor (webmail
    # charset'i silince bozulmasin diye) — karsilastirmadan once cozulur.
    import html as _h
    return _h.unescape(govde[i:i + 4000])


gecen = kalan = 0


def ck(ad, govde, olmali, olmamali=()):
    global gecen, kalan
    eksik = [s for s in olmali if s not in govde]
    fazla = [s for s in olmamali if s in govde]
    if not eksik and not fazla:
        gecen += 1
        print("  %-46s -> tamam" % ad)
    else:
        kalan += 1
        print("  BASARISIZ %s: eksik=%r beklenmeyen=%r" % (ad, eksik, fazla))


tr = render("dolu", "tr")
ck("TR dolu: satirlar var, bos cumle yok", tr,
   ["makinem", "mariadbd"],
   ["şu an disk I/O yapan hesap yok", "I/O verisi bekleniyor", "süreç I/O ölçülemedi"])

tr = render("olctuk_yok", "tr")
ck("TR olctuk ama yapan yok", tr,
   ["şu an disk I/O yapan hesap yok", "şu an disk I/O yapan süreç yok"],
   ["I/O verisi bekleniyor", "süreç I/O ölçülemedi"])

tr = render("olcum_yok", "tr")
ck("TR olcum yok: bekleniyor/olculemedi", tr,
   ["I/O verisi bekleniyor", "süreç I/O ölçülemedi"],
   ["şu an disk I/O yapan"])

en = render("olctuk_yok", "en")
ck("EN olctuk ama yapan yok", en,
   ["no account is doing I/O right now", "no process is doing I/O right now"],
   ["I/O data pending", "no process I/O measured"])

en = render("dolu", "en")
ck("EN pencere etiketi satirda", en, ["account · LVE 1m"])

shutil.rmtree(IS, ignore_errors=True)
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
