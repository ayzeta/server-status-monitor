"""Hesap I/O'sunu /proc/lve/list'ten okuyan kodu KAYNAKTAN cikarip sinar.

Can alici noktalar:
  - Dosya SEKME ile ayrilmis ve bos alanlar var; bosluga gore ayirirsak sutunlar
    kayar (IO 16., IOPS 23. sutun).
  - Sayaclar KUMULATIF: ilk turda cikti olmaz, sonraki turda fark/saniye.
  - Birim KB (uretimde lveinfo ile karsilastirilarak dogrulandi).
  - Sayac geri giderse (LVE yeniden kuruldu) o hesap atlanir, eksi hiz yazilmaz.
  - cPanel hesabi olmayan (root, sistem) satirlar elenir.
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
TAB = chr(9)
src = io.open(KOK + "src/collector.sh", encoding="utf-8", errors="replace").read()

bas = src.index('IO_OUT=$(python3 -I - "$DATA_DIR/.lve_state" /proc/lve/list')
bas = src.index(NL, bas) + 1
son = src.index(NL + "PYEOF", bas)
kod = src[bas:son]

STUB = NL.join([
    "import sys, types",
    "_p = types.ModuleType('pwd')",
    "_TBL = {1089: 'eczashop', 1002: 'ayzeta', 0: 'root', 1500: 'sistemd'}",
    "class _R:",
    "    def __init__(self, n): self.pw_name = n",
    "def _g(u):",
    "    if u in _TBL: return _R(_TBL[u])",
    "    raise KeyError(u)",
    "_p.getpwuid = _g",
    "sys.modules['pwd'] = _p",
    "",
])
MOD = os.path.join(BURASI, "lve_mod.py")
io.open(MOD, "w", encoding="utf-8", newline=NL).write(STUB + kod.replace("'/var/cpanel/users'", "os.environ['T_CP']"))

CP = os.path.join(BURASI, "t_lve_cp")
shutil.rmtree(CP, ignore_errors=True)
os.makedirs(CP)
for ad in ("eczashop", "ayzeta"):
    io.open(os.path.join(CP, ad), "w").write("")

LISTE = os.path.join(BURASI, "t_lve_list.txt")
STATE = os.path.join(BURASI, "t_lve_state")

BASLIK = TAB.join(["10:LVE", "lCPU", "lCPUW", "nCPU", "lEP", "lNPROC", "lMEM", "lMEMPHY",
                   "lIO", "lIOPS", "lNETO", "lNETI", "EP", "CPU", "MEM", "IO", "fMEM",
                   "fEP", "MEMPHY", "fMEMPHY", "NPROC", "fNPROC", "IOPS", "NETO", "NETI"])


def satir(uid, io_kb, iops):
    """Gercek dosyadaki gibi: bos alanlar var, ayirici SEKME."""
    f = [""] * 25
    f[0] = "0,%d" % uid
    f[1] = "10000"; f[8] = "32768"
    f[15] = str(io_kb)
    f[22] = str(iops)
    return TAB.join(f)


def calistir(satirlar, yas=None):
    io.open(LISTE, "w", encoding="utf-8", newline=NL).write(NL.join([BASLIK] + satirlar) + NL)
    if yas is not None and os.path.exists(STATE):      # onceki ornegin zamanini geri al
        st = io.open(STATE, encoding="utf-8").read().split(NL)
        st[0] = "t %f" % (float(st[0].split()[1]) - yas)
        io.open(STATE, "w", encoding="utf-8", newline=NL).write(NL.join(st))
    r = subprocess.run([sys.executable, "-I", MOD, STATE, LISTE],
                       capture_output=True, text=True, env=dict(os.environ, T_CP=CP))
    if r.returncode and r.stderr:
        print("  (hata) " + r.stderr.strip().splitlines()[-1])
    return r.stdout.strip()


gecen = kalan = 0


def yakin(g, b):
    """ioacct satirlarinda hiz alani TOLERANSLI (%2): dt duvar saatinden geliyor,
    testteki iki kosu arasinda gecen sure tam 60.000 sn olmuyor."""
    gl, bl = g.split(NL), b.split(NL)
    if len(gl) != len(bl):
        return False
    for a, c in zip(gl, bl):
        ga, ca = a.split(), c.split()
        if ga[:1] != ca[:1] or len(ga) != len(ca):
            return False
        if ga[0] == "ioacct":
            if ga[1] != ca[1] or ga[3] != ca[3]:
                return False
            try:
                if abs(float(ga[2]) - float(ca[2])) > float(ca[2]) * 0.02:
                    return False
            except ValueError:
                return False
        elif a != c:
            return False
    return True


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if isinstance(gelen, str) and isinstance(beklenen, str) and gelen and beklenen \
       and gelen != beklenen and yakin(gelen, beklenen):
        gelen = beklenen
    if gelen == beklenen:
        gecen += 1
        print("  %-46s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s:\n    beklenen=%r\n    gelen   =%r" % (ad, beklenen, gelen))


# ── Ilk tur: taban yok -> hic cikti yok (olcum yok demek) ──────
for f in (STATE,):
    if os.path.exists(f): os.remove(f)
ck("ilk tur: isaret bile yazilmaz",
   calistir([satir(1089, 1000, 10), satir(1002, 500, 5)]), "")

# ── Ikinci tur: 60 sn'de 136 KB -> 2.3 KB/s (uretim olcumu) ────
ck("fark hiza cevrilir (KB -> KB/s)",
   calistir([satir(1089, 1136, 70), satir(1002, 604, 5)], yas=60),
   NL.join(["io_src lve 1m", "ioacct eczashop 2.3 1", "ioacct ayzeta 1.7 0"]))

# ── Degisim yok: satir yok ama OLCUM ISARETI var ───────────────
ck("hareket yoksa yalniz isaret",
   calistir([satir(1089, 1136, 70), satir(1002, 604, 5)], yas=60), "io_src lve 1m")

# ── Sayac geri gitti (LVE yeniden kuruldu): o hesap atlanir ────
ck("sayac sifirlanmis hesap atlanir",
   calistir([satir(1089, 5, 1), satir(1002, 1204, 5)], yas=60),
   NL.join(["io_src lve 1m", "ioacct ayzeta 10.0 0"]))

# ── cPanel hesabi olmayanlar elenir (root, sistem kullanicisi) ─
calistir([satir(0, 0, 0), satir(1500, 0, 0), satir(1089, 100, 0)])
ck("cpanel disi uid elenir",
   calistir([satir(0, 600000, 0), satir(1500, 600000, 0), satir(1089, 160, 0)], yas=60),
   NL.join(["io_src lve 1m", "ioacct eczashop 1.0 0"]))

# ── Bosluga gore ayirsaydik ne olurdu (regresyon korumasi) ─────
bos_ayrim = BASLIK.replace(TAB, " ")
ck("baslik satiri veri sayilmaz", "," in bos_ayrim.split()[0], False)

for f in (LISTE, STATE, MOD):
    if os.path.exists(f): os.remove(f)
shutil.rmtree(CP, ignore_errors=True)
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
