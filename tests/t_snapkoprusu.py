"""ANLIK GORUNTU -> PANO koprusu: toplayicinin YAZDIGI her bolumun ayristiricida
bir dali var mi.

Gercek kusur (2026-10-22): surec I/O'su "--- Top IO processes ---" bolumune
yaziliyordu ama ayristiricida o baslik icin dal yoktu; satirlar sessizce cope
gidiyor, kart "surec I/O olculemedi" diyordu. Uretici ve render ayri ayri
sinanmisti, ARALARINDAKI kablo sinanmamisti.

Bu test iki yonlu: (1) yazilan her bolum okunuyor mu, (2) ornek bir anlik
goruntu gercekten ayristirilip beklenen degiskenleri dolduruyor mu.
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
col = io.open(KOK + "src/collector.sh", encoding='utf-8', errors='replace').read()
php = io.open(KOK + "src/index.php", encoding='utf-8', errors='replace').read()

yazilan = [m.group(1).strip() for m in
           re.finditer(r'echo "--- (.+?) ---"', col)]
okunan = [m.group(1) for m in re.finditer(r"stripos\(\$title, '([^']+)'\)", php)]

hata = 0
print("── Yazılan bölümler ve karşılığı")
for b in dict.fromkeys(yazilan):
    eslesen = [o for o in okunan if o.lower() in b.lower()]
    if eslesen:
        print("   %-24s -> %s" % (b, eslesen[0]))
    else:
        hata += 1
        print("   %-24s -> DAL YOK (satırlar çöpe gider)" % b)

# ── Ucu uca: ornek anlik goruntu ayristiriliyor mu ─────────────
ornek = NL.join([
    "--- Top IO accounts ---",
    "io_src lve 1m",          # pencere alani: kart hangi araligi gosterdigini bilir
    "ioacct makinem 45.0 12",
    "",
    "--- Top IO processes ---",
    "ioproc_ok 1m",           # "olctuk, yapan yok" ile "olculemedi" ayrimi
    # YENI bicim (PID'li) ve ESKI bicim bir arada: guncellemeden sonra diskteki
    # anlik goruntu bir tur boyunca eski collector'in yazdigi hali olabiliyor.
    "ioproc 2295514 mysql 2048.0 /usr/sbin/mariadbd",
    "ioproc root 512.0 /usr/local/cpanel/bin/backup_-x",
    "",
])
io.open(os.path.join(BURASI, "t_snap.txt"), "w", encoding="utf-8", newline=NL).write(ornek)

# Ayristirma dongusunu kaynaktan cikar
bas = php.index("    $sections = preg_split(")
son = php.index(NL + "    }" + NL, php.index("Top IO processes", bas))
kod = php[bas:son] + NL + "    }"

test = NL.join([
    "<?php",
    '$snapRaw = file_get_contents("t_snap.txt");',
    "$ioAcct = []; $ioProc = []; $ioSrc = ''; $ioWin = ''; $ioProcOk = false;",
    "$diskAcct = []; $procCpu = [];",
    "$procRam = []; $procPhp = []; $procSql = []; $procSec = []; $rootSvc = [];",
    "$svcAge = []; $svcVer = []; $mailqTop = []; $smartBad = []; $netSpeed = [];",
    kod,
    'echo json_encode(["ioSrc" => $ioSrc, "ioWin" => $ioWin, "ioProcOk" => $ioProcOk,',
    '                  "acct" => $ioAcct, "proc" => $ioProc]);',
])
io.open(os.path.join(BURASI, "t_snap.php"), "w", encoding="utf-8", newline=NL).write(test)
r = subprocess.run(["php", "t_snap.php"], capture_output=True, text=True,
                   encoding="utf-8", cwd=BURASI)
if r.returncode:
    sys.exit("ayristirma calismadi: " + (r.stderr or r.stdout)[:300])

import json
o = json.loads(r.stdout)
print()
print("── Uçtan uca ayrıştırma")


def ck(ad, gelen, beklenen):
    global hata
    if gelen == beklenen:
        print("   %-38s -> %r" % (ad, gelen))
    else:
        hata += 1
        print("   BASARISIZ %s: beklenen=%r gelen=%r" % (ad, beklenen, gelen))


ck("io kaynagi", o["ioSrc"], "lve")
ck("io penceresi", o["ioWin"], "1m")
ck("surec olcum isareti", o["ioProcOk"], True)
ck("hesap satiri", o["acct"], [["makinem", 45.0, 12]])
ck("surec satiri sayisi", len(o["proc"]), 2)
# PID satirda tasiniyor ama EKRANDA YOK: ayristirici onu atar, iki bicim de
# ayni uc alana dusurulur (yeni collector 5 alan, eskisi 4 alan yaziyor).
ck("yeni bicim: pid atilir", o["proc"][0], ["mysql", 2048.0, "/usr/sbin/mariadbd"])
ck("eski bicim de okunur", o["proc"][1], ["root", 512.0, "/usr/local/cpanel/bin/backup -x"])
ck("alt cizgi bosluga cevrilir", o["proc"][1][2], "/usr/local/cpanel/bin/backup -x")

for f in ("t_snap.txt", "t_snap.php"):
    os.remove(os.path.join(BURASI, f))
print()
print("HATA: %d" % hata)
sys.exit(1 if hata else 0)
