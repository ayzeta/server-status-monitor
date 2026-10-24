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

# ── CSS: görünürlük :checked ile ───────────────────────────────
for kural in ("#iov-p:checked ~ .io-wrap .iop{display:table-row-group;}",
              "#iov-a:checked ~ .io-wrap #pt-io{display:table-row-group;}"):
    ck("CSS kuralı var: " + kural[:34], kural in src, True)
ck("disk pencereleri GROW_WINS'ten üretiliyor",
   "#dkv-<?=$w?>:checked~.proc-table #pt-dkg-<?=$w?>{display:table-row-group;}" in src, True)

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

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
