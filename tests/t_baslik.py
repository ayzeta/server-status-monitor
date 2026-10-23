"""Baslik standardini DENETLER — iki dilde birden, derlenmis sayfadan.

Kurallar (ihlali raporlanir):
 1) Kart basligi "<Olcu> · <satir ne>" kalibinda; ustunluk sozcugu yok.
 2) Saklanan metin CUMLE buyuklugunde; kisaltmalar haric (CPU, RAM, DNS, FTP,
    SSL, PHP, MySQL, I/O, IP, WHM, SMTP...). Bagirmayi CSS yapar.
 3) Her gorunen Ingilizce basligin TR karsiligi VAR ve Ingilizcesinden farkli
    (ya da bilerek ayni olanlar listede).
"""
import io
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
src = io.open(KOK + "src/index.php", encoding='utf-8', errors='replace').read()

sozluk = {}
for m in re.finditer(r"'((?:[^'\\]|\\.)*)'\s*=>\s*'((?:[^'\\]|\\.)*)'", src):
    sozluk[m.group(1).replace("\\'", "'")] = m.group(2).replace("\\'", "'")

KISALTMA = {"CPU", "RAM", "DNS", "FTP", "SSL", "PHP", "MySQL", "I/O", "IP", "WHM",
            "SMTP", "IMAP", "POP3", "GB", "KB", "MB", "TCP", "HTTP", "HTTPS", "DB",
            "ID", "LVE", "IOPS", "RAID", "SMART"}
# Bilerek iki dilde ayni kalanlar
AYNI_OLABILIR = {"DNS", "FTP", "I/O", "MySQL · query", "PHP · account"}


def sadece_kisaltma(s):
    """Tamami kisaltmadan ibaret baslik cevrilmez; sozluk girdisi beklenmez."""
    return all(w in KISALTMA or not w[0].isalpha()
               for w in re.split(r"[ ·]+", s) if w)

basliklar = {
    "kart": re.findall(r"proc-title\">'\s*\.\s*t\('([^']+)'\)", src),
    "servis": re.findall(r'svc-name"><\?=t\(\'([^\']+)\'\)\?>', src),
    "olcu": re.findall(r'res-name"><\?=t\(\'([^\']+)\'\)\?>', src),
    "bolum": re.findall(r"<span><\?=upper\(t\('([^']+)'\)\)\?></span>", src),
    "sutun": re.findall(r"<th[^>]*>'\s*\.\s*upper\(t\('([^']+)'\)\)", src),
}

hata = 0


def cumle_mi(metin):
    """Ilk sozcuk disindaki sozcukler kucuk harfle baslamali (kisaltmalar haric)."""
    for i, w in enumerate(re.split(r"[ ·]+", metin)):
        if not w or w in KISALTMA or not w[0].isalpha():
            continue
        if i == 0:
            continue
        if w[0].isupper():
            return False
    return True


for tur, liste in basliklar.items():
    for s in dict.fromkeys(liste):
        if tur == "kart" and re.match(r"^(Top|En |Most )", s):
            hata += 1
            print("  USTUNLUK SOZCUGU  %-8s %r" % (tur, s))
        if not cumle_mi(s):
            hata += 1
            print("  BUYUK HARF        %-8s %r" % (tur, s))
        tr = sozluk.get(s)
        if tr is None and not sadece_kisaltma(s):
            hata += 1
            print("  CEVIRI YOK        %-8s %r" % (tur, s))
        elif tr is not None and tr == s and s not in AYNI_OLABILIR:
            hata += 1
            print("  CEVIRI AYNI       %-8s %r" % (tur, s))
        elif tr is not None and not cumle_mi(tr):
            hata += 1
            print("  TR BUYUK HARF     %-8s %r -> %r" % (tur, s, tr))

# Ayni olcunun iki adi olmasin: olcu karti ile kart basligi ortak terim kullanmali
olcu_tr = {s: sozluk.get(s, s) for s in basliklar["olcu"]}
for kart in basliklar["kart"]:
    sol = kart.split(" · ")[0]
    if sol in olcu_tr:
        kart_tr = sozluk.get(kart, kart).split(" · ")[0]
        if kart_tr != olcu_tr[sol]:
            hata += 1
            print("  TERIM AYRISMASI   %r: olcu karti %r, kart basligi %r"
                  % (sol, olcu_tr[sol], kart_tr))

print()
print("IHLAL: %d" % hata)
sys.exit(1 if hata else 0)
