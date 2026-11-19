"""Render eden testler icin: GERCEK config.php'yi yok etmeden gecici config yaz.

NEDEN: urunu gercekten render eden testler (t_bosdurum, t_onbellek, t_sekme)
src/config.php'ye kendi tohum dizinlerini yaziyor, sonra `os.remove` ile
SILIYORDU. O dosya .gitignore'da, yani depoda degil — GERCEK KURULUM dosyasi:
marka, web kullanicisi, esikler orada yasiyor. Bu depo sunucuda da duruyor ve
pano oradan kosuyor; orada `bash tests/calistir.sh` kosturan biri canli
yapilandirmayi geri donusu olmadan kaybediyordu (2026-11-19'da fark edildi).

NE YAPAR: gercek dosya varsa SILINMEZ, yanina '.test-yedek' olarak alinir;
test bitince geri konur. Cokme olursa bile kendini toparlar: bir sonraki
kosumda yedek yerinde durur ve geri() onu iade eder.
"""
import io
import os

NL = chr(10)


def _yollar(kok):
    cfg = kok + "src/config.php"
    return cfg, cfg + ".test-yedek"


def yaz(kok, home_dir):
    """Gecici config.php yazar. Gercek dosya varsa once kenara alinir."""
    cfg, yedek = _yollar(kok)
    if os.path.exists(cfg):
        if os.path.exists(yedek):
            # Onceki kosum yarida kalmis: YEDEK gercek olandir, cfg artiktir.
            os.remove(cfg)
        else:
            os.rename(cfg, yedek)
    io.open(cfg, "w", encoding="utf-8", newline=NL).write(
        "<?php" + NL + "return ['home_dir' => " +
        _json(home_dir.replace("\\", "/")) + "];" + NL)
    return cfg


def geri(kok):
    """Gecici config'i kaldirir, gercek dosya varsa yerine koyar."""
    cfg, yedek = _yollar(kok)
    if os.path.exists(cfg):
        os.remove(cfg)
    if os.path.exists(yedek):
        os.rename(yedek, cfg)


def _json(s):
    import json
    return json.dumps(s)
