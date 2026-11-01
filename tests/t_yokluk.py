"""YOKLUK ARIZA DEĞİLDİR — bu sefer cPanel'in bildiği servisler için.

Önbellek kartında düzeltilen kural buraya da gerekiyordu: `whmSvcOk` cPanel
"kapalı" ya da "kurulu değil" dediğinde de null dönüyor ve kod o durumda PORT
YOKLAMASINA düşüyordu. Sonuç: FTP'si kapalı, DNS'i dışarıda ya da mail servisi
olmayan her kurulumda satır kırmızı yanıyordu — kullanılmayan bir şey için.

Karar tablosu (svcCheck KAYNAKTAN çıkarılıp koşuluyor; portOpen/isListening
testte yerine konuyor, böylece makinenin gerçek portları sonucu etkilemiyor):

  cPanel: açık+kurulu, çalışıyor      -> yeşil
  cPanel: açık+kurulu, çalışmıyor     -> KIRMIZI (çalışması gerekiyordu)
  cPanel: kapalı,      port kapalı    -> gri 'kullanılmıyor'
  cPanel: kurulu değil, port kapalı   -> gri 'kurulu değil'
  cPanel: kapalı AMA port açık        -> yeşil (çalışan şeye "yok" denmez)
  cPanel bilmiyor,     port kapalı    -> kırmızı (kanıt yok, eski davranış)
  cPanel bilmiyor,     port yok       -> gri 'bilinmiyor'
"""
import io
import json
import os
import subprocess
import sys

import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NL = chr(10)
BURASI = os.path.dirname(os.path.abspath(__file__))
src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()


def cikar(imza):
    b = src.index(imza)
    e = src.index(NL + "}", b) + 2
    return src[b:e]


php = NL.join([
    "<?php",
    "function t($s){ return $s; }",
    # portOpen/isListening TESTTE yerine konuyor: gercek makinenin portlari
    # sonucu etkilerse test urunu degil o makineyi olcerdi.
    "$GLOBALS['ACIK'] = [];",
    "function portOpen($h, $p){ return in_array($p, $GLOBALS['ACIK'], true); }",
    "function isListening($p, $lp){ return in_array($p, $GLOBALS['ACIK'], true); }",
    cikar("function whmSvcOk("),
    cikar("function svcCheck("),
    "$in = json_decode(file_get_contents('t_yokluk_in.json'), true);",
    "$out = [];",
    "foreach ($in as $c) {",
    "  $GLOBALS['ACIK'] = $c['acik'];",
    "  $r = svcCheck('X', $c['ad'], $c['port'], [], $c['svc'], $c['whmOk']);",
    "  $out[] = ['ok' => !empty($r['ok']), 'unknown' => !empty($r['unknown']), 'note' => $r['note']];",
    "}",
    "echo json_encode($out);",
])


def svc(enabled=1, installed=1, running=1):
    """whmapi1'den gelen servis kaydının test karşılığı (yalnız 'ftpd' tanımlı:
    'cPanel bu servisi bilmiyor' durumunu kurmak için başka ad sorulur)."""
    return {"ftpd": {"name": "ftpd", "enabled": enabled,
                     "installed": installed, "running": running}}


DURUMLAR = [
    ("açık+kurulu, çalışıyor, port açık", dict(ad="ftpd", port=21, acik=[21], whmOk=True,
                                               svc=svc()), (True, False, "running · listening")),
    ("açık+kurulu, çalışmıyor -> KIRMIZI", dict(ad="ftpd", port=21, acik=[], whmOk=True,
                                                svc=svc(running=0)), (False, False, "stopped")),
    ("cPanel 'kapalı' + port kapalı -> gri", dict(ad="ftpd", port=21, acik=[], whmOk=True,
                                                  svc=svc(enabled=0)), (False, True, "not in use")),
    ("cPanel 'kurulu değil' -> gri", dict(ad="ftpd", port=21, acik=[], whmOk=True,
                                          svc=svc(installed=0)), (False, True, "not installed")),
    ("'kapalı' ama port AÇIK -> yeşil", dict(ad="ftpd", port=21, acik=[21], whmOk=True,
                                             svc=svc(enabled=0)), (True, False, "responding · listening")),
    ("cPanel bilmiyor + port kapalı -> kırmızı", dict(ad="redis", port=6379, acik=[], whmOk=True,
                                                      svc=svc()), (False, False, "no response")),
    ("cPanel bilmiyor + port yok -> gri", dict(ad="redis", port=None, acik=[], whmOk=True,
                                               svc=svc()), (False, True, "unknown")),
    ("besleme yok + port kapalı -> kırmızı", dict(ad="ftpd", port=21, acik=[], whmOk=False,
                                                  svc=svc(enabled=0)), (False, False, "no response")),
]

io.open(os.path.join(BURASI, "t_yokluk_in.json"), "w", encoding="utf-8").write(
    json.dumps([d for _, d, _ in DURUMLAR]))
io.open(os.path.join(BURASI, "t_yokluk.php"), "w", encoding="utf-8", newline=NL).write(php)
r = subprocess.run(["php", "t_yokluk.php"], capture_output=True, text=True,
                   encoding="utf-8", cwd=BURASI)
if r.returncode:
    sys.exit("php hatasi: " + (r.stderr or r.stdout)[:400])
sonuc = json.loads(r.stdout)

gecen = kalan = 0
for (ad, _, bek), g in zip(DURUMLAR, sonuc):
    gelen = (g["ok"], g["unknown"], g["note"])
    if gelen == bek:
        gecen += 1
        print("  %-44s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s:\n    beklenen=%r\n    gelen   =%r" % (ad, bek, gelen))

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
