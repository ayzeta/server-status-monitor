"""OPcache segment taramasi: kural CEKIRDEGIN GERCEK /proc/<pid>/maps ciktisiyla
sinanir.

Fikstur UYDURULMADI: tests/ornek/maps_opcache.txt, gercek bir Linux cekirdeginin
urettigi maps dosyasidir. Icindeki uc paylasimli eslemeyi olusturmak icin
/dev/zero MAP_SHARED ile 128 MB, 1 MB ve 8 KB olarak haritalandi -- OPcache'in
yaptiginin aynisi. Alan dizilisi ($2 izinler, $5 inode, $6 yol) bu yuzden
tahmin degil, olcum.

NIYE ONEMLI: bu depoda tam olarak bu hata yasandi (2026-11-01). Baska bir
programin ciktisini ayristiran bir kural, o ciktinin VARSAYILAN halini esas
alinca uretimde hicbir satir eslesmedi ve pano ayakta olan 371 ornege
"calismiyor" dedi. Testler yesildi, cunku fiksturu de ayni varsayim yazmisti.
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"
NL = chr(10)
src = io.open(KOK + "src/collector.sh", encoding="utf-8", errors="replace").read()
ornek = io.open(KOK + "tests/ornek/maps_opcache.txt", encoding="utf-8").read()

# Kural KAYNAKTAN cikarilir; testin icine kopyalanan bir kural urun degisince
# sessizce eskir (TOPIO'da 16 gun suren regresyonun sebebi buydu).
b = src.index('echo "opcache $(cat /proc/[0-9]*/maps')
e = src.index("')\"", b)
kural = src[src.index("awk '", b) + len("awk '"):e]

gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-54s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, beklenen, NL, gelen))


def tara(metin):
    r = subprocess.run(["awk", kural], input=metin, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
    p = r.stdout.split()
    return (int(p[0]), int(p[1])) if len(p) == 2 else (None, None)


# ── Gercek ciktinin kendisi ────────────────────────────────────
ck("ornek gercek cekirdek ciktisi (uc paylasimli esleme)",
   len(re.findall(r"^\S+ rw-s .* /dev/zero", ornek, re.M)), 3)
ck("128 MB sayilir, 1 MB ve 8 KB esigin altinda kalir", tara(ornek), (1, 128))

# ── TEKILLESTIRME: ayni segmenti bir havuzun BUTUN surecleri haritalar ──
# Tekillestirilmezse rakam isci sayisi kadar siser. Ayni dosyayi uc kez
# beslemek, ayni segmenti haritalayan uc surec demektir.
ck("ayni segment uc surecte: sayilar DEGISMEZ", tara(ornek * 3), (1, 128))

# ── Inode farkliysa ayri segmenttir ────────────────────────────
# Gercek satirin yalnizca inode'u degistiriliyor (bicim aynen cekirdekten).
ikinci = re.sub(r"(rw-s 00000000 00:01 )10828", r"\g<1>99999", ornek)
ck("farkli inode = ayri segment", tara(ornek + ikinci), (2, 256))

# ── Esik: 8 MB ─────────────────────────────────────────────────
# Uretimde ayni kalipta 659 adet kucuk esleme olculdu (toplami 100 MB'in
# altinda: cpanel_php_fpm, litespeed, imunify360). OPcache segmenti
# memory_consumption kadardir ve pratikte cok daha buyuk.
ck("esik kaynakta 8 MB", "mb >= 8" in kural, True)
# 7 MB'lik gercek bir satir uretmek icin 128 MB'lik satirin BITIS adresi
# degistiriliyor; bicim yine cekirdekten.
yedi = "7b416c1c0000-7b416c8c0000 rw-s 00000000 00:01 10828                      /dev/zero (deleted)" + NL
ck("7 MB sayilmaz", tara(yedi), (0, 0))
sekiz = "7b416c1c0000-7b416c9c0000 rw-s 00000000 00:01 10828                      /dev/zero (deleted)" + NL
ck("8 MB sayilir", tara(sekiz), (1, 8))

# ── Yanlis eslemeler girmemeli ─────────────────────────────────
# 'rw-p' OZEL (paylasimsiz) bellektir, OPcache degil; dosya destekli
# paylasimli eslemeler de degil. Ikisi de gercek ornegin icinde zaten var.
ck("ozel (rw-p) eslemeler sayilmaz", tara(re.sub(r"rw-s", "rw-p", ornek)), (0, 0))
ck("/dev/zero disindaki paylasimli esleme sayilmaz",
   tara(re.sub(r"/dev/zero", "/dev/shm/x", ornek)), (0, 0))

# ── Hic eslesme yoksa cikti "0 0" olmali, BOS degil ────────────
# Pano iki sayi bekliyor; bos dizge gelirse satir hic cizilmez ama bu
# "olculdu, OPcache yok" ile "olculemedi"yi ayirt edilemez kilardi.
ck("eslesme yok -> '0 0'", tara("x" + NL), (0, 0))

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
