"""Kart görünümlerini CSS SEÇİYOR (JS değil) — sözleşme bozulmasın.

NEDEN: I/O ve Disk kartlarındaki sekmeler gizli radyo düğmesi + <label> ile
çalışıyor. Bunun tek sebebi CSF mail eki: orada script çalışmaz, eskiden
sekmeler görünür ama ölüydü. Biri "daha kolay" diye JS'li sınıf çevirmeye
dönerse mailde yine ölü düğmeler olur ve bunu kimse fark etmez — bu test o
dönüşü yakalar.

Sınananlar (ürün gerçekten render edilerek):
  - Her kartta radyo düğmeleri var ve grup başına TAM BİR tanesi seçili.
  - Sekmeler <label for="..."> ve işaret ettikleri radyo mevcut.
  - Görünürlük kuralları ":checked ~" ile yazılmış.
  - VARSAYILAN: radyo silinse bile (bazı webmail'ler <input> siler) hesap ve
    boyut görünümü ayakta kalır — ek boş görünmez.
  - JS artık görünüm sınıflarını çevirmiyor.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys

import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NL = chr(10)
BURASI = os.path.dirname(os.path.abspath(__file__))
IS = os.path.join(BURASI, "t_sekme_is")

src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()
gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-52s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s: beklenen=%r gelen=%r" % (ad, beklenen, gelen))


# ── Kaynak düzeyinde: JS artık sınıf çevirmiyor ────────────────
js = src[src.index("const ioCard=document.getElementById('io-card')"):]
js = js[:js.index("const awBtn=")]
ck("JS görünüm sınıfı çevirmiyor",
   bool(re.search(r"classList\.(toggle|add|remove)\(['\"](io-acct|io-proc|dk-size|dk-grow|dk-w)", js)),
   False)
ck("JS seçimi hatırlıyor (localStorage)", "az-io-view" in js and "az-disk-view" in js, True)
ck("CPU/RAM seçimi de hatırlanıyor",
   "az-cpu-view" in js and "az-ram-view" in js, True)

# ── CSS: görünürlük :checked ile ───────────────────────────────
for kural in ("#iov-p:checked ~ .io-wrap .iop{display:table-row-group;}",
              "#iov-a:checked ~ .io-wrap #pt-io{display:table-row-group;}"):
    ck("CSS kuralı var: " + kural[:34], kural in src, True)
ck("disk pencereleri GROW_WINS'ten üretiliyor",
   "#dkv-<?=$w?>:checked~.proc-table #pt-dkg-<?=$w?>{display:table-row-group;}" in src, True)
# CPU/RAM kartlarında iki AYRI tablo var (süreç görünümü 5-6 sütun, hesap
# görünümü 3). Görünürlüğü yine :checked seçiyor.
for kural in ("#cpv-a:checked~.cpa{display:table;}", "#cpv-a:checked~.ptp{display:none;}",
              "#rmv-a:checked~.rma{display:table;}", "#rmv-a:checked~.ptp{display:none;}"):
    ck("CSS kuralı var: " + kural[:30], kural in src, True)
# MOBİLDE PID GİZLEME KURALI TABLOYA BAĞLI OLMALI, kartın sırasına değil:
# eskiden "1. ve 2. kart"ın ilk sütunu gizleniyordu; o kartlara hesap tablosu
# eklenince aynı kural HESAP sütununu gizliyordu.
ck("mobil PID kuralı .ptp'ye bağlı",
   ".proc-table.ptp th:nth-child(1)," in src, True)
ck("mobil kuralı kart sırasına bakmıyor",
   ".proc-row .proc-card:nth-child(1) td:nth-child(1)" in src, False)

# ── Ürünü render et ────────────────────────────────────────────
shutil.rmtree(IS, ignore_errors=True)
seed = os.path.join(IS, "seed")
os.makedirs(seed)
shutil.copy(KOK + "demo/seed.snapshot", os.path.join(seed, ".proc_snapshot"))
import datetime
bugun = datetime.date.today()
io.open(os.path.join(seed, ".diskacct_history"), "w", encoding="utf-8", newline=NL).write(
    "%s bluewave:21.300 shopfast:13.050%s%s bluewave:22.635 shopfast:13.068%s"
    % (bugun - datetime.timedelta(days=1), NL, bugun, NL))
cfg = KOK + "src/config.php"
io.open(cfg, "w", encoding="utf-8", newline=NL).write(
    "<?php" + NL + "return ['home_dir' => " + json.dumps(seed.replace("\\", "/")) + "];" + NL)
try:
    r = subprocess.run(["php", KOK + "src/index.php"], capture_output=True, timeout=120)
finally:
    os.remove(cfg)
    shutil.rmtree(IS, ignore_errors=True)
if r.returncode:
    sys.exit("php hatasi: " + r.stderr.decode("utf-8", "replace")[:300])
sayfa = r.stdout.decode("utf-8", "replace")

iov = re.findall(r'<input type="radio" name="iov" id="(iov-[ap])" class="vw-radio"( checked)?>', sayfa)
dkv = re.findall(r'<input type="radio" name="dkv" id="(dkv-[a-z0-9]+)" class="vw-radio"( checked)?>', sayfa)
ck("I/O kartında iki radyo", len(iov), 2)
ck("I/O'da tam bir tanesi seçili", sum(1 for _, c in iov if c), 1)
ck("I/O varsayılanı HESAP", [i for i, c in iov if c], ["iov-a"])
ck("disk radyoları (boyut + pencereler)", len(dkv) >= 2, True)
ck("diskte tam bir tanesi seçili", sum(1 for _, c in dkv if c), 1)
ck("disk varsayılanı BOYUT", [i for i, c in dkv if c], ["dkv-s"])

cpv = re.findall(r'<input type="radio" name="cpv" id="(cpv-[ap])" class="vw-radio"( checked)?>', sayfa)
rmv = re.findall(r'<input type="radio" name="rmv" id="(rmv-[ap])" class="vw-radio"( checked)?>', sayfa)
ck("CPU kartında iki radyo", len(cpv), 2)
ck("RAM kartında iki radyo", len(rmv), 2)
ck("CPU'da tam bir tanesi seçili", sum(1 for _, c in cpv if c), 1)
ck("RAM'de tam bir tanesi seçili", sum(1 for _, c in rmv if c), 1)
# VARSAYILAN HESAP: disk ve I/O kartlarıyla aynı. Kartın cevapladığı soru "kim
# yakıyor" ve süreç listesi onu cevaplamıyor.
ck("CPU varsayılanı HESAP", [i for i, c in cpv if c], ["cpv-a"])
ck("RAM varsayılanı HESAP", [i for i, c in rmv if c], ["rmv-a"])
# Sekme SIRASI da hesap önce (I/O kartındaki gibi): ilk <label> hesabı göstersin.
ilk_cp = re.search(r'<label for="(cpv-[ap])"', sayfa)
ilk_rm = re.search(r'<label for="(rmv-[ap])"', sayfa)
ck("CPU'da ilk sekme HESAP", ilk_cp.group(1) if ilk_cp else None, "cpv-a")
ck("RAM'de ilk sekme HESAP", ilk_rm.group(1) if ilk_rm else None, "rmv-a")
# Radyoyu silen webmail'de ":checked" hiç eşleşmez; temel kural da hesabı
# göstermeli, yoksa ek canlı sayfadan FARKLI görünür.
# SATIR BAŞINA DEMİRLİ ara: ".ptp{display:none;}" düz dizgi olarak
# "#cpv-a:checked~.ptp{display:none;}" içinde de geçiyor ve iddia boşa geçiyordu.
temel_ptp = re.compile(r'^\.ptp\{display:none;\}$', re.M)
ck("radyosuz varsayılan: süreç tablosu gizli", bool(temel_ptp.search(sayfa)), True)
ck("radyosuz varsayılan: hesap tabloları açık",
   bool(re.search(r'^\.cpa,\.rma\{display:table;\}$', sayfa, re.M)), True)
cprm = re.findall(r'<label for="(cpv-[ap]|rmv-[ap])" class="(?:cp|rm)-tab', sayfa)
ck("CPU/RAM sekmeleri de <label>",
   sorted(cprm) == sorted([i for i, _ in cpv] + [i for i, _ in rmv]), True)

etiketler = re.findall(r'<label for="(iov-[ap]|dkv-[a-z0-9]+)" class="(?:io|dk)-tab', sayfa)
ck("sekmeler <label> (düğme değil)", len(etiketler) >= 4, True)
ck("her etiket var olan bir radyoyu gösteriyor",
   sorted(set(etiketler)) == sorted(set([i for i, _ in iov] + [i for i, _ in dkv])), True)
ck("eski düğme işaretlemesi kalmamış",
   bool(re.search(r'<button[^>]*class="(io|dk)-tab', sayfa)), False)

# Radyolar silinirse (webmail <input> siler) varsayılan görünüm ayakta mı:
# ":checked" kuralları eşleşmez, geriye temel kurallar kalır.
ck("radyosuz varsayılan: süreç gövdesi gizli (.iop)", ".iop{display:none;}" in sayfa, True)
ck("radyosuz varsayılan: artış gövdeleri gizli", ".dkg,.dkh-g{display:none;}" in sayfa, True)

# ── LVE YOKSA: sekme de hesap tablosu da HİÇ ÇIKMAZ ────────────
# Ölçemediğimiz bir şeyi kullanıcıya "sende CloudLinux LVE yok" diye yazmak
# panonun işi değil; CloudLinux'suz bir sunucuda kart eskisi gibi yalnız süreç
# gösterir. Aynı anlık görüntü, yalnız LVE bölümü çıkarılmış hâliyle render
# edilip sınanıyor.
ham = io.open(KOK + "demo/seed.snapshot", encoding="utf-8").read()
kesik = re.sub(r'--- LVE per account ---\n(?:(?!^--- ).*\n)*', '', ham, flags=re.M)
ck("fikstürden LVE bölümü gerçekten çıktı",
   ("lveram " in ham, "lveram " in kesik), (True, False))
shutil.rmtree(IS, ignore_errors=True)
seed2 = os.path.join(IS, "seed")
os.makedirs(seed2)
io.open(os.path.join(seed2, ".proc_snapshot"), "w", encoding="utf-8", newline="").write(kesik)
io.open(cfg, "w", encoding="utf-8", newline=NL).write(
    "<?php" + NL + "return ['home_dir' => " + json.dumps(seed2.replace("\\", "/")) + "];" + NL)
try:
    r2 = subprocess.run(["php", KOK + "src/index.php"], capture_output=True, timeout=120)
finally:
    os.remove(cfg)
    shutil.rmtree(IS, ignore_errors=True)
if r2.returncode:
    sys.exit("php hatasi (LVE'siz): " + r2.stderr.decode("utf-8", "replace")[:300])
sayfa2 = r2.stdout.decode("utf-8", "replace")
ck("LVE'siz: CPU/RAM radyosu yok",
   bool(re.search(r'name="(cpv|rmv)"', sayfa2)), False)
ck("LVE'siz: hesap tablosu yok",
   ('id="pt-cpuacct"' in sayfa2, 'id="pt-ramacct"' in sayfa2), (False, False))
ck("LVE'siz: 'LVE gerekiyor' yazısı yok",
   ("CloudLinux LVE gerekiyor" in sayfa2, "needs CloudLinux LVE" in sayfa2), (False, False))
ck("LVE'siz: süreç tablosunu gizleyen temel kural basılmamış",
   bool(temel_ptp.search(sayfa2)), False)
# Kart yine de duruyor ve süreç listesi dolu — "sekme yok" ile "kart yok" ayrı.
ck("LVE'siz: CPU kartı ve süreç tablosu duruyor",
   ('id="cpu-card"' in sayfa2 and 'id="pt-cpu"' in sayfa2), True)
ck("LVE'siz: RAM kartı ve süreç tablosu duruyor",
   ('id="ram-card"' in sayfa2 and 'id="pt-ram"' in sayfa2), True)

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
