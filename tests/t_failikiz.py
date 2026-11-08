"""Yuk/CPU/RAM uyarisindaki FAIL EKI: PHP ve JS ayni satiri mi yaziyor.

Iki yol var ve ikisi de ayni olayi anlatiyor:
  - PHP ($topSfx)  : gecmis sutunundan. SAYFA ACILISI ve MAIL EKI bunu kullanir
                     -- ekte JS hic kosmaz, olay kaydi tamamen sunucu render
                     sonucundan gelir.
  - JS   (rowTop)  : canli tikte, anlik goruntunun surec satirindan.
Biri "lsphp", oteki "lsphp - acmeco - public_html/index.php" derse pano kendi
kendisiyle celisir. 1.5.68'e kadar TAM OLARAK bu oluyordu: betik yolu yalnizca
canli sayfada vardi, gecmis sutununda yoktu.

Girdi UYDURULMUYOR: PHP tarafina verilen alan, t_pssnap.sh'in URUN KODUYLA
uretip dogruladigi bicimin aynisi ("deger:hesap:ad:betik"); JS tarafina verilen
komut satiri da ayni surecin gercek ps args hali.
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"
BURASI = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()

# ── Iki dali da KAYNAKTAN cikar ────────────────────────────────
pb = src.index("        $topSfx = function ($raw, $fmt, $lead = null) {")
pe = src.index(NL + "        };", pb) + len(NL + "        };")
php_fn = src[pb:pe]

jb = src.index("  const ptok=c=>")
JM = "    return n+u+(sc?' · '+sc:'')+' '+val;};"
je = src.index(JM, jb) + len(JM)
js_blok = src[jb:je]

# ── Ornekler: (alan, canli_satir, beklenen) ────────────────────
# canli_satir = [pid, kullanici, cpu, mem, sure, komut] (data.procCpu bicimi)
ORNEK = [
    ("26:acmeco:lsphp:public_html/index.php",
     [1234, "acmeco", 26, 0.1, "05:05", "lsphp:/home/acmeco/public_html/index.php"]),
    ("8192:mysql:mariadbd:",
     [2295514, "mysql", 8192, 6.1, "1-00:00:00", "/usr/sbin/mariadbd"]),
    ("10:root:im360.run:",
     [1291495, "root", 10, 0.1, "00:16", "/opt/imunify360/venv/bin/python3 -m im360.run"]),
]

php = NL.join([
    "<?php",
    "function t($s) { return $s; }",
    "$cikti = [];",
    php_fn.strip(),
    "foreach (json_decode(file_get_contents('t_fail_in.json'), true) as $alan) {",
    "  $cikti[] = $topSfx($alan, function ($v) { return $v . '%'; });",
    "}",
    "echo json_encode($cikti, JSON_UNESCAPED_UNICODE);",
])

js = NL.join([
    # Blok icinde suffix()/snapFresh de var (fail ekinin onegini kuran kisim);
    # rowTop onlara dokunmuyor ama tanimsiz degiskenle yuklenemiyor.
    "function t(s){return s;}",
    "function tf(s){var a=[].slice.call(arguments,1),i=0;"
    "return s.replace(/%s/g,function(){return a[i++];});}",
    "const data={procAge:0}, TH={snap_stale:90};",
    "const giris=require('./t_fail_rows.json');",
    js_blok,
    "const out=giris.map(r=>rowTop(r, r[2]+'%'));",
    "console.log(JSON.stringify(out));",
])

io.open(os.path.join(BURASI, "t_fail_in.json"), "w", encoding="utf-8").write(
    json.dumps([a for a, _ in ORNEK]))
io.open(os.path.join(BURASI, "t_fail_rows.json"), "w", encoding="utf-8").write(
    json.dumps([r for _, r in ORNEK]))
io.open(os.path.join(BURASI, "t_failikiz.php"), "w", encoding="utf-8", newline=NL).write(php)
io.open(os.path.join(BURASI, "t_failikiz.js"), "w", encoding="utf-8", newline=NL).write(js)

rp = subprocess.run(["php", "t_failikiz.php"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
rj = subprocess.run(["node", "t_failikiz.js"], capture_output=True, text=True,
                    encoding="utf-8", cwd=BURASI)
if rp.returncode or rj.returncode:
    sys.exit((rp.stderr or "") + (rj.stderr or ""))

p = json.loads(rp.stdout)
j = json.loads(rj.stdout)

gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-48s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s:%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, beklenen, NL, gelen))


# PHP eki " - top: <metin>" seklinde; JS yalniz <metin> uretir (onekini
# suffix() koyuyor). Karsilastirmadan once onek atilir.
onek = "— " + "top:" + " "
for (alan, _), ph, jsx in zip(ORNEK, p, j):
    ck("ikiz: " + alan, ph.strip()[len(onek):], jsx)

# ── Betik yolu GERCEKTEN yaziliyor mu (asil regresyon) ─────────
ck("lsphp satirinda betik yolu var", "public_html/index.php" in p[0], True)
ck("hesap adi yolun icinde tekrarlanmiyor", "/home/acmeco" in p[0], False)
ck("betigi olmayan surecte fazladan ayirac yok", p[1].strip(), "— top: mariadbd · mysql 8192%")

# ── Eski bicim (1.5.67 ve oncesi) hala okunuyor ────────────────
# Guncellemeden sonra gecmis dosyasinda ~35 dakika eski satir kaliyor.
eski = subprocess.run(["php", "-r", NL.join([
    "function t($s){return $s;}", php_fn.strip(),
    "echo $topSfx('lsphp:26:acmeco', function($v){return $v.'%';});"])],
    capture_output=True, text=True, encoding="utf-8", cwd=BURASI)
ck("eski sira da okunur (ad:deger:hesap)", eski.stdout.strip(), "— top: lsphp · acmeco 26%")

# ── I/O kolonu: "deger::hesap" (ortadaki alan kasten bos) ──────
io_t = subprocess.run(["php", "-r", NL.join([
    "function t($s){return $s;}", php_fn.strip(),
    "echo $topSfx('5::ayzeta', function($v){return $v.' KB/s';});"])],
    capture_output=True, text=True, encoding="utf-8", cwd=BURASI)
ck("I/O kolonu: bos sahip alani satiri bozmuyor", io_t.stdout.strip(),
   "— top: ayzeta 5 KB/s")

for f in ("t_fail_in.json", "t_fail_rows.json", "t_failikiz.php", "t_failikiz.js"):
    y = os.path.join(BURASI, f)
    if os.path.exists(y):
        os.remove(y)

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
