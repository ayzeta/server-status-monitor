"""I/O SUREC govdesinin PHP ve JS ikizleri ayni HTML'i mi uretiyor.

Sunucu render'i (ve CSF mail eki) PHP ioProcRows() ile, 30 sn'lik tik JS ikiziyle
basiyor. Ayrisirlarsa sayfa ilk acilista baska, ilk tikte baska gorunur. Iki dal
da KAYNAKTAN cikariliyor — elle kopyalanmiyor.
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()

# ── PHP dali ───────────────────────────────────────────────────────────
pb = src.index("function ioProcRows(")
pe = src.index(NL + "}", pb) + 2
php_fn = src[pb:pe]
ab = src.index("function ioAcctCls(")
ae = src.index(NL + "}", ab) + 2
php_cls = src[ab:ae]
fb = src.index("function fmtKbps(")
fe = src.index(NL, fb) + 1
php_fmt = src[fb:fe]

# ── JS dali ────────────────────────────────────────────────────────────
jb = src.index("    const g=data.ioProc||[];")
je = src.index(".join('');" + NL + "    }", jb) + len(".join('');" + NL + "    }")
js_blok = src[jb:je]

ORNEK = [
    [],
    [["mysql", 2048.0, "/usr/sbin/mariadbd"]],
    [["root", 512.0, "/usr/local/cpanel/bin/backup -x"]],
    [["root", 900.0, "a"], ["nobody", 100.0, "b"]],      # %60+ ama 1 MB alti
    [["root", 2000.0, "a"], ["nobody", 900.0, "b"]],     # hot + warm
    [["<script>", 10.0, "cmd \"x\" & 'y'"]],             # kacis
]

php = NL.join([
    "<?php",
    "$T = ['no process I/O measured' => 'surec I/O olculemedi'];",
    "function t($s) { global $T; return $T[$s] ?? $s; }",
    php_fmt,
    php_cls,
    php_fn,
    "$h = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');",
    "$cikti = [];",
    "foreach (json_decode(file_get_contents('t_io_in.json'), true) as $v) {",
    "  $cikti[] = ioProcRows($v, $h);",
    "}",
    "echo json_encode($cikti);",
])

js = NL.join([
    "const TRD={'no process I/O measured':'surec I/O olculemedi'};",
    "function t(s){return TRD[s]||s;}",
    "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
    ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#039;');}",
    "function fmtKbps(kb){return kb>=1024?(Math.round(kb/1024*10)/10)+' MB/s':Math.round(kb)+' KB/s';}",
    "const giris=require('./t_io_in.json');",
    "function govde(rows){",
    "  const iop={innerHTML:''}, data={ioProc:rows};",
    js_blok,
    "  return iop.innerHTML;",
    "}",
    "console.log(JSON.stringify(giris.map(govde)));",
])

io.open(os.path.join(BURASI, "t_io_in.json"), "w", encoding="utf-8").write(json.dumps(ORNEK))
io.open(os.path.join(BURASI, "t_ioikiz.php"), "w", encoding="utf-8", newline=NL).write(php)
io.open(os.path.join(BURASI, "t_ioikiz.js"), "w", encoding="utf-8", newline=NL).write(js)

rp = subprocess.run(["php", "t_ioikiz.php"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
rj = subprocess.run(["node", "t_ioikiz.js"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
if rp.returncode or rj.returncode:
    sys.exit((rp.stderr or "") + (rj.stderr or ""))

p = json.loads(rp.stdout)
j = json.loads(rj.stdout)


def norm(s):
    return re.sub(r">\s+<", "><", " ".join(s.split())).strip()


fail = 0
for v, a, b in zip(ORNEK, p, j):
    ad = json.dumps(v)[:46]
    if norm(a) != norm(b):
        fail += 1
        print("  AYRISMA %s" % ad)
        print("    php=%s" % norm(a)[:220])
        print("    js =%s" % norm(b)[:220])
    else:
        print("  %-48s tutuyor" % ad)

# Komut artik TOOLTIPTE DEGIL, hucrenin kendisinde olmali (asil kusur buydu).
govde = norm(p[1])
if "/usr/sbin/mariadbd</span>" not in govde:
    fail += 1
    print("  EKSIK: komut metni hucrede gorunmuyor")
# Satir UC hucre: kullanici | komut | I/O (PID bilerek yok, cubuk da yok).
if govde.count("<td") != 3:
    fail += 1
    print("  BEKLENMEDIK sutun sayisi: %d" % govde.count("<td"))
if "php-bar" in govde:
    fail += 1
    print("  BEKLENMEDIK: surec gorunumunde cubuk var")

print()
print("AYRISMA: %d" % fail)
sys.exit(1 if fail else 0)
