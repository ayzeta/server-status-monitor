"""SSL seviyesi TEK kaynaktan mi geliyor: PHP ile JS ayni mi, ve JS eski
sayfa esigine DUSMUYOR mu.

Gercek olay: kullanici onbellegi silince baslik (sunucudan) duzeldi ama kutu
(tarayicida TH ile hesaplanan) sari kaldi. Bu test o ayrismayi yakalar.
"""
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BURASI = os.path.dirname(os.path.abspath(__file__))
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
NL = chr(10)
src = io.open(KOK + "src/index.php", encoding='utf-8', errors='replace').read()

# PHP: seviye hesabi
pb = src.index("$sslLvl = $sslDaysLeft === null ? 'ok'")
pe = src.index(";", src.index("'warn' : 'ok'", pb)) + 1
php_lvl = src[pb:pe]
# PHP: renk
cb = src.index("$sslColorCss = $sslLvl === 'err'")
ce = src.index(";", cb) + 1
php_col = src[cb:ce]

# JS: renk dali
jb = src.index("    const lvl=data.sslLvl||")
je = src.index(NL, src.index("const col=lvl===", jb))
js_col = src[jb:je]
# JS: olay kaydi dali
tb = src.index("    const sl=data.sslLvl||")
te = src.index(NL, tb)
js_log = src[tb:te]

for ad, parca in (('JS renk', js_col), ('JS olay', js_log)):
    if 'data.sslLvl' not in parca:
        sys.exit("%s sunucunun seviyesini kullanmiyor" % ad)

DURUMLAR = [
    # gun, ssl_warn, ssl_crit, beklenen seviye
    [30, 14, 5, 'ok'], [14, 14, 5, 'warn'], [5, 14, 5, 'err'],
    [30, 30, 7, 'warn'], [7, 30, 7, 'err'], [31, 30, 7, 'ok'],
    [None, 14, 5, 'ok'],
]
io.open(os.path.join(BURASI, "t_ssl_in.json"), "w", encoding="utf-8").write(json.dumps(DURUMLAR))

php = NL.join([
    "<?php",
    "$cikti = [];",
    "foreach (json_decode(file_get_contents('t_ssl_in.json'), true) as $d) {",
    "  [$sslDaysLeft, $w, $c] = $d;",
    "  $TH = ['ssl_warn' => $w, 'ssl_crit' => $c];",
    php_lvl,
    php_col,
    "  $cikti[] = [$sslLvl, $sslColorCss];",
    "}",
    "echo json_encode($cikti);",
])
js = NL.join([
    "const giris=require('./t_ssl_in.json');",
    "const out=giris.map(d=>{",
    "  const [g,w,c]=d;",
    "  // Sunucunun seviyesi: PHP ile ayni kurali burada TEKRARLAMIYORUZ, veri gibi veriyoruz.",
    "  const lvlSrv=g===null?'ok':(g<=c?'err':(g<=w?'warn':'ok'));",
    "  // ESKI sayfa esigi bilerek YANLIS verilir (30/7): JS sunucuya uyuyorsa etkilenmez.",
    "  const TH={ssl_warn:30,ssl_crit:7};",
    "  const data={sslDaysLeft:g,sslLvl:lvlSrv};",
    js_col,
    "  return [lvl,col];});",
    "console.log(JSON.stringify(out));",
])
io.open(os.path.join(BURASI, "t_sslikiz.php"), "w", encoding="utf-8", newline=NL).write(php)
io.open(os.path.join(BURASI, "t_sslikiz.js"), "w", encoding="utf-8", newline=NL).write(js)

rp = subprocess.run(["php", "t_sslikiz.php"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
rj = subprocess.run(["node", "t_sslikiz.js"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
if rp.returncode or rj.returncode:
    sys.exit((rp.stderr or "") + (rj.stderr or ""))
p = json.loads(rp.stdout); j = json.loads(rj.stdout)

fail = 0
for d, a, b in zip(DURUMLAR, p, j):
    ad = "gun=%s esik=%s/%s" % (d[0], d[1], d[2])
    if a != b:
        fail += 1
        print("  AYRISMA %-22s php=%s js=%s" % (ad, a, b))
    elif a[0] != d[3]:
        fail += 1
        print("  BEKLENTI %-22s beklenen=%s gelen=%s" % (ad, d[3], a[0]))
    else:
        print("  %-22s -> %s" % (ad, a))

print()
print("AYRISMA/HATA: %d" % fail)
sys.exit(1 if fail else 0)
