"""IPUCU KUTUSU KAPANIYOR MU? — dokunmatikte ekranda kilitlenme kusuru.

URETIMDE GORULDU (2026-11-22, telefonda): bellek kartindaki shmem ipucuna
dokunuldu, kutu acildi ve BIR DAHA KAPANMADI — bosluga dokunmak da, kendi
zamanlayicisi da ise yaramadi. Tek degisme yolu baska bir ipucu acmakti.

SEBEP (canli panoda yeniden uretildi, adim adim olculdu):
  1. dokunus      -> kutu acilir (opaklik 1), hintFor = o oge
  2. canli tik    -> kart yeniden cizilir, hintFor'un dugumu kopar.
                     hintTara DOKUNMATIKTE kutuyu BILEREK acik birakir
                     (okunurken kaybolmasin) ama hintFor'u null yapar.
  3. hintGizle()  -> "if(hintFor)" diye basliyordu; hintFor null oldugu icin
                     HICBIR SEY YAPMIYORDU. Kapatma yollarinin hepsi buradan
                     gectigi icin (zamanlayici, bosluga dokunus, kaydirma)
                     kutu ekranda kaldi.
Olculen sira: 1 -> opaklik 1 | 2 -> opaklik 1, hintFor yok | 3 -> opaklik 1.

Bu test URUN KODUNU KAYNAKTAN CIKARIP kosar: hintGizle ve hintTara. Kural:
KAPATMA KOSULSUZDUR. Kutuyu ACIK BIRAKMA karari yalnizca hintTara'nindir.
"""
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NL = chr(10)
BURASI = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURASI) + "/"
src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()


def satir(imza):
    b = src.index(imza)
    return src[src.rindex(NL, 0, b) + 1:src.index(NL, b)]


def blok(imza, son=NL + "}"):
    b = src.index(imza)
    e = src.index(son, b) + len(son)
    return src[b:e]


# ── Kosum betigi: urun kodu + sahte DOM ───────────────────────────────
js = NL.join([
    "let hintFor=null,hintDokunmatik=false,hintSup=false,hintBek=false;",
    "const hintEl={style:{opacity:'0'},textContent:''};",
    "let taranacak=[];",
    "const document={querySelectorAll:()=>taranacak};",
    satir("function hintGizle("),
    blok("function hintTara("),
    "const out=[];",
    "function dur(){return [hintEl.style.opacity+'', hintFor?'var':'yok'];}",
    # 1) Normal kapanis: bag duruyor
    "hintFor={isConnected:true};hintEl.style.opacity='1';",
    "hintGizle();out.push(dur());",
    # 2) KILITLENME HALI: kutu gorunur, bag kopmus (hintFor null)
    "hintFor=null;hintEl.style.opacity='1';",
    "hintGizle();out.push(dur());",
    # 3) Dokunmatikte tik yeniden cizdi: kutu ACIK KALIR, bag kopar
    "hintDokunmatik=true;hintFor={isConnected:false};hintEl.style.opacity='1';",
    "taranacak=[];hintTara();out.push(dur());",
    # 4) ... ve ardindan bosluga dokunus / zamanlayici onu KAPATIR
    "hintGizle();out.push(dur());",
    # 5) Masaustunde tik yeniden cizdi: kutu hemen kapanir
    "hintDokunmatik=false;hintFor={isConnected:false};hintEl.style.opacity='1';",
    "hintTara();out.push(dur());",
    # 6) Baglanti duruyorsa tarama kutuya dokunmaz
    "hintDokunmatik=false;hintFor={isConnected:true};hintEl.style.opacity='1';",
    "hintTara();out.push(dur());",
    # 7) title -> data-tip tasima + aria-label (metinsiz ogede)
    "const oge={_t:'Kaydı temizle',_aria:null,dataset:{},textContent:'',",
    " getAttribute(k){return k==='title'?this._t:this._aria;},",
    " setAttribute(k,v){this._aria=v;},removeAttribute(k){this._t=null;}};",
    "taranacak=[oge];hintFor=null;hintTara();",
    "out.push([oge.dataset.tip+'', (oge._t===null?'silindi':'duruyor'), oge._aria+'']);",
    "console.log(JSON.stringify(out));",
])
io.open(os.path.join(BURASI, "t_ipucukapanma.js"), "w", encoding="utf-8",
        newline=NL).write(js)
r = subprocess.run(["node", "t_ipucukapanma.js"], capture_output=True, text=True,
                   encoding="utf-8", cwd=BURASI)
if r.returncode:
    sys.exit("node hatasi: " + (r.stderr or r.stdout)[:600])
sonuc = json.loads(r.stdout)

BEKLENEN = [
    ("bag dururken kapanir", ["0", "yok"]),
    ("BAG KOPMUSKEN DE KAPANIR (kilitlenme kusuru)", ["0", "yok"]),
    ("dokunmatikte tik: kutu ACIK kalir, bag kopar", ["1", "yok"]),
    ("... sonra bosluga dokunus kapatir", ["0", "yok"]),
    ("masaustunde tik: kutu hemen kapanir", ["0", "yok"]),
    ("bag dururken tarama kutuya dokunmaz", ["1", "var"]),
    ("title data-tip'e tasinir, aria-label yazilir",
     ["Kaydı temizle", "silindi", "Kaydı temizle"]),
]

gecen = kalan = 0
for (ad, bek), g in zip(BEKLENEN, sonuc):
    g = [str(x) for x in g]
    if g == bek:
        gecen += 1
        print("  %-48s -> %r" % (ad, g))
    else:
        kalan += 1
        print("  BASARISIZ %s%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, bek, NL, g))

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
