"""Hesap basina CPU/RAM govdesinin PHP ve JS ikizleri ayni HTML'i mi uretiyor.

Sunucu render'i (ve CSF mail eki) PHP lveAcctRows() ile, 30 sn'lik tik JS
ikiziyle basiyor. Ayrisirlarsa sayfa ilk acilista baska, ilk tikte baska
gorunur. Iki dal da KAYNAKTAN cikariliyor -- elle kopyalanmiyor, cunku testin
icine yazilan kopya urun degisince sessizce eskiyor.

AYRICA burada sinanan tek sey ikizlik degil: RAM rengi FIZIKSEL RAM'in yuzdesine
bakiyor ve bu Windows'ta TAM SAYFA RENDER'I ile sinanamaz (/proc/meminfo yok,
$memTotalGB 0 kaliyor ve renk hep bos cikiyor). Bu yuzden karar kaynaktan
cikarilip DOGRUDAN kosuluyor -- t_onbellek'teki Redis tavani kararinin aynisi.
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()

# ── PHP dali: cpuAcctCls + ramAcctCls + fmtMB + lveAcctRows tek dilimde ──
pb = src.index("function cpuAcctCls(")
pe = src.index("function renderProcTables(", pb)
php_blok = src[pb:pe]
for ad in ("function cpuAcctCls(", "function ramAcctCls(", "function fmtMB(", "function lveAcctRows("):
    if ad not in php_blok:
        sys.exit("CAPA KAYDI: %r PHP diliminde yok" % ad)

# ── JS dali: bicimlendiriciler + govde ───────────────────────────────────
jb = src.index("function fmtMB(mb){")
je = src.index("return p>=5?'hot':p>=2.5?'warm':'';}", jb) + len("return p>=5?'hot':p>=2.5?'warm':'';}")
js_fmt = src[jb:je]
gb = src.index("  const lveGovde=(rows,tur,totalGB)=>{")
ge = src.index(NL + "  };", gb) + len(NL + "  };")
js_govde = src[gb:ge]
ob = src.index("  const lveOzet=(tot,cores,srv)=>{")
oe = src.index(NL + "  };", ob) + len(NL + "  };")
js_ozet = src[ob:oe]

# Ozet fiksturleri: (hesap toplami [tek cekirdek %], cekirdek, sunucu %).
# Esikler SECIM degil bicim: 10'un altinda tek ondalik, ustunde tam sayi.
OZET = [
    [205.4, 12, 24],      # tipik: pay %17,1 -> sistem %6,9
    [1200.0, 12, 100],    # hesaplar tam sunucu kadar -> sistem 0
    [600.0, 12, 10],      # OLCUM KAYMASI: pay sunucudan buyuk -> sistem 0, eksi YOK
    [119.9, 12, 24],      # pay 9,99 -> tek ondalik tarafi
    [120.1, 12, 24],      # pay 10,01 -> tam sayi tarafi
    [0.0, 12, 3],         # hic hesap yuk basmiyor ama sunucu mesgul (sistem)
    [205.4, 1, 30],       # tek cekirdek
    [None, 12, 24],       # toplayici bildirmedi -> satir BOS
    [205.4, 0, 24],       # cekirdek bilinmiyor -> satir BOS
    [205.4, 12, None],    # sunucu yuzdesi yok -> yalniz hesap payi
]

# RAM 94 GB (demo tohumuyla ayni): %5 = 4812 MB, %2,5 = 2406 MB.
RAM_GB = 94
ORNEK = [
    ["cpu", []],
    ["ram", []],
    # CPU esikleri: tam bir cekirdek kirmizi, yarim cekirdek turuncu.
    ["cpu", [["makinem", 118.4, 24], ["bluewave", 100.0, 11], ["riverside", 99.9, 7],
             ["zencache", 50.0, 3], ["maplebox", 49.9, 2], ["wholesale", 0.1, 1]]],
    # CPU metni HER ZAMAN tek ondalik (surec gorunumu de oyle).
    ["cpu", [["a", 62.0, 1], ["b", 120.0, 2], ["c", 7.5, 0]]],
    # RAM esikleri: 94 GB = 96256 MB; %5 = 4812,8 MB, %2,5 = 2406,4 MB.
    # Siniri HESAPLAYIP yazmak yetmiyordu -- 4812 "yuvarlak" gorunuyor ama
    # esigin ALTINDA; esigin iki yanindan birer ornek konuyor.
    ["ram", [["makinem", 4813.0, 40], ["bluewave", 4812.0, 30],
             ["riverside", 2407.0, 20], ["zencache", 2406.0, 10]]],
    # MB -> GB gecisi ve gereksiz sifir: 1023 MB, 1024 MB, 2841 MB, 10240 MB.
    ["ram", [["a", 1023.0, 1], ["b", 1024.0, 1], ["c", 2841.0, 1],
             ["d", 10240.0, 1], ["e", 0.4, 1]]],
    # Kacis: hesap adi uretimde suzuluyor ama govde kendi basina da kacirmali.
    ["cpu", [["<script>&'\"", 12.3, 1]]],
    # Surec sayisi 0 ise ipucu YAZILMAZ (olculmemis sayiyi gosterme).
    ["ram", [["a", 512.0, 0]]],
]

php = NL.join([
    "<?php",
    # TR anahtarlari da konuyor: '%%' kacisinin iki tarafta ayni cozulmesi
    # sinaniyor (PHP vsprintf vs JS iki asamali replace).
    "$T = ['%s processes' => '%s surec', '%s%% accounts' => 'hesaplar %%%s',"
    " '%s%% system' => 'sistem %%%s', '%s%% server' => 'sunucu %%%s'];",
    "function t($s) { global $T; return $T[$s] ?? $s; }",
    "function tf($s, ...$a) { global $T; return vsprintf($T[$s] ?? $s, $a); }",
    "$memTotalGB = %d;" % RAM_GB,
    php_blok,
    "$h = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');",
    "$cikti = [];",
    "foreach (json_decode(file_get_contents('t_lve_in.json'), true) as [$tur, $rows]) {",
    # LVE olcumu YOKSA bu tablo hic basilmiyor (bkz. t_sekme), yani tek dal var.
    "  $cikti[] = lveAcctRows($rows, $h, $tur);",
    "}",
    "foreach (json_decode(file_get_contents('t_lve_ozet.json'), true) as [$t, $c, $s]) {",
    "  $cikti[] = lveOzetMetni($t, $c, $s);",
    "}",
    "echo json_encode($cikti);",
])

js = NL.join([
    "const TRD={'%s processes':'%s surec','%s%% accounts':'hesaplar %%%s',"
    "'%s%% system':'sistem %%%s','%s%% server':'sunucu %%%s'};",
    "function t(s){return TRD[s]||s;}",
    "function tf(s){var a=[].slice.call(arguments,1),i=0;"
    "return (TRD[s]||s).replace(/%s/g,function(){return a[i++];}).replace(/%%/g,'%');}",
    "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
    ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#039;');}",
    js_fmt,
    "function govde(tur,rows){",
    js_govde,
    "  return lveGovde(rows,tur,%d);" % RAM_GB,
    "}",
    "function ozet(t,c,s){",
    js_ozet,
    "  return lveOzet(t,c,s);",
    "}",
    "const giris=require('./t_lve_in.json');",
    "const cikti=[];",
    "for(const [tur,rows] of giris){cikti.push(govde(tur,rows));}",
    "for(const [t,c,s] of require('./t_lve_ozet.json')){cikti.push(ozet(t,c,s));}",
    "console.log(JSON.stringify(cikti));",
])

io.open(os.path.join(BURASI, "t_lve_in.json"), "w", encoding="utf-8").write(json.dumps(ORNEK))
io.open(os.path.join(BURASI, "t_lve_ozet.json"), "w", encoding="utf-8").write(json.dumps(OZET))
io.open(os.path.join(BURASI, "t_lveikiz.php"), "w", encoding="utf-8", newline=NL).write(php)
io.open(os.path.join(BURASI, "t_lveikiz.js"), "w", encoding="utf-8", newline=NL).write(js)

rp = subprocess.run(["php", "t_lveikiz.php"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
rj = subprocess.run(["node", "t_lveikiz.js"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
if rp.returncode or rj.returncode:
    sys.exit((rp.stderr or "") + (rj.stderr or ""))

p = json.loads(rp.stdout)
j = json.loads(rj.stdout)


def norm(s):
    return re.sub(r">\s+<", "><", " ".join(s.split())).strip()


gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-52s -> %r" % (ad, gelen if not isinstance(gelen, str) or len(gelen) < 60
                                 else gelen[:57] + "..."))
    else:
        kalan += 1
        print("  BASARISIZ %s:%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, beklenen, NL, gelen))


N = len(ORNEK) + len(OZET)
ck("iki taraf ayni sayida cikti uretti", (len(p), len(j)), (N, N))
for i, (a, b) in enumerate(zip(p[:len(ORNEK)], j[:len(ORNEK)])):
    tur, rows = ORNEK[i]
    ck("%s %s" % (tur, json.dumps(rows)[:30]), norm(a) == norm(b), True)
for i, (a, b) in enumerate(zip(p[len(ORNEK):], j[len(ORNEK):])):
    ck("ozet %s" % json.dumps(OZET[i]), a == b, True)

# ── Govdenin kendisi dogru mu (ikizlik tek basina yetmez) ───────────────
g = norm(p[2])          # CPU esikleri
ck("CPU %118.4 kirmizi", 'class="num hot" title="24 surec">118.4<' in g, True)
ck("CPU tam bir cekirdek (%100) kirmizi", 'class="num hot" title="11 surec">100.0<' in g, True)
ck("CPU %99.9 kirmizi DEGIL", 'class="num warm" title="7 surec">99.9<' in g, True)
ck("CPU %50 turuncu", 'class="num warm" title="3 surec">50.0<' in g, True)
ck("CPU %49.9 renksiz", 'class="num " title="2 surec">49.9<' in g, True)
ck("CPU metni her zaman tek ondalik", ">62.0<" in norm(p[3]) and ">120.0<" in norm(p[3]), True)

r = norm(p[4])          # RAM esikleri
ck("RAM 4813 MB (94 GB'in %5'i) kirmizi", 'class="num hot" title="40 surec">4.7 GB<' in r, True)
ck("RAM 4812 MB (%5'in altinda) turuncu", 'class="num warm" title="30 surec">4.7 GB<' in r, True)
ck("RAM 2407 MB (%2,5) turuncu", 'class="num warm" title="20 surec">2.4 GB<' in r, True)
ck("RAM 2406 MB (%2,5 altinda) renksiz", 'class="num " title="10 surec">2.3 GB<' in r, True)

b = norm(p[5])          # birim gecisleri
for beklenen in (">1023 MB<", ">1 GB<", ">2.8 GB<", ">10 GB<", ">0 MB<"):
    ck("RAM birimi: " + beklenen, beklenen in b, True)

ck("hesap adi kaciriliyor", "&lt;script&gt;" in norm(p[6]), True)
ck("surec sayisi 0 ise ipucu yok", "title=" not in norm(p[7]), True)

# BOS LISTE = "olctuk, kimse yok". "Olculemedi" dali YOK: LVE olcumu gelmezse
# tablo hic basilmiyor (bkz. t_sekme), yani kullaniciya "CloudLinux kur"
# denmiyor. Iki bos mesaji yine de AYRI -- CPU'da "yakan yok", RAM'de
# "bildirilmedi" ve bu ikisi ayni sey degil.
bos_cpu = norm(p[0]); bos_ram = norm(p[1])
ck("bos CPU: 'CPU yakan hesap yok'", "burning CPU" in bos_cpu, True)
ck("bos RAM: ayri mesaj", "no account RAM reported" in bos_ram, True)
ck("iki bos mesaji AYRI", bos_cpu != bos_ram, True)
ck("hicbir bos mesajda 'CloudLinux' gecmiyor",
   ("CloudLinux" in bos_cpu, "CloudLinux" in bos_ram), (False, False))

# ── Ozet metni dogru mu (ikizlik tek basina yetmez) ─────────────────────
o = p[len(ORNEK):]
# 10'un ALTINDAKI her deger tek ondalik yazilir, 10 ve ustu tam sayi -- kural
# her sayiya AYRI uygulanir, yani "%17" ile "%6.9" ayni satirda olagan.
ck("tipik: 205,4 / 12 cekirdek", o[0], "hesaplar %17 · sistem %6.9 · sunucu %24")
ck("hesaplar sunucu kadar -> sistem %0", o[1], "hesaplar %100 · sistem %0.0 · sunucu %100")
# EN ONEMLI IDDIA: pay sunucu yuzdesini asiyorsa girdilerden biri guvenilmez.
# "sistem %0" demek OLCMEDIGIMIZ bir seyi iddia etmek olurdu -> yalniz pay.
ck("pay sunucudan buyuk -> sistem HIC yazilmaz", o[2], "hesaplar %50")
ck("pay 9,99 -> tek ondalik", o[3].startswith("hesaplar %10.0 "), True)
ck("pay 10,01 -> tam sayi", o[4].startswith("hesaplar %10 "), True)
ck("hic hesap yok ama sunucu mesgul", o[5], "hesaplar %0.0 · sistem %3.0 · sunucu %3")
ck("tek cekirdek: pay %205 > sunucu %30 -> yalniz pay", o[6], "hesaplar %205")
ck("toplayici bildirmedi -> satir BOS", o[7], "")
ck("cekirdek bilinmiyor -> satir BOS", o[8], "")
ck("sunucu yuzdesi yok -> yalniz hesap payi", o[9], "hesaplar %17")
ck("ozette '%%' kacisi cozulmus (cift yuzde yok)",
   any("%%" in s for s in o), False)

for f in ("t_lve_in.json", "t_lveikiz.php", "t_lveikiz.js"):
    try: os.remove(os.path.join(BURASI, f))
    except OSError: pass

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
