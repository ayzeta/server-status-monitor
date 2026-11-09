"""Hesap I/O'sunu /proc/lve/list'ten okuyan kodu KAYNAKTAN cikarip sinar.

Can acmeco noktalar:
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
import time

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
    # 2000-2019: ilk 15 kesmesini asmak icin yirmi hesap (toplam testi).
    "_TBL = {1089: 'pixelcart', 1002: 'ayzeta', 0: 'root', 1500: 'sistemd'}",
    "_TBL.update({2000 + i: 'hesap%02d' % i for i in range(20)})",
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
for ad in ("pixelcart", "ayzeta"):
    io.open(os.path.join(CP, ad), "w").write("")
for i in range(20):
    io.open(os.path.join(CP, "hesap%02d" % i), "w").write("")

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
        # PENCERE SIMDIDEN geri alinir, onceki damgadan DEGIL. Eskiden
        # dt = 300 + (onceki alt surecin suresi) oluyordu; yuzde kil payi
        # asagi kayip 118.4 yerine 118.3 yaziyordu ve iddia 118.4 bekledigi
        # icin test ARADA BIR dusuyordu. Simdi sapma yalnizca python acilisi.
        st[0] = "t %f" % (time.time() - yas)
        io.open(STATE, "w", encoding="utf-8", newline=NL).write(NL.join(st))
    r = subprocess.run([sys.executable, "-I", MOD, STATE, LISTE],
                       capture_output=True, text=True, env=dict(os.environ, T_CP=CP))
    if r.returncode and r.stderr:
        print("  (hata) " + r.stderr.strip().splitlines()[-1])
    return r.stdout.strip()


gecen = kalan = 0


def yakin(g, b):
    """ioacct satirlarinda hiz alani TOLERANSLI (%2): dt duvar saatinden geliyor,
    testteki iki kosu arasinda gecen sure tam yas saniye olmuyor.

    PENCERE 300 SANIYE, 60 DEGIL (2026-11-08). Olcumun uzerine makinenin kendi
    gecikmesi biniyor; 60 saniyelik pencerede 2 saniyelik gecikme %3,3 agirlik
    tasiyor ve 136/60=2,27 ("2.3") degeri 136/62=2,19 ("2.2") oluyordu -- test
    URUN DOGRUYKEN kirmizi yaniyordu, ama yalnizca TAKIM YUKU altinda, tek
    basina kosunca geciyordu. Boyle bir test kirmizinin anlamini bitiriyor.
    Pencere bes katina cikinca ayni gecikme %0,7'ye dusuyor. Daha uzuna
    cikilamaz: urunun kendi tavani 600 sn ("now - pt > 600" ise olcum YOK
    sayiliyor), 600 secilseydi gecikmeyle birlikte tavani asip hic cikti
    vermiyordu -- denendi. Beklenen hizlar degismesin diye hem IO hem IOPS
    sayac farklari da bes katina cikarildi."""
    gl, bl = g.split(NL), b.split(NL)
    if len(gl) != len(bl):
        return False
    for a, c in zip(gl, bl):
        ga, ca = a.split(), c.split()
        if ga[:1] != ca[:1] or len(ga) != len(ca):
            return False
        # ioacct hizi ve lvecpu yuzdesi dt'ye bagli -> TOLERANSLI.
        # lveram ANLIK deger (dt'ye bagli degil) -> TAM esitlik beklenir.
        if ga[0] == "lvecpu_tot":
            # Toplam da dt'ye bagli -> toleransli; hesap SAYISI tam esit.
            if ga[2] != ca[2]:
                return False
            try:
                if abs(float(ga[1]) - float(ca[1])) > float(ca[1]) * 0.02:
                    return False
            except ValueError:
                return False
        elif ga[0] in ("ioacct", "lvecpu"):
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
   calistir([satir(1089, 1680, 310), satir(1002, 1020, 5)], yas=300),
   NL.join(["io_src lve 1m", "ioacct pixelcart 2.3 1 32768", "ioacct ayzeta 1.7 0 32768"]))

# ── Degisim yok: satir yok ama OLCUM ISARETI var ───────────────
ck("hareket yoksa yalniz isaret",
   calistir([satir(1089, 1680, 310), satir(1002, 1020, 5)], yas=300), "io_src lve 1m")

# ── Sayac geri gitti (LVE yeniden kuruldu): o hesap atlanir ────
ck("sayac sifirlanmis hesap atlanir",
   calistir([satir(1089, 5, 1), satir(1002, 4020, 5)], yas=300),
   NL.join(["io_src lve 1m", "ioacct ayzeta 10.0 0 32768"]))

# ── cPanel hesabi olmayanlar elenir (root, sistem kullanicisi) ─
calistir([satir(0, 0, 0), satir(1500, 0, 0), satir(1089, 100, 0)])
ck("cpanel disi uid elenir",
   calistir([satir(0, 600000, 0), satir(1500, 600000, 0), satir(1089, 400, 0)], yas=300),
   NL.join(["io_src lve 1m", "ioacct pixelcart 1.0 0 32768"]))

# ── Bosluga gore ayirsaydik ne olurdu (regresyon korumasi) ─────
bos_ayrim = BASLIK.replace(TAB, " ")
ck("baslik satiri veri sayilmaz", "," in bos_ayrim.split()[0], False)

# ── TARIHCE 15. KOLONU (TOPIO): "hesap:kbps" ───────────────────
# Kural KAYNAKTAN cikarilir ve YUKARIDAKI kodun KENDI CIKTISIYLA beslenir --
# elle yazilmis bir dizgiyle degil. Sebebi olculmus bir regresyon: kural
# 'NR==1 && $1=="ioacct"' idi, 2026-10-23'te ciktinin basina "io_src lve 1m"
# olcum isareti eklenince hesap satirlari ikinciye kaydi ve kural 16 gun
# boyunca hep BOS dondu. Hata vermedi: 15. kolon '-' yazildi, sayfa acilisinda
# gecmisten kurulan yuk uyarilari I/O failini hic tasimadi, I/O bekleme uyarisi
# da CPU failine dustu (uretimde goruldu 2026-11-08). Test yoktu.
TOPIO_AWK = src[src.index("TOPIO=$(printf"):].split("awk '", 1)[1].split("')", 1)[0]


def topio(ciktisi):
    r = subprocess.run(["awk", TOPIO_AWK], input=ciktisi + NL,
                       capture_output=True, text=True)
    return r.stdout.strip()


# Hiz alani SINANMAZ: dt duvar saatinden geliyor (bkz. yakin()), sayac da
# kumulatif oldugu icin onceki ornekten tasiyor. Regresyonun konusu zaten hiz
# degil: kolon DOLUYOR MU ve DOGRU HESABI mi yaziyor.
# Bicim "deger::hesap" (1.5.68): oteki iki kolonla ayni siralama
# ("deger:hesap:ad:betik"), ortadaki alan bos cunku burada ayri bir sahip yok --
# adin kendisi hesap. Geriye donuk: 1.5.67'ye kadar "hesap:kbps" idi.
def topio_ad(c):
    p = topio(c).split(":")
    return (p[2] if len(p) > 2 else "",
            len(p) == 3 and p[1] == "" and p[0].isdigit() and int(p[0]) > 0)


ck("kural isaret satirini veri sanmiyor", TOPIO_AWK.startswith("NR==1"), False)
ck("en cok I/O yapan hesap yazilir",
   topio_ad(calistir([satir(1089, 2272, 70), satir(1002, 604, 5)], yas=300)),
   ("pixelcart", True))
# Sabit bir hesaba degil, SIRAYA bakiyor: bu turda artisi buyuk olan ayzeta,
# yani bir onceki iddiada kazanan pixelcart degil.
ck("en buyugu alir (sabit hesap degil)",
   topio_ad(calistir([satir(1089, 8272, 70), satir(1002, 99999, 5)], yas=300)),
   ("ayzeta", True))
ck("hareket yoksa kolon bos kalir", topio("io_src lve 1m"), "")

# ══ HESAP BASINA CPU ve RAM (1.5.75) ═══════════════════════════════════
# AYNI dosyadan, AYNI turda okunuyor: ek tarama yok. Iki sayacin TABIATI
# farkli ve kod bunu ayri ele almak zorunda:
#   CPU (14. sutun)    -> KUMULATIF NANOSANIYE, fark alinir (I/O gibi).
#   MEMPHY (19. sutun) -> ANLIK SAYFA sayisi, fark ALINMAZ.
# Birimler uretimde olculdu (lin, 2026-11-08): f[13] 60 saniyede 7879976103
# artti, yani bir cekirdegin %13,1'i; mikrosaniye olsaydi %13133 (131 cekirdek)
# cikardi. dt=300 sn oldugu icin burada yuzde = fark / 3e9.
C0 = 116566380513598          # uretimdeki mertebe (sayac acilistan beri biriktiriyor)
SAYFA_MB = 256                # 4 KB sayfa -> 1 MB = 256 sayfa


def satir_tam(uid, io_kb, iops, cpu_ns, mem_sayfa, nproc):
    """satir() ile ayni, ayrica CPU/MEMPHY/NPROC alanlari DOLU."""
    f = [""] * 25
    f[0] = "0,%d" % uid
    f[1] = "10000"; f[8] = "32768"
    f[13] = str(cpu_ns); f[15] = str(io_kb); f[18] = str(mem_sayfa)
    f[20] = str(nproc); f[22] = str(iops)
    return TAB.join(f)


if os.path.exists(STATE): os.remove(STATE)
# I/O farki BILEREK sifir: boylece beklenen cikti yalniz CPU/RAM satirlarindan
# olusuyor ve iddia okunur kaliyor.
calistir([satir_tam(1089, 1000, 10, C0, 2841 * SAYFA_MB, 42),
          satir_tam(1002, 1000, 10, C0, 486 * SAYFA_MB, 7)])
ck("CPU kumulatif: ilk turda satir yok",
   calistir([satir_tam(1089, 1000, 10, C0 + 355200000000, 2841 * SAYFA_MB, 42),
             satir_tam(1002, 1000, 10, C0 + 55800000000, 486 * SAYFA_MB, 7)], yas=300),
   NL.join(["io_src lve 1m", "lve_ok 1m", "lvecpu_tot 137.0 2",
            "lvecpu pixelcart 118.4 42 100", "lvecpu ayzeta 18.6 7 100",
            "lveram_tot 3327.0 2",
            "lveram pixelcart 2841.0 42 -1", "lveram ayzeta 486.0 7 -1"]))

# CPU ve RAM AYRI siralanir: ayzeta CPU'da ikinci, RAM'de birinci olmali.
ck("iki liste bagimsiz siralanir",
   calistir([satir_tam(1089, 1000, 10, C0 + 710400000000, 500 * SAYFA_MB, 42),
             satir_tam(1002, 1000, 10, C0 + 111600000000, 9000 * SAYFA_MB, 7)], yas=300),
   NL.join(["io_src lve 1m", "lve_ok 1m", "lvecpu_tot 137.0 2",
            "lvecpu pixelcart 118.4 42 100", "lvecpu ayzeta 18.6 7 100",
            "lveram_tot 9500.0 2",
            "lveram ayzeta 9000.0 7 -1", "lveram pixelcart 500.0 42 -1"]))

# ── TOPLAM, ILK 15 KESMESINDEN ETKILENMEZ ──────────────────────────────
# Panodaki "hesaplar %X" satirinin BUTUN anlami bu: listede 15 hesap gorunse
# de toplam hepsini sayar. 20 hesap, her biri ayni yuku basiyor.
if os.path.exists(STATE): os.remove(STATE)
YIRMI_0 = [satir_tam(2000 + i, 1000, 10, C0, 100 * SAYFA_MB, 3) for i in range(20)]
YIRMI_1 = [satir_tam(2000 + i, 1000, 10, C0 + 30000000000, 100 * SAYFA_MB, 3)
           for i in range(20)]
calistir(YIRMI_0)
yirmi = calistir(YIRMI_1, yas=300).split(NL)
tot = [s for s in yirmi if s.startswith("lvecpu_tot ")]
ck("20 hesap varken liste 15'te kesilir",
   len([s for s in yirmi if s.startswith("lvecpu ")]), 15)
ck("toplam satiri bir tane", len(tot), 1)
ck("toplam BUTUN hesaplari sayar (20, 15 degil)", tot[0].split()[2], "20")
ck("toplam = 20 x %10 = %200 (tek cekirdek yuzdesi)",
   abs(float(tot[0].split()[1]) - 200.0) <= 200.0 * 0.02, True)
ck("toplam satiri listeden ONCE gelir",
   yirmi.index(tot[0]) < min(i for i, s in enumerate(yirmi) if s.startswith("lvecpu ")), True)
# RAM TOPLAMI DA AYNI KURALA TABI: her hesap 100 MB tutuyor, liste 15'te kesilir
# ama toplam 20 hesabi ve 2000 MB'i gostermek zorunda.
rtot = [s for s in yirmi if s.startswith("lveram_tot ")]
ck("RAM listesi de 15'te kesilir",
   len([s for s in yirmi if s.startswith("lveram ")]), 15)
ck("RAM toplami BUTUN hesaplari sayar", (len(rtot), rtot[0].split()[2]), (1, "20"))
ck("RAM toplami = 20 x 100 MB", rtot[0].split()[1], "2000.0")
ck("RAM toplami RAM listesinden ONCE gelir",
   yirmi.index(rtot[0]) < min(i for i, s in enumerate(yirmi) if s.startswith("lveram ")), True)

# ── BOS ALAN: I/O OLCUMU KAYBOLMAMALI ──────────────────────────────────
# Bu dosyada bos alanlar var (tab duruyor, deger yok). CPU/MEMPHY ayni try
# blogunda okunsaydi bos bir alan satirin TAMAMINI dusurur ve 16 gun sessizce
# calisan I/O olcumunu de gotururdu. satir() zaten bu alanlari bos biraktigi
# icin fikstur gerceginin ta kendisi.
if os.path.exists(STATE): os.remove(STATE)
calistir([satir(1089, 1000, 10), satir_tam(1002, 1000, 10, C0, 486 * SAYFA_MB, 7)])
ck("CPU alani bos olan hesabin I/O'su yine okunur",
   calistir([satir(1089, 1900, 10),
             satir_tam(1002, 1000, 10, C0 + 55800000000, 486 * SAYFA_MB, 7)], yas=300),
   NL.join(["io_src lve 1m", "ioacct pixelcart 3.0 0 32768", "lve_ok 1m",
            "lvecpu_tot 18.6 1", "lvecpu ayzeta 18.6 7 100",
            "lveram_tot 486.0 1", "lveram ayzeta 486.0 7 -1"]))

# ── CPU sayaci geri gitti (LVE yeniden kuruldu) ─────────────────────────
if os.path.exists(STATE): os.remove(STATE)
calistir([satir_tam(1089, 1000, 10, C0, 2841 * SAYFA_MB, 42),
          satir_tam(1002, 1000, 10, C0, 486 * SAYFA_MB, 7)])
# RAM SATIRI YINE YAZILIR: MEMPHY anlik deger, CPU sayacinin sifirlanmasiyla
# ilgisi yok. (Bu iddia once "ikisi de dusmeli" diye yazilmisti; urun dogruydu.)
ck("CPU sayaci sifirlanan hesabin CPU'su dusurulur, RAM'i kalir",
   calistir([satir_tam(1089, 1000, 10, 5, 2841 * SAYFA_MB, 42),
             satir_tam(1002, 1000, 10, C0 + 55800000000, 486 * SAYFA_MB, 7)], yas=300),
   # TOPLAM da sifirlanan hesabi SAYMAZ: liste neyi gosteriyorsa toplam da
   # onu sayiyor, yani ikisi tutarli (1 hesap, %18,6).
   NL.join(["io_src lve 1m", "lve_ok 1m", "lvecpu_tot 18.6 1",
            "lvecpu ayzeta 18.6 7 100",
            # RAM TOPLAMI IKI HESABI DA SAYAR: CPU sayacinin sifirlanmasi
            # MEMPHY'yi dusurmez (anlik deger), yani RAM listesi de toplami da
            # iki satirli kalir -- CPU tarafiyla ayni kumede OLMAMASI olagan.
            "lveram_tot 3327.0 2",
            "lveram pixelcart 2841.0 42 -1", "lveram ayzeta 486.0 7 -1"]))

# ── ESKI DURUM DOSYASI (3 alan, CPU'suz) ───────────────────────────────
# Guncellemeden sonraki ILK turda diskteki .lve_state onceki toplayicinin
# yazdigi hal olur. O turda CPU UYDURULMAZ: satir hic yazilmaz. I/O ve RAM ise
# calisir -- RAM'in taban ornege ihtiyaci yok (anlik deger).
if os.path.exists(STATE): os.remove(STATE)
calistir([satir_tam(1089, 1000, 10, C0, 2841 * SAYFA_MB, 42)])
_st = io.open(STATE, encoding="utf-8").read().split(NL)
io.open(STATE, "w", encoding="utf-8", newline=NL).write(
    NL.join([_st[0]] + [" ".join(l.split()[:3]) for l in _st[1:] if l.strip()]) + NL)
ck("eski durum dosyasi: CPU satiri yok, I/O ve RAM calisir",
   calistir([satir_tam(1089, 1900, 10, C0 + 355200000000, 2841 * SAYFA_MB, 42)], yas=300),
   NL.join(["io_src lve 1m", "ioacct pixelcart 3.0 0 32768", "lve_ok 1m",
            "lveram_tot 2841.0 1", "lveram pixelcart 2841.0 42 -1"]))

# ── URETIMDEN ALINMIS GERCEK SATIR ─────────────────────────────────────
# Asagidaki satir lin'den (2026-11-08) alinan bir hesap satirinin AYNISI;
# yalnizca uid kurgusal. Onemli olan ALAN DIZILIMI: 25 isimden UCU -- fMEMPHY,
# NPROC, fNPROC -- BOS geliyor, CPU ve IO ise dolu. (Hizalama IO ile
# dogrulaniyor: 16. sutun 3460817234152, yani urunun zaten uretimde
# dogrulanmis f[15]'i.)
#
# Bu satir olmadan test kendi varsayimimi dogrulardi: once uc alani TEK try
# icinde okuyordu ve boyle bir satirda hesabin CPU'su da RAM'i de sessizce
# dusuyordu. Satiri gercekten gorunce kural degisti.
GERCEK = [
    "0,%d", "10000", "100", "1", "20", "100", "0", "262144", "32768", "8192",
    "0", "0", "1", "%d", "0", "3460817234152", "0", "1", "%d", "", "", "",
    "99389", "13477401992", "22654854626",
]


def satir_gercek(uid, cpu_ns, memphy):
    f = list(GERCEK)
    f[0] = f[0] % uid; f[13] = f[13] % cpu_ns; f[18] = f[18] % memphy
    return TAB.join(f)


ck("gercek satir 25 alan, ucu bos", (len(GERCEK), sum(1 for x in GERCEK if x == "")), (25, 3))
if os.path.exists(STATE): os.remove(STATE)
calistir([satir_gercek(1089, C0, 0)])
ck("gercek satir: NPROC bos olsa da CPU yazilir (MEMPHY 0 -> RAM satiri yok)",
   calistir([satir_gercek(1089, C0 + 355200000000, 0)], yas=300),
   # MEMPHY 0 -> hesap RAM LISTESINDE yok (0 gosterilmez) ama TOPLAMDA sayilir:
   # "olctuk, 0 cikti" ile "olcemedik" ayri seyler. Alan BOS gelirse (uretimdeki
   # hal) hesap ikisine de girmez -- asagidaki gercek satir testi bunu gosteriyor.
   # NPROC ALANI BOS -> '-1', yani "LVE BILDIRMEDI". Sifirla ayni sey DEGIL:
   # olculdu 2026-11-09 (lin, 399 satir) NPROC hic bos gelmemis ama 121 hesap
   # gercekten 0 demis. Ikisi 0'a indirilirse pano gercek bir olcumu (surec
   # yok) "bildirilmedi" diye gizliyor. Bu fikstur alanin BOS da gelebildigini
   # gosteren uretim ornegi (2026-11-08).
   NL.join(["io_src lve 1m", "lve_ok 1m", "lvecpu_tot 118.4 1",
            "lvecpu pixelcart 118.4 -1 100", "lveram_tot 0.0 1"]))

if os.path.exists(STATE): os.remove(STATE)
calistir([satir_gercek(1089, C0, 2841 * SAYFA_MB)])
ck("ayni satir MEMPHY dolu olunca RAM de yazilir",
   calistir([satir_gercek(1089, C0 + 355200000000, 2841 * SAYFA_MB)], yas=300),
   NL.join(["io_src lve 1m", "lve_ok 1m", "lvecpu_tot 118.4 1",
            "lvecpu pixelcart 118.4 -1 100",
            "lveram_tot 2841.0 1", "lveram pixelcart 2841.0 -1 1024"]))

# ── TAVANLAR: HAM SAYI DEGIL, OLCULMUS BIRIM ───────────────────────────
# Tavanlar hesabin KENDI satirinda geliyor (2=lCPU 6=lNPROC 8=lMEMPHY 9=lIO)
# ve pano onlari doluluk cubugu icin kullaniyor. Sunucu varsayilani YOK:
# limit WHM paketine ve hesaba gore degisir.
#
# BIRIMLER URETIMDE OLCULDU 2026-11-09 (lin, uid 1254), her biri IKINCI bir
# programla dogrulandi:
#   lCPU=10000      <-> "lvectl list" SPEED=100   => yuzde = lCPU / 100
#   lMEMPHY=262144  <-> lvectl PMEM 1024M         => 4 KB sayfa
#   lIO=32768       <-> lveinfo "32.0 MB/s"       => KB/s (cevrim yok)
#
# lCPU'yu HAM haliyle yuzde sanmak sessiz bir yalan olurdu: o hesap o sirada
# tavana YAPISMISTI (lve-read-snapshot: cpu_fault>0) ve pano 99/10000, yani
# "%1 dolu" derdi. Hicbir yerde hata vermez, sadece yanlis olurdu.
if os.path.exists(STATE): os.remove(STATE)
calistir([satir_gercek(1089, C0, 2841 * SAYFA_MB)])
_tav = calistir([satir_gercek(1089, C0 + 355200000000, 2841 * SAYFA_MB)], yas=300)


def _son(cikti, bas):
    for l in cikti.split(NL):
        if l.startswith(bas):
            return l.split()[-1]
    return "(satir yok)"


ck("CPU tavani ham 10000 degil, yuzde 100", _son(_tav, "lvecpu "), "100")
ck("RAM tavani sayfa degil MB (262144 x 4K)", _son(_tav, "lveram "), "1024")


def satir_tavanli(uid, cpu_ns, memphy, lcpu, lmemphy):
    """GERCEK satirin aynisi, yalnizca TAVAN alanlari degistirilmis."""
    f = list(GERCEK)
    f[0] = f[0] % uid; f[13] = f[13] % cpu_ns; f[18] = f[18] % memphy
    f[1] = lcpu; f[7] = lmemphy
    return TAB.join(f)


# "SINIRSIZ" (0) ile "BILDIRILMEDI" (bos) AYRI SEY: NPROC'ta ogrenilen dersin
# aynisi. Ikisinde de cubuk cizilmez ama ipucu ayni seyi soyleyemez.
if os.path.exists(STATE): os.remove(STATE)
calistir([satir_tavanli(1089, C0, 2841 * SAYFA_MB, "", "")])
_bos = calistir([satir_tavanli(1089, C0 + 355200000000, 2841 * SAYFA_MB, "", "")], yas=300)
ck("tavan alani BOS -> -1 (LVE bildirmedi)",
   (_son(_bos, "lvecpu "), _son(_bos, "lveram ")), ("-1", "-1"))

if os.path.exists(STATE): os.remove(STATE)
calistir([satir_tavanli(1089, C0, 2841 * SAYFA_MB, "0", "0")])
_sif = calistir([satir_tavanli(1089, C0 + 355200000000, 2841 * SAYFA_MB, "0", "0")], yas=300)
ck("tavan 0 -> 0 (sinirsiz), -1'e cevrilmez",
   (_son(_sif, "lvecpu "), _son(_sif, "lveram ")), ("0", "0"))

# ── TARIHCE 17. KOLONU (TOPCPUA): "pct::hesap" ─────────────────────────
# TOPIO'nun birebir esi ve ayni yontemle sinaniyor: kural KAYNAKTAN cikariliyor
# ve YUKARIDAKI kodun KENDI CIKTISIYLA besleniyor -- elle yazilmis dizgiyle
# degil. TOPIO'da tam bu yuzden 16 gunluk sessiz bir regresyon yasandi.
TOPCPUA_AWK = src[src.index("TOPCPUA=$(printf"):].split("awk '", 1)[1].split("')", 1)[0]


def topcpua(ciktisi):
    r = subprocess.run(["awk", TOPCPUA_AWK], input=ciktisi + NL,
                       capture_output=True, text=True)
    return r.stdout.strip()


if os.path.exists(STATE): os.remove(STATE)
calistir([satir_tam(1089, 1000, 10, C0, 2841 * SAYFA_MB, 42),
          satir_tam(1002, 1000, 10, C0, 486 * SAYFA_MB, 7)])
_c = calistir([satir_tam(1089, 1000, 10, C0 + 355200000000, 2841 * SAYFA_MB, 42),
               satir_tam(1002, 1000, 10, C0 + 55800000000, 486 * SAYFA_MB, 7)], yas=300)
_t = topcpua(_c).split(":")
# Bu cikti ZATEN 'lvecpu_tot' satiriyla basliyor ve o satir lvecpu'lardan ONCE
# geliyor: kural '^lvecpu' gibi gevsek olsaydi TOPLAMI hesap sanip ilk eslesmede
# cikardi. Asagidaki ad iddiasi o tuzagi da kapatiyor.
ck("en cok CPU yakan hesap yazilir", _t[2] if len(_t) > 2 else "", "pixelcart")
ck("bicim 'pct::hesap': ortadaki alan bos, deger TAM SAYI",
   (len(_t), _t[1], _t[0].isdigit()), (3, "", True))
ck("kural isaret satirini veri sanmiyor", TOPCPUA_AWK.startswith("NR==1"), False)
# ESIK 0,5: altinda kalan hesap int()+0.5 ile "0" olur ve satir "hesap X %0"
# derdi -- olculen seyi yanlis anlatan bir sayi. Satirin BICIMI gercek ciktidan
# aliniyor, yalnizca sayi degistiriliyor (esik bizim kuralimiz).
_ad = [s for s in _c.split(NL) if s.startswith("lvecpu ")][0].split()[1]
ck("0,5 altindaki hesap hic yazilmaz",
   topcpua(NL.join(["io_src lve 1m", "lve_ok 1m", "lvecpu %s 0.4 3" % _ad])), "")
ck("0,5 ve ustu yazilir (yuvarlanarak)",
   topcpua(NL.join(["io_src lve 1m", "lve_ok 1m", "lvecpu %s 0.5 3" % _ad])),
   "1::" + _ad)

# ── BOLUMLERE AYIRMA (kabuk tarafi) ────────────────────────────────────
# Tek python turunun ciktisi IKI bolume bolunuyor: I/O satirlari "Top IO
# accounts"a, CPU/RAM satirlari "LVE per account"a. Panonun ayristiricisi bolum
# basligina baktigi icin yanlis suzgec sessizce ya I/O bolumunu kirletir ya da
# LVE bolumunu bos birakir. Suzgecler KAYNAKTAN cikariliyor.
_io_suzgec = src[src.index('printf \'%s\\n\' "$IO_OUT" | grep -v'):].split(NL, 1)[0]
_lve_suzgec = src[src.index('printf \'%s\\n\' "$IO_OUT" | grep \''):].split(NL, 1)[0]
_ornek = NL.join(["io_src lve 1m", "ioacct pixelcart 2.3 1 32768", "lve_ok 1m",
                  "lvecpu_tot 118.4 1", "lvecpu pixelcart 118.4 42 100",
                  "lveram_tot 2841.0 1", "lveram pixelcart 2841.0 42 -1"])


def suz(satir_kodu):
    kod = satir_kodu.split("|", 1)[1].strip()        # "grep ..." kismi
    r = subprocess.run(["bash", "-c", kod], input=_ornek + NL,
                       capture_output=True, text=True)
    return r.stdout.strip()


ck("I/O bolumune CPU/RAM satiri karismaz", suz(_io_suzgec),
   NL.join(["io_src lve 1m", "ioacct pixelcart 2.3 1 32768"]))
# TOPLAM SATIRLARI DA BU SUZGECTEN GECMEK ZORUNDA: '^lve' onlari da aliyor, yani
# yeni bir toplam eklemek kabuk tarafinda degisiklik GEREKTIRMIYOR -- ama bunu
# varsaymak yerine burada sinaniyor, cunku suzgec daralirsa ozet satiri sessizce
# kaybolur ve panoda yalnizca satir hic cizilmez (hata vermez).
ck("LVE bolumune yalniz CPU/RAM satirlari gider", suz(_lve_suzgec),
   NL.join(["lve_ok 1m", "lvecpu_tot 118.4 1", "lvecpu pixelcart 118.4 42 100",
            "lveram_tot 2841.0 1", "lveram pixelcart 2841.0 42 -1"]))

for f in (LISTE, STATE, MOD):
    if os.path.exists(f): os.remove(f)
shutil.rmtree(CP, ignore_errors=True)
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
