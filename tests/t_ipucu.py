"""IPUCLARI (title) — ikiz paritesi ve kendi kutumuz.

NEDEN: kullanici basina Redis satirinin GB ipucu uretimde hic gorunmedi.
Sunucu render'i title'i koyuyordu, AMA canli donguyu ciziyen JS ikizi
koymuyordu: ilk tick'te (bir dakika icinde) satir yeniden yaziliyor ve ipucu
siliniyordu. Kaynakta "hic konmamis gibi" duruyordu. Bu test o sinifi yakalar:
PHP sub-check satirinda title ureten her alanin JS ikizinde de title uretmesi
gerekir. Alan listesi KAYNAKTAN cikarilir — yeni bir ipucu alani eklenince de
kendiliginden sorar.

Ayrica: ipucu kutusu artik tarayicinin kendi balonu degil, kivilcim
ipucuyla ayni kutu (tema uyumlu). O motorun yerinde oldugu da sinanir.
"""
import io
import re
import sys

import os as _os

# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()
gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-54s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s: beklenen=%r gelen=%r" % (ad, beklenen, gelen))


# ── Iki render'in sub-check bolgeleri ──────────────────────────
php = src[src.index("$age = '<span class=\"sub-age\"'"):]
php = php[:php.index("</div>' . \"" + chr(92) + "n\";")]

js = src[src.index("const age='<span class=\"sub-age\"'"):]
js = js[:js.index("}).join('');")]

print("PHP ve JS sub-check bolgeleri: %d / %d karakter" % (len(php), len(js)))
print()


def php_alanlari(s):
    """<span class="sub-X" ...> icinde title'i hangi $c[...] besliyor."""
    a = dict(re.findall(r'<span class="(sub-\w+)"\'\s*\.\s*\(isset\(\$c\[\'(\w+)\'\]\)', s))
    a.update(dict(re.findall(r'<span class="(sub-\w+)" title="\'\s*\.\s*htmlspecialchars\(\$c\[\'(\w+)\'\]', s)))
    return a


def js_alanlari(s):
    a = dict(re.findall(r'<span class="(sub-\w+)"\'\+\(ch\.(\w+)\?\'\s*title=', s))
    a.update(dict(re.findall(r'<span class="(sub-\w+)" title="\'\+esc\(ch\.(\w+)', s)))
    return a


pa, ja = php_alanlari(php), js_alanlari(js)
print("  PHP ipucu alanlari: %s" % (pa or "-"))
print("  JS  ipucu alanlari: %s" % (ja or "-"))
print()

ck("PHP tarafi ipucu uretiyor (regex tutuyor)", len(pa) >= 3, True)
for sinif in sorted(pa):
    ck("ikiz: .%s ipucu JS'te de var" % sinif, ja.get(sinif), pa[sinif])
# Ters yon: JS'te olup PHP'de olmayan da ayrisma — ilk yuklemede gorunmez,
# tick'ten sonra belirir. O da ayni hatanin aynasi.
for sinif in sorted(ja):
    ck("ikiz: .%s ipucu PHP'de de var" % sinif, pa.get(sinif), ja[sinif])

# Alanin JSON'a girdigi de sinanir: PHP title'i uretse, JS okusa ama alan
# yayinlanmasa yine bos kalirdi. checks dizisi oldugu gibi seri hale geliyor,
# yani alan $cacheChecks'e eklenmis olmali.
for alan in sorted(set(pa.values())):
    ck("'%s' kontrol dizisine yaziliyor" % alan,
       bool(re.search(r"'" + alan + r"'\s*=>", src))           # ['alan' => ...]
       or bool(re.search(r"\['" + alan + r"'\]\s*=", src)),    # $chk['alan'] = ...
       True)

# ── Kendi ipucu kutumuz ────────────────────────────────────────
print()
ck("kutu kivilcim ipucuyla AYNI sinifi kullaniyor",
   "hintEl.className='spark-tip tip-wide'" in src, True)
ck("uzun metin saran varyant tanimli", ".spark-tip.tip-wide{" in src, True)
ck("koyu temada kutunun kendi rengi var",
   '[data-theme="dark"] .spark-tip{' in src, True)
ck("title ilk hover'da data-tip'e tasiniyor (cift balon olmasin)",
   "el.dataset.tip=s;el.removeAttribute('title');" in src, True)
# IKI BALON: tembel tasima yetmiyor. Canli dongu karti dakikada bir yeniden
# yaziyor, title'li YENI dugum geliyor; fare kipirdamadigi icin donusum
# calismiyor ve tarayici kendi balonunu da aciyor (uretimde ust uste gorundu).
ck("tasima sayfa genelinde, gozlemciyle tetikleniyor",
   "new MutationObserver" in src and "attributeFilter:['title']" in src, True)
ck("tarama butun title'lari suruyor",
   "document.querySelectorAll('[title]').forEach" in src, True)
ck("uzerinde durulan oge yeniden cizildiyse kutu gizleniyor",
   "if(hintFor&&!hintFor.isConnected)hintGizle();" in src, True)
ck("metinsiz ogede erisilebilirlik icin aria-label birakiliyor",
   "setAttribute('aria-label',s)" in src, True)
ck("kivilcim ustundeyken metin ipucu kapaniyor", "hintGizle();" in src, True)
ck("kaydirmada kutu havada kalmiyor",
   "addEventListener('scroll',hintGizle" in src, True)
ck("ipucu VAR isareti (nokta nokta alti cizili not)",
   bool(re.search(r"\.sub-note\[title\],\.sub-note\[data-tip\]\{text-decoration:underline dotted", src)), True)
# data-tip'e tasindiktan SONRA da isaret/imlec durmali: iki secici de yazilmis mi
ck("isaret data-tip halini de kapsiyor",
   src.count("[data-tip]") >= 6, True)

# ── Demo verisi: yas ipucu ham saniye olmasin ──────────────────
# Demoda 'up' alanina ham saniye gidiyordu ve ipucu "36000 ayakta" diyordu;
# kisa metin de elle yazildigi icin TR sayfasinda ingilizce kaliyordu. Ipuclari
# gorunur olunca ortaya cikti. Tek kaynak: saniye + urunun kendi yardimcilari.
print()
demo = io.open(KOK + "demo/demo.js", encoding="utf-8", errors="replace").read()
ck("demo: kisa yas urunun ageShort'undan", "c.upS=ageShort(sn)" in demo, True)
ck("demo: uzun yas (ipucu) bicimlenmis metin", "c.up=yasUzun(sn)" in demo, True)
ck("demo: elle yazilmis kisa yas metni kalmamis",
   bool(re.search(r"ck\([^)]*'\d+[dhm]'\s*,\s*\d", demo)), False)
ck("demo: kullanici Redis'i kartta var (ipucuyla)",
   "Redis · user" in demo and "accounts in use" in demo, True)
ck("demo: tavan da ipucunda", "of %s ceiling" in demo, True)

# ── Dokunmatik ─────────────────────────────────────────────────
# Dokunmatikte "ustune gelme" yok: ipucu dokunusla acilmazsa o cihazda HIC
# acilmaz. Dinleyici PASIF ve preventDefault YOK -- yoksa ipucu koydugumuz her
# oge tiklanamaz hale gelirdi (sekmeler, baglantilar).
print()
# Karakter penceresiyle degil, dinleyicinin TAMAMIYLA sinanir: pencere yontemi
# yoruma bagliydi, 2026-11-06'da eklenen aciklama {passive:true}'yu pencerenin
# disina itip testi urun dogruyken kirdi.
_m = re.search(r"addEventListener\('touchstart'[\s\S]*?\n\},\{[^\n]*\);", src)
tdok = _m.group(0) if _m else ""
ck("dokunusla aciliyor", bool(tdok), True)
ck("dinleyici pasif (kaydirmayi engellemesin)", "{passive:true}" in tdok, True)
ck("tiklamayi yutmuyor (preventDefault yok)", "preventDefault" in tdok, False)
ck("parmagin altinda asili kalmiyor (sureli kapanis)",
   "setTimeout(hintGizle" in src, True)
# Komut hucresinde dokunus ZATEN hucreyi aciyor (.expanded). Ipucu kutusu ayni
# metni tekrar ediyordu, ustelik kirpik ve secilemez halde. Mobilde olculdu
# (2026-11-06 ekran goruntusu): ikisi ust uste cikiyor. Masaustu dokunulmadi.
ck("komut hucresinde dokunus ipucusu yok",
   "if(e.target.closest&&e.target.closest('.proc-cmd')){hintGizle();return;}" in src, True)
ck("masaustu hover ipucusu duruyor",
   bool(re.search(r"mousemove[\s\S]{0,400}?hintIzle\(e\)", src)), True)

# ── Toplayici: surum onbellegi yazilabilmeli ───────────────────
# "} > tmp && mv" bloğun cikis koduna bagliydi; son satir kosullu bir echo
# ("memcached kuruluysa yaz"), memcached kalkinca 1 dondu ve onbellek bir daha
# yazilamadi. Sonuc sessiz: agir surum sorgulari HER DAKIKA kostu (olculdu:
# turun 6 sn'sinin 4.3'u) ve pano eski surumleri gosterdi.
col = io.open(KOK + "src/collector.sh", encoding="utf-8", errors="replace").read()
ck("surum onbellegi blogun cikis koduna bagli DEGIL",
   '} > "$VC.tmp" && mv' in col, False)
ck("olcut dosyanin kendisi", '[ -s "$VC.tmp" ] && mv -f "$VC.tmp" "$VC"' in col, True)
ck("tavan ayni turda, ek baglanti yok",
   "INFO keyspace\\r\\nCONFIG GET maxmemory\\r\\n" in col, True)
ck("bitis olcutu artik \\r\\n\\r\\n degil",
   "tavan(st[0]) is not None" in col, True)

# ── Yuk uyarisi: CPU + I/O faili, RAM YOK ──────────────────────
# Yuk islemciden de diskten de gelebilir; ikisi ayni satirda yazilmazsa alarm
# "15.34" deyip susuyor. RAM kasten disarida: en cok RSS tutan surec yuksek
# yukun faili degildir (mariadbd her zaman listenin basinda).
ck("PHP: yuk uyarisi I/O ekini tasiyor", "$sfxLd = $sfx . $topSfx(" in src, True)
ck("PHP: yuk metni $sfxLd kullaniyor",
   "tf('High load: %s (1m)%s', number_format($l1v, 2), $sfxLd)" in src, True)
ck("PHP: yuk uyarisinda RAM eki yok", "number_format($l1v, 2), $sfxR" in src, False)
ck("JS: yuk uyarisi I/O ekini tasiyor", "data.load1.toFixed(2),top+loadIo" in src, True)
ck("JS: I/O eki yeniden kuruluyor (cift 'ust:' olmasin)",
   "' · I/O: '+topIoTxt" in src, True)

# ── Fail adi: genel yorumlayici gizlenmesin ────────────────────
# Uretimde olculdu (2026-11-02): uyari "ust: python3 · root" diyordu, fail
# "/opt/imunify360/venv/bin/python3 -m im360.run" idi. Ad artik args'tan
# cozuluyor; TOPP/TOPR yeni bir ps TARAMASI EKLEMEDEN PS_SNAP'e bakiyor.
ck("TOPP args'li anlik goruntuden", 'TOPP=$(sort -k5,5 -rn "$PS_SNAP"' in col, True)
ck("TOPR args'li anlik goruntuden", 'TOPR=$(sort -k7,7 -rn "$PS_SNAP"' in col, True)
ck("yeni ps taramasi eklenmedi (hala iki tane)",
   len([l for l in col.splitlines() if l.startswith("ps axo ")]), 2)
ck("genel yorumlayici listesi awk'ta",
   "/^(php|python|perl|node|bash|sh|ruby|java|dash|zsh)[0-9.]*$/" in col, True)
ck("ayni liste JS'te",
   "/^(php|python|perl|node|bash|sh|ruby|java|dash|zsh)[0-9.]*$/" in src, True)

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
