"""SSL yoklamasinin onbellegi: BASARISIZLIK da yazilir mi, ne kadar yasar.

Neden: pano WHM'in 2087 portundan sertifikayi okur ve sonucu onbellege yazar.
Eskiden YALNIZ basari yaziliyordu — 2087 cevap vermediginde hicbir kayit
olusmuyor, bu yuzden HER sayfa acilisi 5 saniyelik zaman asimini bastan
bekliyordu. WHM tokezledigi surece pano onunla birlikte agirlasiyordu.

Sinanan davranis (2026-11-19'da eklendi):
  * basarisizlik da yazilir, ama KISA omurle (300 sn); basari 6 saat yasar
  * taze onbellek varken yoklama HIC yapilmaz
  * omur dolunca yeniden yoklanir
  * 'ok' alani OLMAYAN eski onbellek dosyalari hala basari sayilir (6 saat)

OLCUM YONTEMI — dosyanin MTIME'i: urun yoklamayi yaptiysa onbellegi yeniden
yazar, yani mtime degisir; onbellegi kullandiysa dosyaya hic dokunmaz. Boylece
"yoklama kosuldu mu" sorusu sureye (makineye) degil, dosyaya bakarak olculur.
Bu makinede 2087 dinlenmiyor, ama iddialarin hicbiri bunu VARSAYMIYOR: ister
basari ister basarisizlik olsun, yoklama kosarsa mtime degisir.
"""
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ortak_cfg   # gercek config.php yok edilmesin

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
IS = os.path.join(BURASI, "t_sslonbellek_is")
NL = chr(10)
gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-52s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s:%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, beklenen, NL, gelen))


# ── Onbellek dosyasinin yeri: URUNE sorulur, tahmin edilmez ────────────
# azTmp() dosyayi sys_get_temp_dir() altina 'az_ssl_cache_<kimlik>.json' diye
# koyuyor; kimlik Linux'ta uid, Windows'ta kurulum yolunun ozeti. Ikisini de
# kendimiz hesaplamak yerine PHP'nin kendi temp dizininde ariyoruz.
r = subprocess.run(["php", "-r", "echo sys_get_temp_dir();"],
                   capture_output=True, timeout=60, cwd=KOK)
if r.returncode:
    sys.exit("php hatasi: " + r.stderr.decode("utf-8", "replace")[:300])
TEMP = r.stdout.decode("utf-8", "replace").strip()
DESEN = os.path.join(TEMP, "az_ssl_cache_*.json")


def onbellek_sil():
    for y in glob.glob(DESEN):
        os.remove(y)


def onbellek_yolu():
    y = glob.glob(DESEN)
    return y[0] if len(y) == 1 else None


def onbellek_yaz(veri, yas_sn):
    """Onbellegi KUR: icerigi ve yasi verilen degerler olsun.

    Dosya adi URETILMEZ, urunun kendi yazdigi ad kullanilir (GERCEK_YOL):
    azTmp()'nin kimlik ekini test tarafinda hesaplamaya kalksaydik, urun
    baska bir dosyaya bakar ve butun iddialar sessizce anlamsizlasirdi.
    """
    for y in glob.glob(DESEN):
        if y != GERCEK_YOL:
            os.remove(y)
    io.open(GERCEK_YOL, "w", encoding="utf-8", newline=NL).write(json.dumps(veri))
    t = time.time() - yas_sn
    os.utime(GERCEK_YOL, (t, t))
    return GERCEK_YOL


taban = io.open(KOK + "demo/seed.snapshot", encoding="utf-8",
                errors="replace").read()


def render():
    shutil.rmtree(IS, ignore_errors=True)
    seed = os.path.join(IS, "seed")
    os.makedirs(seed)
    io.open(os.path.join(seed, ".proc_snapshot"), "w", encoding="utf-8",
            newline=NL).write(taban)
    ortak_cfg.yaz(KOK, seed)
    try:
        p = subprocess.run(["php", KOK + "src/index.php"],
                           capture_output=True, timeout=180, cwd=KOK)
    finally:
        ortak_cfg.geri(KOK)
        shutil.rmtree(IS, ignore_errors=True)
    if p.returncode:
        sys.exit("php hatasi: " + p.stderr.decode("utf-8", "replace")[:400])
    return p.stdout.decode("utf-8", "replace")


def bitis_satiri(govde):
    m = re.search(r'id="iv-ssl-sub"[^>]*>([^<]*)<', govde)
    return m.group(1).strip() if m else None


# ── 1) Yoklama sonucu HER DURUMDA yazilir ──────────────────────────────
onbellek_sil()
render()
yol = onbellek_yolu()
ck("yoklamadan sonra onbellek dosyasi olusuyor", yol is not None, True)
if yol is None:
    print()
    print("GECEN: %d  KALAN: %d" % (gecen, kalan + 1))
    sys.exit(1)
GERCEK_YOL = yol
if yol:
    d = json.loads(io.open(yol, encoding="utf-8").read())
    ck("kayitta 'ok' alani var (basari da basarisizlik da yazilir)",
       isinstance(d, dict) and "ok" in d, True)
    # Bu makinede 2087 dinlenmiyorsa ok=False bekleriz, ama iddia bunu
    # SARTA baglamaz: hangi sonuc yazildiysa o sonucun bicimi dogru olmali.
    if d.get("ok"):
        ck("basari kaydinda gun ve bitis tarihi var",
           ("days" in d) and ("expiry" in d), True)
    else:
        ck("basarisizlik kaydi deger uydurmuyor (gun/tarih yok)",
           ("days" not in d) and ("expiry" not in d), True)

# ── 2) TAZE basarisizlik kaydi varken yoklama yapilmaz ─────────────────
yol = onbellek_yaz({"ok": False}, 60)          # 60 sn < 300 sn
onceki = os.stat(yol).st_mtime
render()
ck("taze basarisizlik (60 sn): yoklama kosmuyor (mtime ayni)",
   os.stat(yol).st_mtime == onceki, True)
ck("taze basarisizlik: icerik korunuyor",
   json.loads(io.open(yol, encoding="utf-8").read()), {"ok": False})

# ── 3) Omru dolan basarisizlik kaydi yeniden yoklanir ──────────────────
yol = onbellek_yaz({"ok": False}, 600)         # 600 sn > 300 sn
onceki = os.stat(yol).st_mtime
render()
ck("bayat basarisizlik (600 sn): yeniden yoklaniyor (mtime degisti)",
   os.stat(yol).st_mtime != onceki, True)

# ── 4) Basari kaydi 6 saat yasar ve EKRANA cikar ───────────────────────
yol = onbellek_yaz({"ok": True, "days": 99, "expiry": "2099-03-04",
                    "issuer": "Let's Encrypt R3"}, 3600)
onceki = os.stat(yol).st_mtime
g = render()
ck("taze basari (1 saat): yoklama kosmuyor (mtime ayni)",
   os.stat(yol).st_mtime == onceki, True)
ck("taze basari: onbellekteki tarih ekrana basiliyor",
   bitis_satiri(g), "2099-03-04")

yol = onbellek_yaz({"ok": True, "days": 99, "expiry": "2099-03-04"}, 7 * 3600)
onceki = os.stat(yol).st_mtime
render()
ck("bayat basari (7 saat): yeniden yoklaniyor (mtime degisti)",
   os.stat(yol).st_mtime != onceki, True)

# ── 5) ESKI bicim ('ok' alani yok) hala basari sayilir ─────────────────
# Alan eklendiginde diskte zaten duran dosyalar var; onlar yalnizca basarida
# yazildigi icin basari kabul edilir. Yanlis tarafa dusseydi kullanimdaki her
# panonun onbellegi bir kerede gecersizlesir, hepsi yeniden yoklardi.
yol = onbellek_yaz({"days": 42, "expiry": "2098-07-09",
                    "issuer": "cPanel, Inc."}, 3600)
onceki = os.stat(yol).st_mtime
g = render()
ck("eski bicim (1 saat): hala gecerli, yoklama kosmuyor",
   os.stat(yol).st_mtime == onceki, True)
ck("eski bicim: tarihi ekrana basiliyor", bitis_satiri(g), "2098-07-09")

yol = onbellek_yaz({"days": 42, "expiry": "2098-07-09"}, 7 * 3600)
onceki = os.stat(yol).st_mtime
render()
ck("eski bicim (7 saat): omru dolmus, yeniden yoklaniyor",
   os.stat(yol).st_mtime != onceki, True)

onbellek_sil()
shutil.rmtree(IS, ignore_errors=True)
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
