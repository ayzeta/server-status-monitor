"""Surec basina I/O olcumunu KAYNAKTAN cikarip sahte /proc ile sinar.

Can acmeco noktalar:
  - Ilk turda hicbir sey yazilmaz (omur boyu sayaci bir dakikaya yazilamaz).
  - Hiz iki olcum FARKINDAN gelir.
  - PID yeniden kullanimi yakalanir: biten surecin sayaci yenisine yazilmaz.
  - Bosluk iceren komut tek alana sikistirilir (satir bosluk ayirir).
"""
import io
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
src = io.open(KOK + "src/collector.sh", encoding='utf-8', errors='replace').read()

# Gomulu python'u cikar
bas = src.index("IOP_OUT=$(python3 - \"$IOP_STATE\" <<'PYEOF'")
bas = src.index(NL, bas) + 1
son = src.index(NL + "PYEOF", bas)
kod = src[bas:son]

# /proc okumasini sahte dizine yonlendir
kod = kod.replace('"/proc/%d/io" % pid', 'os.environ["T_PROC"] + "/%d/io" % pid')
io.open(os.path.join(BURASI, "ioproc_mod.py"), "w", encoding="utf-8", newline=NL).write(kod)

TMP = os.path.join(BURASI, "t_ioproc")
PROC = os.path.join(TMP, "proc")
STATE = os.path.join(TMP, "state")


def kur():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(PROC)


def surec(pid, etimes, user, komut, rb, wb):
    d = os.path.join(PROC, str(pid))
    os.makedirs(d, exist_ok=True)
    io.open(os.path.join(d, "io"), "w").write(
        "rchar: 1\nread_bytes: %d\nwrite_bytes: %d\n" % (rb, wb))
    return "%d %d %s %s" % (pid, etimes, user, komut)


def tik(satirlar, bekle=None):
    io.open(STATE + ".ps", "w", encoding="utf-8", newline=NL).write(
        NL.join(satirlar) + NL)
    if bekle is not None:                      # onceki ornegin zamanini geri al
        st = io.open(STATE, encoding="utf-8").read().split(NL)
        st[0] = "t %f" % (float(st[0].split()[1]) - bekle)
        io.open(STATE, "w", encoding="utf-8", newline=NL).write(NL.join(st))
    r = subprocess.run([sys.executable, os.path.join(BURASI, "ioproc_mod.py"), STATE],
                       capture_output=True, text=True,
                       env=dict(os.environ, T_PROC=PROC))
    # Ilk satir "olcum yapildi" isareti: taban varsa HER TURDA yazilir, satir
    # cikmasa bile ("yapan yok" ile "olculemedi" kartta ayri cumleler).
    satirlar = r.stdout.strip().split(NL) if r.stdout.strip() else []
    global isaret
    isaret = satirlar[0] if satirlar else ""
    return NL.join(satirlar[1:]) if satirlar else ""


gecen = kalan = 0
isaret = ""


def ck(ad, gelen, beklenen):
    """Hiz alani TOLERANSLI karsilastirilir (%5): dt duvar saatinden geliyor ve
    testteki iki kosu arasinda gecen sure makinenin o anki yukune gore degisiyor
    (yuklu makinede %2-3 sapma gorduk). Kullanici, PID ve komut birebir."""
    global gecen, kalan
    tamam = gelen == beklenen
    if not tamam and isinstance(gelen, str) and isinstance(beklenen, str):
        # Alanlar: ioproc PID KULLANICI KBPS KOMUT
        g, b = gelen.split(), beklenen.split()
        if (len(g) == len(b) == 5 and g[0] == b[0] and g[1] == b[1]
                and g[2] == b[2] and g[4] == b[4]):
            try:
                tamam = abs(float(g[3]) - float(b[3])) <= float(b[3]) * 0.05
            except ValueError:
                tamam = False
    if tamam:
        gecen += 1
        print("  %-46s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s:\n    beklenen=%r\n    gelen   =%r" % (ad, beklenen, gelen))


# ── Ilk tur: taban yok, cikti yok ──────────────────────────────
kur()
ck("ilk tur: hicbir sey yazilmaz",
   tik([surec(100, 500, "mysql", "/usr/sbin/mariadbd", 0, 0)]), "")

# ── Ikinci tur: 60 sn'de 60 MB yazildi -> 1024 KB/s ───────────
ck("fark hiza cevrilir",
   tik([surec(100, 560, "mysql", "/usr/sbin/mariadbd", 0, 60 * 1024 * 1024)], bekle=60),
   "ioproc 100 mysql 1024.0 /usr/sbin/mariadbd")

# ── Degisim yoksa listeye girmez ───────────────────────────────
ck("I/O yapmayan surec listelenmez",
   tik([surec(100, 620, "mysql", "/usr/sbin/mariadbd", 0, 60 * 1024 * 1024)], bekle=60), "")

# ── PID yeniden kullanimi: yas kuculmus -> atlanir ─────────────
kur()
tik([surec(100, 500, "root", "/eski/surec", 0, 10 * 1024 * 1024 * 1024)])
ck("pid yeniden kullanildi: ucuk hiz YAZILMAZ",
   tik([surec(100, 3, "nobody", "/yeni/surec", 0, 0)], bekle=60), "")

# ── Bosluklu komut tek alana sikisir ───────────────────────────
kur()
tik([surec(7, 500, "root", "/usr/bin/perl -w /script.pl", 0, 0)])
ck("bosluklu komut tek alan",
   tik([surec(7, 560, "root", "/usr/bin/perl -w /script.pl", 0, 10 * 1024 * 1024)],
       bekle=60),
   "ioproc 7 root 170.7 /usr/bin/perl_-w_/script.pl")

# ── Siralama: buyukten kucuge ──────────────────────────────────
kur()
tik([surec(1, 500, "a", "az", 0, 0), surec(2, 500, "b", "cok", 0, 0)])
cikti = tik([surec(1, 560, "a", "az", 0, 1 * 1024 * 1024),
             surec(2, 560, "b", "cok", 0, 50 * 1024 * 1024)], bekle=60)
ck("en cok I/O yapan basta", cikti.split(NL)[0].split()[2], "b")
ck("olcum isareti satiri", isaret, "ioproc_ok 1m")
ck("iki satir da var", len(cikti.split(NL)), 2)
# PID alani: 2. alan ve SURECIN KENDI pid'i (b sureci pid=2)
ck("pid satirda tasiniyor", cikti.split(NL)[0].split()[1], "2")

shutil.rmtree(TMP, ignore_errors=True)
os.remove(os.path.join(BURASI, "ioproc_mod.py"))
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
