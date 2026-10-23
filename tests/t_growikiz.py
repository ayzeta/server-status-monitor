"""Buyume govdesinin PHP ve JS ikizleri AYNI HTML'i mi uretiyor.

Sunucu render'i ile 30 sn'lik tik ayni veriden farkli satir uretirse, kullanici
sekmeye bakarken satirlar yerinden oynar. Iki dal da KAYNAKTAN cikarilir.
"""
import io
import os
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
NL = chr(10)
src = io.open(KOK + "src/index.php", encoding='utf-8', errors='replace').read()

pb = src.index('function diskGrowRows(')
pe = src.index(NL + "}", pb) + 2
php_fn = src[pb:pe]

# Birim bicimleyici de KAYNAKTAN: iki taraf ayni yuvarlamayi yapmazsa satirlar
# sunucu render'i ile tik arasinda degisir (ornegin 1.005 GB).
fb = src.index("function fmtGrow($gb) {")
fe = src.index(NL + "}", fb) + 2
php_fmt = src[fb:fe]
jb = src.index("function fmtGrow(gb){")
je = src.index("+' GB';}", jb) + len("+' GB';}")
js_fmt = src[jb:je]

# JS tarafinda govde uretimi artik ayri bir fonksiyon (pencere basina cagriliyor).
jb = src.index("    const govde=rows=>{")
je = src.index(NL + "    };", jb) + len(NL + "    };")
js_blok = src[jb:je]

ORNEK = [
    None,
    [],
    [["bluewave", 12.6, False]],
    [["tasinan", 80.0, True], ["rutin", 1.5, True], ["bluewave", 1.0, False]],
    [["a", 3.0, False], ["b", 1.0, False]],
    [["<script>", 2.0, True]],          # kacis: iki taraf da ayni kacmali
    # Birim sinirlari ve yuvarlama: MB/GB gecisi, yarim deger, cok kucuk artis
    [["mb", 0.019, False], ["tamgb", 1.0, False], ["sinir", 0.999, False],
     ["yarim", 1.005, False], ["minik", 0.001, False], ["buyuk", 12.345, False]],
]

php = NL.join([
    "<?php",
    "$T = ['growth data is building up' => 'artis birikiyor',",
    "      'no account grew in this window' => 'bu pencerede buyuyen yok', 'new' => 'yeni',",
    "      'No record at the start of the window — account is new or was not yet measured' => 'kaydi yok'];",
    "function t($s) { global $T; return $T[$s] ?? $s; }",
    php_fmt,
    php_fn,
    "$h = fn($s) => htmlspecialchars($s, ENT_QUOTES, 'UTF-8');",
    "$cikti = [];",
    "foreach (json_decode(file_get_contents('t_grow_in.json'), true) as $v) {",
    "  $cikti[] = diskGrowRows($v, $h);",
    "}",
    "echo json_encode($cikti);",
])

js = NL.join([
    "const TRD={'growth data is building up':'artis birikiyor',",
    "  'no account grew in this window':'bu pencerede buyuyen yok','new':'yeni',",
    "  'No record at the start of the window — account is new or was not yet measured':'kaydi yok'};",
    "function t(s){return TRD[s]||s;}",
    "function tf(s){var a=[].slice.call(arguments,1),i=0;"
    "return (TRD[s]||s).replace(/%s/g,function(){return a[i++];});}",
    "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
    ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#039;');}",
    js_fmt,
    "const giris=require('./t_grow_in.json');",
    js_blok.replace("    const govde", "const govde"),
    "const out=giris.map(v=>govde(v));",
    "console.log(JSON.stringify(out));",
])

io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "t_grow_in.json"), "w", encoding="utf-8").write(json.dumps(ORNEK))
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "t_growikiz.php"), "w", encoding="utf-8", newline=NL).write(php)
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "t_growikiz.js"), "w", encoding="utf-8", newline=NL).write(js)

rp = subprocess.run(["php", "t_growikiz.php"], capture_output=True, text=True,
                    encoding="utf-8", cwd=os.path.dirname(os.path.abspath(__file__)))
rj = subprocess.run(["node", "t_growikiz.js"], capture_output=True, text=True,
                    encoding="utf-8", cwd=os.path.dirname(os.path.abspath(__file__)))
if rp.returncode or rj.returncode:
    sys.exit((rp.stderr or "") + (rj.stderr or ""))

p = json.loads(rp.stdout)
j = json.loads(rj.stdout)


def norm(s):
    """Etiket ARASI bosluk anlamsiz: PHP okunur HTML icin satir sonu koyuyor,
    JS koymuyor; tarayicida ikisi ayni DOM. Etiket ICI metin aynen karsilastirilir."""
    import re
    return re.sub(r">\s+<", "><", " ".join(s.split())).strip()


fail = 0
for v, a, b in zip(ORNEK, p, j):
    ad = json.dumps(v)[:44]
    if norm(a) != norm(b):
        fail += 1
        print("  AYRISMA %s" % ad)
        print("    php=%s" % norm(a)[:200])
        print("    js =%s" % norm(b)[:200])
    else:
        print("  %-46s tutuyor" % ad)

print()
print("AYRISMA: %d" % fail)
sys.exit(1 if fail else 0)
