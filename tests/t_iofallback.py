"""Hesap I/O'sunun YEDEK yolu: CloudLinux olmayan sunucularda /proc/<pid>/io.

Neden ayri bir test: bu kod yalnizca LVE BULUNMAYAN makinelerde calisiyor.
Gelistirme ve uretim sunucusu CloudLinux oldugu icin burada bir sey bozulsa
kimse gormez — sessiz bozulma sinifi. Kaynaktan cikarilip sahte bir /proc
agaciyla kosuluyor.

Sinanan kararlar:
  - Ilk turda hicbir sey yazilmaz (kumulatif sayac bir dakikaya yazilamaz).
  - Hiz iki tur FARKINDAN gelir, bayt -> KB/s.
  - Ayni kullanicinin birden cok sureci TOPLANIR.
  - uid < 1000 (sistem kullanicilari) hic sayilmaz.
  - cPanel hesabi olmayan kullanici elenir.
  - Olcum yapildi isareti satir cikmasa bile yazilir ("yapan yok" != "olculemedi").
"""
import io
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
src = io.open(KOK + "src/collector.sh", encoding="utf-8", errors="replace").read()

# ── Yedek okuyucuyu KAYNAKTAN cikar ────────────────────────────
bas = src.index('IO_OUT=$(python3 -I - "$DATA_DIR/.io_state"')
bas = src.index(NL, bas) + 1
son = src.index(NL + "PYEOF", bas)
kod = src[bas:son]
# /proc ve /var/cpanel/users okumalarini sahte dizinlere yonlendir
kod = kod.replace("os.listdir('/proc')", "os.listdir(os.environ['T_PROC'])")
kod = kod.replace("'/proc/%s/status' % pid", "os.environ['T_PROC'] + '/%s/status' % pid")
kod = kod.replace("'/proc/%s/io' % pid", "os.environ['T_PROC'] + '/%s/io' % pid")
kod = kod.replace("'/var/cpanel/users'", "os.environ['T_CP']")

STUB = NL.join([
    "import sys, types",
    "_p = types.ModuleType('pwd')",
    "_TBL = {1001: 'alici', 1002: 'ayzeta', 1003: 'cpanelsuz', 500: 'sistem'}",
    "class _R:",
    "    def __init__(self, n): self.pw_name = n",
    "def _g(u):",
    "    if u in _TBL: return _R(_TBL[u])",
    "    raise KeyError(u)",
    "_p.getpwuid = _g",
    "sys.modules['pwd'] = _p",
    "",
])
MOD = os.path.join(BURASI, "iofb_mod.py")
io.open(MOD, "w", encoding="utf-8", newline=NL).write(STUB + kod)

TMP = os.path.join(BURASI, "t_iofb")
PROC = os.path.join(TMP, "proc")
CP = os.path.join(TMP, "cpanel")
STATE = os.path.join(TMP, "io_state")


def kur():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(PROC); os.makedirs(CP)
    for ad in ("alici", "ayzeta"):          # cpanelsuz BILEREK yok
        io.open(os.path.join(CP, ad), "w").write("")


def surec(pid, uid, rb, wb):
    d = os.path.join(PROC, str(pid))
    os.makedirs(d, exist_ok=True)
    io.open(os.path.join(d, "status"), "w").write(
        "Name:\ttest\nUid:\t%d\t%d\t%d\t%d\n" % (uid, uid, uid, uid))
    io.open(os.path.join(d, "io"), "w").write(
        "rchar: 1\nread_bytes: %d\nwrite_bytes: %d\n" % (rb, wb))


def tik(bekle=None):
    if bekle is not None and os.path.exists(STATE):
        st = io.open(STATE, encoding="utf-8").read().split(NL)
        st[0] = "t %f" % (float(st[0].split()[1]) - bekle)
        io.open(STATE, "w", encoding="utf-8", newline=NL).write(NL.join(st))
    r = subprocess.run([sys.executable, "-I", MOD, STATE], capture_output=True, text=True,
                       env=dict(os.environ, T_PROC=PROC, T_CP=CP))
    if r.returncode and r.stderr:
        print("  (hata) " + r.stderr.strip().splitlines()[-1])
    return r.stdout.strip()


gecen = kalan = 0


def ck(ad, gelen, beklenen, tolerans=False):
    global gecen, kalan
    tamam = gelen == beklenen
    if not tamam and tolerans:
        gl, bl = gelen.split(NL), beklenen.split(NL)
        tamam = len(gl) == len(bl)
        for a, b in zip(gl, bl):
            ga, gb = a.split(), b.split()
            if len(ga) != len(gb) or ga[0] != gb[0]:
                tamam = False; break
            if ga[0] == "ioacct":
                if ga[1] != gb[1] or abs(float(ga[2]) - float(gb[2])) > float(gb[2]) * 0.03:
                    tamam = False; break
            elif a != b:
                tamam = False; break
    if tamam:
        gecen += 1
        print("  %-48s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s:\n    beklenen=%r\n    gelen   =%r" % (ad, beklenen, gelen))


# ── Ilk tur: taban yok -> hic cikti yok ────────────────────────
kur()
surec(10, 1001, 0, 0)
ck("ilk tur: isaret bile yazilmaz", tik(), "")

# ── Ikinci tur: 60 sn'de 60 MB -> 1024 KB/s ────────────────────
surec(10, 1001, 0, 60 * 1024 * 1024)
ck("fark hiza cevrilir", tik(bekle=60),
   NL.join(["io_src proc 1m", "ioacct alici 1024.0 -"]), tolerans=True)

# ── Ayni kullanicinin iki sureci toplanir ──────────────────────
kur()
surec(10, 1002, 0, 0); surec(11, 1002, 0, 0)
tik()
surec(10, 1002, 30 * 1024 * 1024, 0); surec(11, 1002, 0, 30 * 1024 * 1024)
ck("ayni hesabin surecleri toplanir", tik(bekle=60),
   NL.join(["io_src proc 1m", "ioacct ayzeta 1024.0 -"]), tolerans=True)

# ── Sistem kullanicisi (uid<1000) sayilmaz ─────────────────────
kur()
surec(10, 500, 0, 0); surec(11, 1001, 0, 0)
tik()
surec(10, 500, 0, 600 * 1024 * 1024); surec(11, 1001, 0, 6 * 1024 * 1024)
ck("uid<1000 hic sayilmaz", tik(bekle=60),
   NL.join(["io_src proc 1m", "ioacct alici 102.4 -"]), tolerans=True)

# ── cPanel hesabi olmayan kullanici elenir ─────────────────────
kur()
surec(10, 1003, 0, 0); surec(11, 1001, 0, 0)
tik()
surec(10, 1003, 0, 600 * 1024 * 1024); surec(11, 1001, 0, 6 * 1024 * 1024)
ck("cpanel disi hesap elenir", tik(bekle=60),
   NL.join(["io_src proc 1m", "ioacct alici 102.4 -"]), tolerans=True)

# ── Hareket yoksa: satir yok ama OLCUM ISARETI var ─────────────
ck("hareket yoksa yalniz isaret", tik(bekle=60), "io_src proc 1m")

# ── Yeni gorulen hesap o turda sayilmaz (omur boyu sayac) ──────
surec(12, 1002, 0, 500 * 1024 * 1024)
ck("ilk gorulen hesap o turda yazilmaz", tik(bekle=60), "io_src proc 1m")

shutil.rmtree(TMP, ignore_errors=True)
os.remove(MOD)
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
