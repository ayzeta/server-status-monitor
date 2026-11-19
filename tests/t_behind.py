"""Guncelleme uygulandiktan sonra "guncelleme var" yazisi hemen dusuyor mu.

Gercek olay: kullanici guncelledi (sunucu v1.5.35), footer hala "guncelleme var (1)"
diyordu — sayi gunluk onbellekten okunuyordu. Sayi artik her turda YERELDEN sayilir.

Test GERCEK git deposu kurar: iki depo (uzak + yerel), yerel geride birakilir,
sonra pull edilir; sayinin ag erisimi olmadan 0'a dusmesi beklenir.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
src = io.open(KOK + "src/collector.sh", encoding='utf-8', errors='replace').read()

# Kaynaktan sayma komutunu cikar — elle yazmayalim
m = re.search(r'UPD_BEHL=\$\(git -C "\$REPO_DIR" (rev-list --count "HEAD\.\.origin/\$UPD_BRL")',
              src)
if not m:
    sys.exit("yerel sayma komutu bulunamadi")
print("kaynaktaki sayma:", m.group(1))

tmp = tempfile.mkdtemp(prefix="beh")
uzak = os.path.join(tmp, "uzak")
yerel = os.path.join(tmp, "yerel")


def g(*a, cwd=None):
    r = subprocess.run(["git"] + list(a), cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip()


pass_ = fail = 0


def ck(ad, gelen, beklenen):
    global pass_, fail
    if str(gelen) == str(beklenen):
        pass_ += 1
        print("  %-44s -> %s" % (ad, gelen))
    else:
        fail += 1
        print("  BASARISIZ %s: beklenen=%s gelen=%s" % (ad, beklenen, gelen))


os.makedirs(uzak)
g("init", "-q", "-b", "main", cwd=uzak)
g("config", "user.email", "t@t"), g("config", "user.name", "t")
subprocess.run(["git", "config", "user.email", "t@t"], cwd=uzak)
subprocess.run(["git", "config", "user.name", "t"], cwd=uzak)
io.open(os.path.join(uzak, "a.txt"), "w").write("1")
g("add", "-A", cwd=uzak); g("commit", "-qm", "ilk", cwd=uzak)
g("clone", "-q", uzak, yerel)
subprocess.run(["git", "config", "user.email", "t@t"], cwd=yerel)
subprocess.run(["git", "config", "user.name", "t"], cwd=yerel)


def say():
    dal = g("rev-parse", "--abbrev-ref", "HEAD", cwd=yerel)
    return g("rev-list", "--count", "HEAD..origin/%s" % dal, cwd=yerel)


ck("klon tazeyken geride degil", say(), "0")

# Uzakta iki yeni tur
for i in (2, 3):
    io.open(os.path.join(uzak, "a.txt"), "w").write(str(i))
    g("add", "-A", cwd=uzak); g("commit", "-qm", "tur%d" % i, cwd=uzak)
ck("fetch YAPILMADAN sayi degismez", say(), "0")

g("fetch", "-q", "origin", "main", cwd=yerel)
ck("fetch sonrasi 2 tur geride", say(), "2")

# Guncelleme uygulandi (update.sh'in yaptigi: pull)
g("merge", "-q", "origin/main", cwd=yerel)
ck("guncelleme sonrasi ANINDA 0 (ag yok)", say(), "0")

# ════════════════════════════════════════════════════════════════════
# SAYI DOGRU AMA TAZE MI? (2026-11-19)
#
# Yukaridaki sayim dogru calisiyor, ama tek basina yetmiyor: yereldeki
# origin/<dal> isaretcisi ancak GUNDE BIR kosan fetch'le ilerliyor (collector.sh
# "gt 86400"). Iki fetch arasinda pano "guncel" derken aslinda "en son baktigimda
# guncelsem" diyor. Olculdu: 19 Kasim'da pano updBehind=0 gosterirken depo 4
# commit ileriydi ve kullanici panoyu guncel sandi. Asagisi, altbilginin artik
# SON BAKISIN YASINI da yazdigini sinar.
# ════════════════════════════════════════════════════════════════════
import time

# ── A) collector: onbellegin mtime'i yayinlaniyor mu ────────────────
# Satirlar URUN KAYNAGINDAN cikariliyor; elle kopyalansaydi test kendi
# yazdigini dogrulardi.
mc = re.search(r'(UPD_CHK=\$\(stat -c %Y "\$UPD_CACHE".*\n.*upd_checked \$UPD_CHK.*)\n', src)
if not mc:
    sys.exit("upd_checked yayini kaynakta bulunamadi")
parca = mc.group(1)

onb = os.path.join(tmp, "upd_cache")
io.open(onb, "w").write("abc1234 0\n")
DAMGA = int(time.time()) - 19 * 3600
os.utime(onb, (DAMGA, DAMGA))


def kosu(yol):
    r = subprocess.run(["bash", "-c", 'UPD_CACHE="$1"\n' + parca, "_", yol],
                       capture_output=True, text=True)
    return r.stdout.strip()


ck("onbellek varsa mtime yayinlaniyor", kosu(onb), "upd_checked %d" % DAMGA)
ck("onbellek yoksa satir hic yok", kosu(os.path.join(tmp, "yok")), "")

# ── B) altbilgi: sayinin yaninda yas da yaziliyor mu ────────────────
# Burasi URUNU RENDER EDIYOR: metnin kendisi olculur, kaynakta aranmaz.
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import ortak_cfg   # gercek config.php yok edilmesin

IS = os.path.join(tmp, "render")
NL = chr(10)
taban = io.open(KOK + "demo/seed.snapshot", encoding="utf-8", errors="replace").read()
taban = re.sub(r"\n--- Root checks ---\n(?:.|\n)*$", "\n", taban)
PHP_VAR = subprocess.run(["php", "-v"], capture_output=True).returncode == 0


def altbilgi(satirlar, lang="en"):
    shutil.rmtree(IS, ignore_errors=True)
    seed = os.path.join(IS, "seed")
    os.makedirs(seed)
    snap = taban + NL + "--- Root checks ---" + NL + NL.join(satirlar) + NL
    io.open(os.path.join(seed, ".proc_snapshot"), "w", encoding="utf-8",
            newline=NL).write(snap)
    ortak_cfg.yaz(KOK, seed)
    try:
        kod = ('$_COOKIE["lang"]="tr"; include "src/index.php";' if lang == "tr"
               else 'include "src/index.php";')
        r = subprocess.run(["php", "-r", kod], capture_output=True, timeout=180, cwd=KOK)
    finally:
        ortak_cfg.geri(KOK)
    if r.returncode:
        sys.exit("php hatasi: " + r.stderr.decode("utf-8", "replace")[:400])
    g = r.stdout.decode("utf-8", "replace")
    import html as _h
    m2 = re.search(r'id="footer-time">(.*?)</div>', g, re.S)
    return _h.unescape(m2.group(1)) if m2 else None


if not PHP_VAR:
    print("  ATLANDI: php yok, altbilgi render edilemedi")
else:
    ESKI = int(time.time()) - 19 * 3600          # 19 saat once bakilmis
    alt = altbilgi(["upd_rev abc1234", "upd_behind 4", "upd_checked %d" % ESKI])
    ck("geride: sayi yaziyor", "update available (4)" in alt, True)
    ck("geride: son bakisin yasi da yaziyor", "checked 19h ago" in alt, True)

    # ASIL KUSUR BURASIYDI: sayi 0 iken altbilgi hicbir sey demiyordu ve
    # kullanici panoyu guncel saniyordu. Simdi "guncel" DIYOR ama ne zamana
    # gore guncel oldugunu da soyluyor.
    alt = altbilgi(["upd_rev abc1234", "upd_behind 0", "upd_checked %d" % ESKI])
    ck("geride degil: 'guncel' yaziyor", "up to date" in alt, True)
    ck("geride degil: yas yine yaziyor", "checked 19h ago" in alt, True)

    alt = altbilgi(["upd_rev abc1234", "upd_behind 0"])
    ck("hic bakilmamis: bunu acikca soyluyor", "not checked yet" in alt, True)
    ck("hic bakilmamis: uydurma yas yok", "ago" in alt, False)

    # Git kopyasi olmayan kurulumda guncelleme takibi YOKTUR; orada "guncel"
    # demek yanlis olurdu, satir hic cikmamali.
    alt = altbilgi(["opcache 286 36608"])
    ck("git kopyasi yok: guncelleme metni hic cikmiyor",
       ("up to date" in alt) or ("checked" in alt) or ("update available" in alt), False)

    # Turkcesi sozlukte mi: t() eksik anahtarda SESSIZCE Ingilizceye duser,
    # yani "ekranda bir sey yaziyor" yetmez.
    alt = altbilgi(["upd_rev abc1234", "upd_behind 0", "upd_checked %d" % ESKI], "tr")
    ck("TR: 'güncel · 19sa önce bakıldı'",
       ("güncel" in alt) and ("19sa önce bakıldı" in alt), True)

shutil.rmtree(tmp, ignore_errors=True)
print()
print("GECEN: %d  KALAN: %d" % (pass_, fail))
sys.exit(1 if fail else 0)
