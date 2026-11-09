"""CEVIRI KAPSAMI — t()/tf() cagrisinin sozlukte karsiligi var mi.

NEDEN BU TEST VAR (uretimde olculdu, 2026-11-09):
SUREC sutununun ipucu panoda INGILIZCE ve ESKI iddiayla gorundu. Sebep:
1.5.83'te sozluge ($TR) ipucunun YENI metni eklendi, ama cagri yeri eski
metinde kaldi. t() bulamadigi anahtari sessizce AYNEN dondurur --

    function t($s) { global $T; return $T[$s] ?? $s; }

-- yani hata vermez, dil degismez, yalnizca metin Ingilizce kalir. Pano
ayakta, testler yesil, ipucu yanlis. Hicbir test "bu dizgenin sozlukte
karsiligi var mi" diye sormuyordu.

Bu test onu sorar: kaynaktaki HER t('...') / tf('...') cagrisinin dizgesi
$TR'de ANAHTAR olmak zorunda. Dizge listesi KAYNAKTAN cikarilir, yani yeni
bir ipucu yazildiginda da kendiliginden sorar.

TEK SOZLUK, IKI RENDER: JS ikizi ayni $TR'yi json_encode ile aliyor
(src/index.php icinde "const TR=<?=... json_encode($TR) ...?>"), bu yuzden
tek kontrol PHP ve JS render'inin ikisini birden koruyor. O satirin yerinde
durdugu da burada sinanir -- JS kendi sozlugune gecse bu test korumasini
sessizce kaybederdi.
"""
import io
import os as _os
import re
import sys

KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()
gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-56s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s: beklenen=%r gelen=%r" % (ad, beklenen, gelen))


# ── Iki dilde AYNI olan, bilerek cevrilmeyen dizgeler ──────────
# Kisaltma ya da marka: Turkcesi de ayni. Yeni bir tane eklenirse test SORAR
# ve buraya yazmak BILINCLI bir karar olur -- sessiz Ingilizce dusus degil.
CEVRILMEZ = {'DNS', 'FTP', 'I/O'}


def coz_tek(x):
    return x.replace("\\'", "'").replace('\\\\', '\\')


def coz_cift(x):
    return x.replace('\\"', '"').replace('\\\\', '\\')


def dizgeler(s):
    """(ofset, metin) — tek ve cift tirnakli PHP/JS dizgeleri."""
    out = []
    for m in re.finditer(r"'((?:[^'\\\n]|\\.)*)'", s):
        out.append((m.start(), coz_tek(m.group(1))))
    for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', s):
        out.append((m.start(), coz_cift(m.group(1))))
    return out


# ── Sozluk siniri kaynaktan bulunur ────────────────────────────
tr_bas = src.index('$TR = [')
tr_son = src.index('\n];', tr_bas)
sozluk = src[tr_bas:tr_son]
ck("sozluk ($TR) bulundu", (tr_bas > 0, tr_son > tr_bas), (True, True))

# Anahtarlar: '...' => ya da "..." =>
anahtar = set()
for m in re.finditer(r"'((?:[^'\\\n]|\\.)*)'\s*=>", sozluk):
    anahtar.add(coz_tek(m.group(1)))
for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"\s*=>', sozluk):
    anahtar.add(coz_cift(m.group(1)))
print("  sozluk anahtari: %d" % len(anahtar))
ck("sozluk makul buyuklukte (>200 anahtar)", len(anahtar) > 200, True)

# ── Cagrilar: sozlugun KENDISI haric butun kaynak ──────────────
kod = src[:tr_bas] + src[tr_son:]
cagri = {}
for m in re.finditer(r"\b(t|tf)\(\s*'((?:[^'\\\n]|\\.)*)'", kod):
    cagri.setdefault(coz_tek(m.group(2)), 0)
    cagri[coz_tek(m.group(2))] += 1
for m in re.finditer(r'\b(t|tf)\(\s*"((?:[^"\\\n]|\\.)*)"', kod):
    cagri.setdefault(coz_cift(m.group(2)), 0)
    cagri[coz_cift(m.group(2))] += 1
print("  ayri t()/tf() dizgesi: %d" % len(cagri))
ck("cagri taramasi is gordu (>200 dizge)", len(cagri) > 200, True)

# ── ASIL IDDIA ─────────────────────────────────────────────────
eksik = sorted(k for k in cagri if k not in anahtar and k not in CEVRILMEZ)
if eksik:
    print()
    print("  SOZLUKTE KARSILIGI OLMAYAN (t() bunlari Ingilizce dondurur):")
    for k in eksik:
        print("    [%dx] %r" % (cagri[k], k[:160]))
ck("sozlukte karsiligi olmayan cagri yok", eksik, [])

# Beyaz listenin kendisi de kullanilmali: olu girdi birikmesin.
ck("cevrilmez listesinin hepsi hala cagriliyor",
   sorted(x for x in CEVRILMEZ if x not in cagri), [])

# ── Tek sozluk iki render'i besliyor ───────────────────────────
# Bu satir giderse (JS kendi sozlugune gecerse) yukaridaki kontrol yalniz
# PHP'yi korur hale gelir ve kimse farketmez. O yuzden burada sinaniyor.
ck("JS ikizi ayni $TR'yi aliyor",
   bool(re.search(r'const TR=<\?=.*json_encode\(\$TR', src)), True)
ck("JS t() bulamadigini AYNEN donduruyor (PHP ile ayni davranis)",
   "function t(s){return LANG_UI==='tr'?(TR[s]||s):s;}" in src, True)

# ── SUREC ipucu: kullanicinin istedigi bilgi URUNDE kalsin ─────
# "0 yazacaksak ipucunada 0= okuma aninda surec yok diyecekmiyiz, bu
# bilgileri hem biz unutmayalim hem uründe kalsin." (2026-11-09)
npt = [k for k in cagri if k.startswith('Processes the account has right now')]
ck("SUREC sutununun ipucusu tek bir dizgeden geliyor", len(npt), 1)
if len(npt) == 1:
    ck("ipucu '0 =' halini aciklıyor", '0 = no process at the moment of reading' in npt[0], True)
    ck("ipucu ANLIK/FARK ayrimini soyluyor",
       ('one-minute difference' in npt[0], 'this count is an instant' in npt[0]), (True, True))
    ck("ipucu bos hucreyi ayri sebebe baglıyor", 'An empty cell means LVE did not' in npt[0], True)
    ck("ipucunun Turkcesi sozlukte", npt[0] in anahtar, True)
    tr = None
    m = re.search(r"'" + re.escape(npt[0].replace("'", "\\'")) + r"'\s*\n?\s*=>\s*'((?:[^'\\]|\\.)*)'", sozluk)
    if m:
        tr = coz_tek(m.group(1))
    ck("Turkcesi de '0 =' diyor", tr is not None and '0 = okuma anında süreç yok' in tr, True)
    ck("Turkcesi FARK/ANLIK ayrimini soyluyor",
       tr is not None and 'bir dakikalık FARK' in tr and 'ANLIK' in tr, True)

# ── Bilgi (iddia degil): cagrilmayan anahtarlar ────────────────
# Degisken besleyen t($x) cagrilari var, bu yuzden "olu" demek icin yetersiz.
olu = len([k for k in anahtar if k not in cagri])
print("  bilgi: cagrida gorunmeyen anahtar %d (t($x) ile beslenenler dahil)" % olu)

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
