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
gb = src.index("  const lveGovde=(rows,tur,ok,totalGB)=>{")
ge = src.index(NL + "  };", gb) + len(NL + "  };")
js_govde = src[gb:ge]

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
    "$T = ['%s processes' => '%s surec'];",
    "function t($s) { global $T; return $T[$s] ?? $s; }",
    "function tf($s, ...$a) { global $T; return vsprintf($T[$s] ?? $s, $a); }",
    "$memTotalGB = %d;" % RAM_GB,
    php_blok,
    "$h = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');",
    "$cikti = [];",
    "foreach (json_decode(file_get_contents('t_lve_in.json'), true) as [$tur, $rows]) {",
    "  $cikti[] = lveAcctRows($rows, $h, true, $tur);",
    "  $cikti[] = lveAcctRows($rows, $h, false, $tur);",   # olculemedi dali
    "}",
    "echo json_encode($cikti);",
])

js = NL.join([
    "const TRD={'%s processes':'%s surec'};",
    "function t(s){return TRD[s]||s;}",
    "function tf(s){var a=[].slice.call(arguments,1),i=0;"
    "return (TRD[s]||s).replace(/%s/g,function(){return a[i++];}).replace(/%%/g,'%');}",
    "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
    ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#039;');}",
    js_fmt,
    "function govde(tur,rows,ok){",
    js_govde,
    "  return lveGovde(rows,tur,ok,%d);" % RAM_GB,
    "}",
    "const giris=require('./t_lve_in.json');",
    "const cikti=[];",
    "for(const [tur,rows] of giris){cikti.push(govde(tur,rows,true));cikti.push(govde(tur,rows,false));}",
    "console.log(JSON.stringify(cikti));",
])

io.open(os.path.join(BURASI, "t_lve_in.json"), "w", encoding="utf-8").write(json.dumps(ORNEK))
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


ck("iki taraf ayni sayida govde uretti", (len(p), len(j)), (len(ORNEK) * 2, len(ORNEK) * 2))
for i, (a, b) in enumerate(zip(p, j)):
    tur, rows = ORNEK[i // 2]
    ad = "%s %s %s" % (tur, "olculdu" if i % 2 == 0 else "olculemedi", json.dumps(rows)[:24])
    ck(ad, norm(a) == norm(b), True)

# ── Govdenin kendisi dogru mu (ikizlik tek basina yetmez) ───────────────
g = norm(p[4])          # CPU esikleri, olculdu
ck("CPU %118.4 kirmizi", 'class="num hot" title="24 surec">118.4<' in g, True)
ck("CPU tam bir cekirdek (%100) kirmizi", 'class="num hot" title="11 surec">100.0<' in g, True)
ck("CPU %99.9 kirmizi DEGIL", 'class="num warm" title="7 surec">99.9<' in g, True)
ck("CPU %50 turuncu", 'class="num warm" title="3 surec">50.0<' in g, True)
ck("CPU %49.9 renksiz", 'class="num " title="2 surec">49.9<' in g, True)
ck("CPU metni her zaman tek ondalik", ">62.0<" in norm(p[6]) and ">120.0<" in norm(p[6]), True)

r = norm(p[8])          # RAM esikleri, olculdu
ck("RAM 4813 MB (94 GB'in %5'i) kirmizi", 'class="num hot" title="40 surec">4.7 GB<' in r, True)
ck("RAM 4812 MB (%5'in altinda) turuncu", 'class="num warm" title="30 surec">4.7 GB<' in r, True)
ck("RAM 2407 MB (%2,5) turuncu", 'class="num warm" title="20 surec">2.4 GB<' in r, True)
ck("RAM 2406 MB (%2,5 altinda) renksiz", 'class="num " title="10 surec">2.3 GB<' in r, True)

b = norm(p[10])         # birim gecisleri
for beklenen in (">1023 MB<", ">1 GB<", ">2.8 GB<", ">10 GB<", ">0 MB<"):
    ck("RAM birimi: " + beklenen, beklenen in b, True)

ck("hesap adi kaciriliyor", "&lt;script&gt;" in norm(p[12]), True)
ck("surec sayisi 0 ise ipucu yok", "title=" not in norm(p[14]), True)

bos_ok = norm(p[0]); bos_yok = norm(p[1])
ck("olculdu + bos: 'CPU yakan hesap yok'", "burning CPU" in bos_ok, True)
ck("olculemedi: CloudLinux LVE deniyor", "CloudLinux LVE" in bos_yok, True)
ck("iki bos mesaji AYRI", bos_ok != bos_yok, True)

for f in ("t_lve_in.json", "t_lveikiz.php", "t_lveikiz.js"):
    try: os.remove(os.path.join(BURASI, f))
    except OSError: pass

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
