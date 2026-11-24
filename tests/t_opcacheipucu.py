"""OPCACHE SATIRININ IPUCU: "1.2/3.1 GB" ifadesinin NE oldugunu soyluyor mu?

URETIMDE GORULDU (2026-11-25): ipucu tek paragrafti, dogruydu ama kullanici
"yarim saat okudum, tutulan/ayrilan oldugunu anlamak guc" dedi. Redis satirinin
ipucu KISA parcalardan olusuyor (' · ' ile ayrilmis) ve o anlasiliyordu.

KURAL: OPcache ipucu da ayni dilbilgisinde olur; ILK is sayilari adlandirmaktir,
gerekce arkadan gelir. Ve TUTULAN OLCULEMEDIYSE "soldaki/sagdaki" parcasi HIC
yazilmaz -- o zaman notta tek sayi vardir ("3.1 GB ayrilmis"), sol/sag demek
olmayan bir seyi tarif etmek olurdu.

Bu test URUN KODUNU KAYNAKTAN CIKARIP kosar (kopyasini degil): index.php'deki
OPcache blogu, stub t()/tf() ile. Ayrica her ipucu dizgesinin SOZLUKTE TURKCE
karsiligi var mi diye bakar -- t() eksik anahtarda sessizce Ingilizceye duser,
bu depoda iki kez yasandi.
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NL = chr(10)
BURASI = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURASI) + "/"
src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()

b = src.index("// ── OPcache ──")
blok = src[b:src.index(NL + "[$cacheStatus", b)]

gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-52s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, beklenen, NL, gelen))


def kos(opcache, shmem, tmpfs):
    """Blogu gercek PHP ile kosar; (note, noteT, fill) dondurur."""
    tmp = os.path.join(BURASI, "t_opcacheipucu_tmp.php")
    on = [
        "<?php",
        "function t($s){return $s;}",
        "function tf($s,...$a){return vsprintf($s,$a);}",
        "$cacheChecks=[];",
        "$procSec=" + ("['opcache'=>'%s'];" % opcache if opcache is not None else "[];"),
        "$shmemGB=%s; $tmpfsGB=%s;" % (shmem, "null" if tmpfs is None else tmpfs),
    ]
    son = [
        "$c=$cacheChecks?end($cacheChecks):null;",
        "echo json_encode($c===null?null:[$c['note'],$c['noteT'],",
        "  array_key_exists('fill',$c)?$c['fill']:null], JSON_UNESCAPED_UNICODE);",
    ]
    io.open(tmp, "w", encoding="utf-8", newline=NL).write(
        NL.join(on) + NL + blok + NL + NL.join(son) + NL)
    r = subprocess.run(["php", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if r.returncode:
        sys.exit("php hatasi: " + (r.stderr or r.stdout)[:600])
    import json
    return json.loads(r.stdout)


# ── 1) Tutulan OLCULDU: not iki sayi, ipucu ikisini de adlandirir ──────
# 25 havuz x 128 MB = 3200 MB; shmem 1.8 - tmpfs 0.3 = 1.5 GB tutulan.
note, tip, fill = kos("25 3200", "1.8", "0.3")
ck("not: havuz sayisi · tutulan/ayrilan", note, "25 pools · 1.5/3.1 GB")
parca = tip.split(" · ")


def pa(i):
    return parca[i] if i < len(parca) else "(parca yok)"


ck("ipucu TEK PARAGRAF degil, parcali", len(parca), 4)
ck("1. parca: bu nedir", pa(0), "PHP compiled-code cache")
ck("2. parca: sayilari adlandirir", pa(1), "left figure held, right reserved")
ck("3. parca: tutulan nereden", pa(2),
   "held: the part really in RAM (shmem minus tmpfs)")
ck("4. parca: ayrilan nereden", pa(3),
   "reserved: what the live pools set aside, it moves as pools come and go")
ck("parcalarin hepsi kisa (<=70 karakter)", max(len(p) for p in parca) <= 70, True)
ck("sayilar ipucunda TEKRARLANMAZ (Redis kurali)",
   bool(re.search(r"\d+\.\d+ GB", tip)), False)
# 1.5 / 3.125 = %48 (notta yuvarlanmis 3.1 gorunur, cubuk ham sayiyi kullanir).
ck("cubuk: tutulan/ayrilan orani", fill, 48)

# ── 2) Tutulan OLCULEMEDI: sol/sag diye bir sey YOK ────────────────────
# tmpfs okunamadi (null) -> cikarma yapilamaz, notta tek sayi kalir.
note2, tip2, fill2 = kos("25 3200", "1.8", None)
ck("tmpfs okunamadi: not tek sayi", note2, "25 pools · 3.1 GB reserved")
ck("  ipucunda 'soldaki/sagdaki' YOK", "left figure" in tip2, False)
ck("  ipucunda 'tutulan' aciklamasi da YOK", "held:" in tip2, False)
ck("  geriye kalan: ne oldugu + ayrilan", tip2.split(" · "),
   ["PHP compiled-code cache",
    "reserved: what the live pools set aside, it moves as pools come and go"])
ck("  cubuk cizilmez (payda tek basina oran degil)", fill2, None)
# tmpfs >= shmem: cikarma anlamsiz, ayni yola duser.
ck("tmpfs shmem'e esit: yine tek sayi", kos("25 3200", "0.3", "0.3")[0],
   "25 pools · 3.1 GB reserved")

# ── 3) Olculemedi: satir HIC cizilmez ──────────────────────────────────
ck("opcache satiri yok -> kart satiri da yok", kos(None, "1.8", "0.3"), None)
ck("sayim 0 -> satir yok", kos("0 0", "1.8", "0.3"), None)

# ── 4) Her ipucu dizgesinin TURKCE karsiligi var mi ────────────────────
# t() eksik anahtarda sessizce Ingilizceye duser; ekranda fark edilmez.
for p in parca:
    m = re.search(r"'" + re.escape(p) + r"'\s*=>\s*'([^']+)'", src, re.S)
    ck("sozlukte TR karsiligi: " + p[:34], bool(m) and m.group(1) != p, True)

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
