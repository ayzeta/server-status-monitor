"""BESLEME KESIKKEN TEPE ROZETI: "bilinmiyor" diyor mu, yoksa son olcumu mu iddia ediyor?

URETIMDE GORULDU (2026-11-25): kullanici sunucuyu yeniden baslatti; pano
"Sunucuya ulasilamiyor" diye olay yazdigi HALDE tepe rozeti "Tum sistemler
calisiyor" deyip favicon'u YESIL tuttu. Sebep: rozet, sekme basligi ve favicon
yalnizca BASARILI veriyle yaziliyordu (updateOverall), yani son olcumun
renginde doniyordu. O an pano hicbir sey olcemiyor.

KURAL: olculmemis sey olculmus gibi gosterilmez. Besleme kesikken rozet NOTR
GRI (--muted) olur, "Durum bilinmiyor" yazar, detayda SEBEP + son verinin yasi
durur; favicon da gri boyanir. Kirmizi/turuncu DEGIL -- kesinti sunucuda
olabilecegi gibi agda, CSF'de (403) ya da uyuyan sekmede de olabilir.

Bu test URUN KODUNU KAYNAKTAN CIKARIP kosar: downMsg ve markStale. Sahte DOM,
gercek mantik. Geri donus ayri kod degil -- markStale(false) rozete DOKUNMAZ,
ilk basarili tick'te updateOverall onu bastan yazar; test bunu da sabitler.
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


def blok(imza, son=NL + "}"):
    b = src.index(imza)
    e = src.index(son, b) + len(son)
    return src[b:e]


js = NL.join([
    # ── sahte DOM + yardimcilar ───────────────────────────────────────
    "function t(s){return s;}",
    "function tf(s,...a){let i=0;return s.replace(/%s/g,()=>a[i++]);}",
    "function ageShort(sn){return Math.round(sn/60)+'dk';}",
    "const O={};",
    "for(const id of ['time-val','footer-mode-txt','hdr-dot','hdr-txt','hdr-short','hdr-detail','hdr-status'])",
    "  O[id]={id,textContent:'',title:'',style:{},classList:{_s:new Set(),",
    "         add(c){this._s.add(c);},remove(c){this._s.delete(c);},has(c){return this._s.has(c);}}};",
    "const document={body:{classList:O['hdr-status'].classList._s?{_s:new Set(),",
    "   add(c){this._s.add(c);},remove(c){this._s.delete(c);},has(c){return this._s.has(c);}}:null},",
    "  documentElement:{},getElementById:id=>O[id]||null};",
    "function getComputedStyle(){return {getPropertyValue:p=>p==='--muted'?' #64748b ':''};}",
    "let ikon=null;",
    "function setStatusIcon(col,kisa){ikon=[col,kisa];}",
    "let downKind='',lastHttpStatus=null,lastGoodTime='00:17:45',lastFetchOk=Date.now()-120000;",
    # ── urun kodu ─────────────────────────────────────────────────────
    blok("function downMsg(k,s){"),
    blok("function markStale(on){"),
    # ── vakalar ───────────────────────────────────────────────────────
    "const out={msg:[],hal:[]};",
    "for(const [k,s] of [['offline',null],['403',403],['401',401],['404',404],",
    "                    ['backend',502],['http',418],['timeout',null],['conn',null],['',null]])",
    "  out.msg.push(downMsg(k,s));",
    "function hal(){return {sinif:document.body.classList.has('feed-stale'),",
    "  nokta:O['hdr-dot'].style.background||'', yazi:O['hdr-txt'].textContent,",
    "  kisa:O['hdr-short'].textContent, detay:O['hdr-detail'].textContent,",
    "  detayGorunur:O['hdr-detail'].style.display==='', ikon:ikon};}",
    # 1) hic yanit yok
    "downKind='conn';lastHttpStatus=null;markStale(true);out.hal.push(hal());",
    # 2) 403 (IP engeli)
    "downKind='403';lastHttpStatus=403;markStale(true);out.hal.push(hal());",
    # 3) sekme askidaydi: sebep YOK, yalniz yas
    "downKind='';lastHttpStatus=null;markStale(true);out.hal.push(hal());",
    # 4) veri dondu: markStale(false) rozete DOKUNMAZ (updateOverall yazar)
    "ikon=null;markStale(false);out.hal.push(hal());",
    "console.log(JSON.stringify(out));",
])
io.open(os.path.join(BURASI, "t_bilinmiyor.js"), "w", encoding="utf-8", newline=NL).write(js)
r = subprocess.run(["node", "t_bilinmiyor.js"], capture_output=True, text=True,
                   encoding="utf-8", cwd=BURASI)
if r.returncode:
    sys.exit("node hatasi: " + (r.stderr or r.stdout)[:600])
s = json.loads(r.stdout)

MSG_BEK = [
    ("cihazda ag yok", "No internet connection"),
    ("403 IP engeli", "Access forbidden (403) — IP blocked?"),
    ("401", "Authentication required (401)"),
    ("404", "Page not found (404) — install moved?"),
    ("5xx arka uc", "Server backend not responding (502)"),
    ("diger HTTP hatasi", "Server responded with error (418)"),
    ("zaman asimi", "Server did not respond (timeout)"),
    ("hic yanit yok", "Server unreachable"),
    ("sinif yok: metin de yok", ""),
]
BEK_GRI = "#64748b"
HAL_BEK = [
    ("hic yanit yok: rozet gri, sebep + yas",
     {"sinif": True, "nokta": BEK_GRI, "yazi": "Status unknown", "kisa": "Unknown",
      "detay": "Server unreachable · last data 2dk ago", "detayGorunur": True,
      "ikon": ["var(--muted)", "Unknown"]}),
    ("403: sebep IP engelini soyler",
     {"sinif": True, "nokta": BEK_GRI, "yazi": "Status unknown", "kisa": "Unknown",
      "detay": "Access forbidden (403) — IP blocked? · last data 2dk ago",
      "detayGorunur": True, "ikon": ["var(--muted)", "Unknown"]}),
    ("askidaki sekme: sebep yok, yalniz yas",
     {"sinif": True, "nokta": BEK_GRI, "yazi": "Status unknown", "kisa": "Unknown",
      "detay": "last data 2dk ago", "detayGorunur": True,
      "ikon": ["var(--muted)", "Unknown"]}),
    ("veri dondu: markStale(false) rozete dokunmaz",
     {"sinif": False, "nokta": BEK_GRI, "yazi": "Status unknown", "kisa": "Unknown",
      "detay": "last data 2dk ago", "detayGorunur": True, "ikon": None}),
]

gecen = kalan = 0


def ck(ad, gelen, bek):
    global gecen, kalan
    if gelen == bek:
        gecen += 1
        print("  %-46s -> %s" % (ad, json.dumps(gelen, ensure_ascii=False)))
    else:
        kalan += 1
        print("  BASARISIZ %s%s    beklenen=%s%s    gelen   =%s"
              % (ad, NL, json.dumps(bek, ensure_ascii=False), NL,
                 json.dumps(gelen, ensure_ascii=False)))


print("SEBEP METNI (downMsg) — olay kaydi ve rozet AYNI metni kullanir")
for (ad, bek), g in zip(MSG_BEK, s["msg"]):
    ck(ad, g, bek)

print()
print("ROZET + FAVICON (markStale)")
for (ad, bek), g in zip(HAL_BEK, s["hal"]):
    ck(ad, g, bek)

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
