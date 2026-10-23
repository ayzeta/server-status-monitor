"""BASLANGIC/BITIS SIMETRISI — butun etkinlikler icin, tek tek saymadan.

Kullanici haklı olarak "hepsini ben saymayayım" dedi. Bu test kaynaktan her
etkinligi bulur ve sorar: baslangicta yayinlanan her ayrinti turu icin bitiste
de karsiligi var mi? Yeni bir etkinlik eklendiginde de kendiliginde uyarir.

Kural: '<anahtar>_p' yayinlayan '<anahtar>_end_p' de yayinlamali,
       '<anahtar>_k' yayinlayan '<anahtar>_end_k' de yayinlamali.
Panoda da ikisi birden okunmali (PHP tohumu ve JS gecisi).
"""
import io
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
col = io.open(KOK + "src/collector.sh", encoding='utf-8', errors='replace').read()
php = io.open(KOK + "src/index.php", encoding='utf-8', errors='replace').read()

# Toplayicinin yayinladigi her alan
yayin = set(re.findall(r'echo "(act_[a-z]+)(_end_p|_end_k|_end|_p|_k|_fb|_n)? ', col))
etkinlikler = sorted({a for a, _ in yayin})
alanlar = {a: {ek for b, ek in yayin if b == a} for a in etkinlikler}

# act_emit ile yayinlayanlar (generic yol) da bitis alanlarini alir
emit = set(re.findall(r'act_emit (act_[a-z]+)', col))

gecen = 0
kalan = 0
print("%-16s %-22s %s" % ("ETKINLIK", "BASLANGIC", "BITIS"))
for a in etkinlikler:
    al = alanlar[a]
    bas = [e for e in ('_p', '_k') if e in al]
    bit = [e for e in ('_end_p', '_end_k') if e in al] + (['_end*'] if a in emit else [])
    print("%-16s %-22s %s" % (a, ','.join(bas) or '-', ','.join(bit) or '-'))
    for ek in bas:
        bekl = '_end' + ek
        if bekl in al or a in emit:
            gecen += 1
        else:
            kalan += 1
            print("    EKSIK: %s%s yayinliyor ama %s%s yayinlamiyor" % (a, ek, a, bekl))

# Pano her iki bitis alanini da okuyor mu (PHP tohumu + JS gecisi)
print()
for alan, phpAra, jsAra in (
        ('_end_p', "_end_p", "actEndsP"),
        ('_end_k', "_end_k", "actEndsK")):
    varYayin = any(alan in alanlar[a] for a in etkinlikler)
    if not varYayin:
        continue
    okPhp = phpAra in php
    okJs = jsAra in php
    for ad, ok in (("PHP tohumu", okPhp), ("JS gecisi", okJs)):
        if ok:
            gecen += 1
            print("  %-8s %-12s okuyor" % (alan, ad))
        else:
            kalan += 1
            print("  EKSIK: %s panoda %s tarafindan okunmuyor" % (alan, ad))

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
