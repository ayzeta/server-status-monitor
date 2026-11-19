"""Yoklama onbelleginin damgalarini ILERI alir — testler agi beklemesin.

NEDEN: urun kapali her portu fsockopen ile 1 sn zaman asimi vererek yokluyor
(src/index.php, portOpen). Gelistirme makinesinde o portlarin hicbiri dinlemiyor,
yani her tam sayfa render'i ~16 saniyesini sirayla zaman asimi bekleyerek
geciriyor (olculdu 2026-11-19: render 16.6 sn, ama CPU suresi 0.015 sn —
hesap degil, bekleme). Uste urunun kendi onbellegi var ama TAM SAYFA render'inda
TTL 5 saniye; render 16 saniye surdugu icin bir sonraki render basladiginda
onbellek coktan bayat. Boylece 24 render 6 dakikadan fazla yiyordu.

NE YAPAR: isitma render'inin yazdigi az_probe_cache_*.json dosyasindaki her
girdinin 't' damgasini gelecege tasir. probeCached 'time() - t < ttl' diye
baktigi icin gelecekteki damga her zaman taze sayilir, yoklama bir daha
kosmaz. Degerlere DOKUNULMAZ — ne uydurulur ne degistirilir, yalnizca
isitmada gercekten olculmus sonuclar saklanir.

NEDEN GUVENLI: hicbir test gercek yoklama sonucuna bagli degil; portOpen'a
deger veren tek test (t_yokluk) onu kendi icinde yerine koyuyor. Ayrica
calistir.sh testlerin TMPDIR/TMP/TEMP'ini AYRI bir dizine alir, yani bu dosya
canli panonun onbellegi DEGILDIR — sunucuda test kosulsa bile pano etkilenmez.

Kullanim: python probe_isit.py <temp_dizini>
"""
import glob
import io
import json
import os
import sys

ILERI = 30 * 86400            # 30 gun; isaret onemli, buyuklugu degil

dizin = sys.argv[1] if len(sys.argv) > 1 else ""
if not os.path.isdir(dizin):
    sys.exit("dizin yok: %s" % dizin)

import time
hedef = int(time.time()) + ILERI
n = 0
for yol in glob.glob(os.path.join(dizin, "az_probe_cache_*.json")):
    try:
        with io.open(yol, encoding="utf-8", errors="replace") as fd:
            veri = json.load(fd)
    except Exception as e:
        print("okunamadi %s: %s" % (yol, e))
        continue
    if not isinstance(veri, dict):
        continue
    for k, girdi in veri.items():
        if isinstance(girdi, dict) and "t" in girdi:
            girdi["t"] = hedef
            n += 1
    with io.open(yol, "w", encoding="utf-8", newline="\n") as fd:
        fd.write(json.dumps(veri))

print("yoklama onbellegi isitildi: %d girdi" % n)
