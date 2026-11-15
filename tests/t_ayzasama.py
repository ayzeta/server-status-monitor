"""AYZETA BACKUP ROZETI — is TURU degil, is ASAMASI.

NEDEN: Ayzeta Backup 2.99.57'de kancanin isinde SIRA cevrildi. Once arsiv
denetimi, sonra eksik aktarim. Is turu ('kind') hala "scan", ama is denetim
bittikten sonra da saatlerce "running" kaliyor; o saatlerde yaptigi sey
tamamlama ya da saat beklemesi. Eski eslememizde rozet o sure boyunca
"ARSIV DENETIMI" yazardi — ustelik rozete EN ESKI canli is yazildigi icin
bekleyen scan isi rozeti kilitleyip o sirada baslayan gercek yedeklemeyi
golgelerdi. Arac 2.99.57'de 'asama' alanini ekledi; dogru etiket oradan
kuruluyor.

OLCUM (2026-11-15, aracin kendi oturumundan yazili teyit, worker.php 2.99.58
satir numaralariyla): "denetim" arsivleri OKUYAN HER scan isinde (elle
baslatilan "Arsivleri denetle" dahil), "yukleyici" yalnizca cPanel yukleyicisini
bekleyen kanca isinde, "tamamlama" scan icindeki tamamlama adiminda, "bekliyor"
saat araligi disinda hem scan icindeki tamamlamada hem elle "tamamla" isinde.
Obur 16 turde ve 2.99.56 oncesi kayitlarin hepsinde alan YOK. Is bitince alan
SILINMIYOR, son deger kaliyor — bu yuzden bitmis iste asama'ya bakilmaz.

BU TEST NE SINAR, NE SINAMAZ: burada sinanan sey bizim kendi eslememiz ve
jetonlarin sozlukte karsiligi olmasi — hepsi KAYNAKTAN cikariliyor. Gercek
meta.json'u ayristiran kural HENUZ sinanmadi: arsiv denetimi disindaki
asamalarin gercek dokumu bir sonraki planli cPanel yedeginden sonra gelecek.
Fiksturu kendimiz yazmiyoruz — kendi varsayimimizi dogrulayan test kanit
degildir (2026-11-01, Redis sayimi: testler yesildi, uretimde 371 ornegin
hepsine "calismiyor" dedik). Ornekler gelince buraya ayristirma iddialari
eklenecek.
"""
import io
import os as _os
import re
import sys

KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

col = io.open(KOK + "src/collector.sh", encoding="utf-8", errors="replace").read()
php = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()
gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
    else:
        kalan += 1
        print("  BASARISIZ %s: beklenen=[%r] gelen=[%r]" % (ad, beklenen, gelen))


def sozluk(ad):
    """Tabloyu URUN KODUNDAN cikarip calistirir (kopyasini degil)."""
    m = re.search(r"^%s = \{.*?^\}" % ad, col, re.S | re.M)
    if not m:
        return None
    yer = {}
    exec(compile(m.group(0), "<collector.sh:%s>" % ad, "exec"), yer)
    return yer[ad]


# ── Esleme tablolari ────────────────────────────────────────────────────
GRUP = sozluk("GRUP")
ASAMA = sozluk("ASAMA")
ck("GRUP tablosu cikarildi", GRUP is not None, True)
ck("ASAMA tablosu cikarildi", ASAMA is not None, True)
GRUP = GRUP or {}
ASAMA = ASAMA or {}

# Arac 2026-11-15'te 18 is turu oldugunu yazili teyit etti. Tur eklenirse
# eslesmeyen is SESSIZCE atlanir (rozet hic cikmaz) — en sinsi hata bicimi.
ck("18 is turu", len(GRUP), 18)
ck("scan hala arsiv denetimi grubunda", GRUP.get("scan"), "archive check")
# 'tamamla' artik "backup" DEGIL: aracin kendi arayuzu bu turu her surumde
# "eksik aktarim" diye adlandiriyor (ar.js isTurAdi -> jobs.kindTamamla).
ck("tamamla eksik aktarim grubunda", GRUP.get("tamamla"), "missing transfer")

ck("scan+denetim arsiv denetimi", ASAMA.get(("scan", "denetim")), "archive check")
ck("scan+tamamlama eksik aktarim", ASAMA.get(("scan", "tamamlama")), "missing transfer")
ck("scan+bekliyor sira bekliyor", ASAMA.get(("scan", "bekliyor")), "waiting for window")
ck("scan+yukleyici aktarici bekleniyor",
   ASAMA.get(("scan", "yukleyici")), "waiting for transporter")
ck("tamamla+bekliyor sira bekliyor",
   ASAMA.get(("tamamla", "bekliyor")), "waiting for window")
ck("tamamla+tamamlama eksik aktarim",
   ASAMA.get(("tamamla", "tamamlama")), "missing transfer")
# Aracin saydigi dort asamanin HEPSI scan icin karsilanmali.
ck("scan'in dort asamasi da karsilanmis",
   sorted(a for (k, a) in ASAMA if k == "scan"),
   ["bekliyor", "denetim", "tamamlama", "yukleyici"])

# ── Alan yoksa eski davranis ────────────────────────────────────────────
# 16 turde ve eski kayitlarda 'asama' yok. Varsayilan grup OLMAZSA rozet o
# islerde bos etiketle cikar.
ck("alan yoksa eski etikete dusuluyor",
   'ASAMA.get((m.get("kind"), asama), grup)' in col, True)
ck("asama bos string'e normalize ediliyor",
   'asama = str(m.get("asama") or "")' in col, True)

# ── 'scan' ve 'tamamla'da kapsam 'user'a DUSMEZ ─────────────────────────
# O iki tur sunucu genelinde kosuyor ve 'user' hesap adi degil: scan'de hedef
# adlari, kancanin tamamlamasinda isin kendi adi. Hesap adinin beklendigi yere
# yaziliyor ve 28 karakterde kesiliyordu.
ck("kapsam once current",
   'best_scope = (m.get("current") or "").strip()' in col, True)
ck("scan ve tamamla user'a dusmuyor",
   'if not best_scope and m.get("kind") not in ("scan", "tamamla"):' in col, True)

# ── Jetonlarin sozlukte karsiligi ───────────────────────────────────────
# Collector bosluklari "_" yapiyor, PHP/JS tarafi geri ceviriyor; cevrilen
# metin $TR anahtari olmali. JS ikizi ayni $TR'yi kullaniyor (TR=json_encode),
# bu yuzden tek sozluk iki tarafi da kapatiyor.
ck("collector bosluklari alt cizgiye ceviriyor",
   'best_kind.replace(" ", "_")' in col, True)
ck("PHP alt cizgiyi geri ceviriyor",
   "t(str_replace('_', ' ', $aK))" in php, True)
ck("JS ikizi de ceviriyor", "t(kd.replace(/_/g,' '))" in php, True)
for jeton in sorted(set(list(ASAMA.values()) + list(GRUP.values()))):
    ck("sozlukte: " + jeton, ("'%s' =>" % jeton) in php, True)

# ── 2.99.58 TUZAGI: surdurulen iste finished_at eski kosudan kaliyor ────
# Arac bildirdi (2026-11-15): durdurulup surdurulen iste state "running" iken
# finished_at DOLU kalabiliyor; 2.99.59'da siliniyor ama sunucuda henuz o yok.
# Bizi kirmamasinin tek sebebi finished_at'i YALNIZCA 'finished' dosyasi varken
# okumamiz. O kosul kalkarsa suren is "bitti" diye rozete yazilir.
i_bitti = col.find('bitti = os.path.join(d, "finished")')
i_var = col.find("if os.path.exists(bitti):")
i_fa = col.find('fa = mb.get("finished_at")')
ck("finished_at okunuyor", i_fa > 0, True)
ck("finished_at YALNIZCA 'finished' dosyasi varken okunuyor",
   0 < i_bitti < i_var < i_fa, True)
ck("finished_at bir kez okunuyor", col.count('mb.get("finished_at")'), 1)
# Bitmis is canli listeye DE girmemeli: arac is bitince 'asama' alanini
# silmiyor, son deger kaliyor.
ck("finished dali canli taramaya devam etmiyor",
   bool(re.search(r"if os\.path\.exists\(bitti\):.*?\n        continue\n", col, re.S)), True)

# ── GERCEK KAYITLA AYRISTIRMA ───────────────────────────────────────────
# tests/ornek/ayz_meta_bekliyor.json, 2026-11-15'te sunucudaki CANLI kanca
# isinin meta.json'udur (2.99.58). Degistirilenler yalnizca adlar: alti hesap
# adi kurgusalla ("bluewave" ...), iki hedef kimligi ayni uzunlukta kurgusal
# jetonla. Alan adlari, turleri ve degerleri oldugu gibi.
#
# Bu kayit tam da ulasamadigimiz asamayi tasiyor: asama "bekliyor", current ""
# ve finished_at DOLU iken state "running" (2.99.58'in bildirdigi tuzak;
# is klasorunde 'finished' dosyasi YOK).
import json
import shutil
import subprocess
import tempfile
import time

blok = re.search(r"^import json, os, sys, time$.*?^PYEOF$", col, re.S | re.M)
ck("collector'un python blogu cikarildi", blok is not None, True)
ornek = json.load(io.open(KOK + "tests/ornek/ayz_meta_bekliyor.json",
                          encoding="utf-8"))
ck("ornek gercekten bekleyen kanca isi",
   (ornek["kind"], ornek["asama"], ornek["current"], ornek["state"]),
   ("scan", "bekliyor", "", "running"))
ck("ornekte tuzak var: calisirken finished_at dolu",
   isinstance(ornek.get("finished_at"), int) and ornek["finished_at"] > 0, True)


def kos(meta, bitti=False):
    """Urun kodunu KAYNAKTAN cikarip gercek kayit uzerinde kosar."""
    tmp = tempfile.mkdtemp()
    try:
        py = _os.path.join(tmp, "blok.py")
        io.open(py, "w", encoding="utf-8").write(blok.group(0)[:-len("\nPYEOF")])
        jobs = _os.path.join(tmp, "jobs", meta["id"])
        _os.makedirs(jobs)
        io.open(_os.path.join(jobs, "meta.json"), "w", encoding="utf-8").write(
            json.dumps(meta, ensure_ascii=False))
        if bitti:
            io.open(_os.path.join(jobs, "finished"), "w").write("")
        c = subprocess.run([sys.executable, py, _os.path.dirname(jobs)],
                           capture_output=True, text=True, encoding="utf-8")
        return (c.stdout or "").strip().split()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Canlilik olcutu MAKINEYE bagli (pid + /proc/<pid>/cmdline), bu yuzden
# testte pid 0'a alinip 'updated' bugune tasiniyor — kodun pid 0 dali zaten
# "son yazma 600 sn'den taze mi" diye bakiyor. Ayristirilan alanlar (kind,
# asama, current, user, started, finished_at) gercek kayittaki degerleridir.
canli = dict(ornek, pid=0, updated=int(time.time()))
cikti = kos(canli)
ck("dort alan basildi", len(cikti), 4)
if len(cikti) == 4:
    yas, kapsam, fin, tur = cikti
    ck("yas pozitif", yas.isdigit() and int(yas) > 0, True)
    # ASIL IDDIA: etiket artik "arsiv denetimi" degil.
    ck("gercek kayitta etiket sira bekliyor", tur, "waiting_for_window")
    # Gercek kayitta current "" ve user "GoogleDrive, Storage Box · otomatik
    # (yedekleme kancasi)". Eski kuralla rozete "GoogleDrive,Storage_Box__ot"
    # yazilirdi -- bu iddia onun geri gelmesini engelliyor.
    ck("beklerken kapsam yazilmiyor", kapsam, "-")
    # TUZAK KILIDI: 'finished' dosyasi yokken bayat finished_at ASLA
    # "bitti" diye yayinlanmaz. Bu satir kirmizi yanarsa suren yedekleme
    # panoda "bitti" gorunuyor demektir.
    ck("calisirken bitis damgasi yayinlanmiyor", fin, "-")

# Ayni kayit, 'asama' alani silinmis: 2.99.56 oncesi kayitlarin taklidi.
# Baska hicbir alan ellenmedi.
eski = dict(canli)
del eski["asama"]
cikti2 = kos(eski)
ck("alan yoksa dort alan basildi", len(cikti2), 4)
if len(cikti2) == 4:
    ck("alan yoksa eski etiket", cikti2[3], "archive_check")
    # Kapsam kurali asama'ya DEGIL ture bagli: alan hic yokken de 'user'a
    # dusulmuyor. Dusseydi burada "GoogleDrive,Storage_Box__ot" cikardi.
    ck("alan yoksa da kapsam yazilmiyor", cikti2[1], "-")

# Ayni kayit + 'finished' dosyasi: bitmis isin damgasi OKUNUR. Boylece
# yukaridaki "-" iddiasi "hic okumuyoruz" degil, "dogru kosulda okuyoruz".
cikti3 = kos(canli, bitti=True)
ck("bitmis iste dort alan basildi", len(cikti3), 4)
if len(cikti3) == 4:
    ck("bitmis iste damga okunuyor", cikti3[2], str(ornek["finished_at"]))
    ck("bitmis is canli sayilmiyor", cikti3[0], "-")
    ck("bitmis iste asama'ya bakilmiyor", cikti3[3], "archive_check")
    # Bitmis iste 'current' HER ZAMAN bos: kural orada da gecerli olmazsa
    # biten her denetimin "bitti" cipi hedef adlarini yazar.
    ck("bitmis iste de kapsam yazilmiyor", cikti3[1], "-")

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
