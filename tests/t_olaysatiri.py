"""OLAY KAYDI SATIRI — "sorunlu" derken SEBEBİ doğru yazıyor mu?

ÜRETİMDE GÖRÜLDÜ (2026-11-20, lin): Önbellek kartı sarı yandı çünkü hesap
başına Redis örneklerinden biri (askıya alınıp geri açılan bir hesabın)
çalışmıyordu. Kartın kendi sayacı doğruydu: "2/2 aktif · 1 kullanılmıyor".
Ama olay kaydı şunu yazdı:

    Önbellek sorunlu · Redis (6379), Redis · kullanıcı

Oysa Redis (6379) bu sunucuda KULLANILMIYOR — gri satır, sayımdan düşüyor,
kartı sarı yapan o değil. Kullanıcı olay kaydına bakıp yanlış servisi aradı.
Sebep: hem PHP tohumu hem JS geçişi "ok olmayan" her satırı sebep sayıyordu;
'unknown' (kullanılmıyor / kurulu değil / doğrulanamadı) ayıklanmıyordu.

İKİNCİ KUSUR, aynı yerde: PHP tohumu 'operational' OLMAYAN her kartı sorun
sayıyordu — 'unused' (ölçülebilir hiçbir kontrolü olmayan kart) dahil. DNS'i
dışarıda olan ya da Redis/Memcached kullanmayan bir kurulumda sayfa her
açıldığında "DNS sorunlu" diye uydurma bir alarm yazılıyordu.

ÜÇÜNCÜ KUSUR: JS geçiş tablosunda 'unused' else'e düşüyordu, yani bir kart
ölçülemez hale geldiğinde "Önbellek geri geldi" diye YEŞİL yazıyordu.

Bu test ÜRÜN KODUNU KAYNAKTAN ÇIKARIP koşar: PHP tarafında svcBadTxt() ve
tohum döngüsü, JS tarafında svcBad() ve geçiş tablosu. Fikstürün ilk vakası
panonun KENDİ canlı ?json çıktısından alınmıştır (2026-11-20 00:19; yalnız
hesap adı kurgusal).
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NL = chr(10)
BURASI = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURASI) + "/"
src = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()


def cikar(imza, son=NL + "}"):
    b = src.index(imza)
    e = src.index(son, b) + len(son)
    return src[b:e]


def satir(imza):
    b = src.index(imza)
    return src[src.rindex(NL, 0, b) + 1:src.index(NL, b)]


# ── Fikstürler ────────────────────────────────────────────────────────
# GERÇEK vaka: canlı panonun 'cache' bölümü (hesap adı kurgusal).
ONBELLEK = [
    {"label": "Redis (6379)", "ok": False, "unknown": True, "note": "not in use"},
    {"label": "Redis · user", "ok": False, "warn": True, "note": "364/365 · gama",
     "who": "gama"},
    {"label": "OPcache", "ok": True, "note": "154 pools"},
]
KONTROL_VAKA = [
    ("gerçek Önbellek kartı: sebep yalnız kullanıcı Redis'i",
     ONBELLEK, " · Redis · user (gama)"),
    ("kullanılmıyor arada: sebep listesine girmez",
     [{"label": "A", "ok": False}, {"label": "B", "ok": False, "unknown": True},
      {"label": "C", "ok": False}], " · A, C"),
    ("üç arıza + bir kullanılmıyor: +N'yi şişirmez",
     [{"label": "A", "ok": False}, {"label": "B", "ok": False},
      {"label": "C", "ok": False}, {"label": "D", "ok": False, "unknown": True}],
     " · A, B +1"),
    ("dört arıza: iki ad + kalan sayı",
     [{"label": "A", "ok": False}, {"label": "B", "ok": False},
      {"label": "C", "ok": False}, {"label": "D", "ok": False}], " · A, B +2"),
    ("hepsi kullanılmıyor: sebep yok",
     [{"label": "A", "ok": False, "unknown": True},
      {"label": "B", "ok": False, "unknown": True}], ""),
    ("hepsi sağlam: sebep yok", [{"label": "A", "ok": True}], ""),
    ("saglam kontrolun who'su satira girmez",
     [{"label": "A", "ok": True, "who": "delta"}, {"label": "B", "ok": False}], " · B"),
    ("iki adlı who olduğu gibi geçer",
     [{"label": "Redis · user", "ok": False, "who": "gama teta +3"}],
     " · Redis · user (gama teta +3)"),
]

# Tohum döngüsü: kart durumu -> yazılan olaylar
TOHUM_VAKA = [
    ("çalışan kart olay yazmaz", "Cache", "operational", ONBELLEK, []),
    ("kullanılmayan kart olay YAZMAZ", "DNS", "unused",
     [{"label": "DNS TCP (53)", "ok": False, "unknown": True}], []),
    ("sorunlu kart: sebep yalnız gerçek arıza", "Cache", "degraded", ONBELLEK,
     [["warn", "Cache degraded · Redis · user (gama)"]]),
    ("çökmüş kart: kırmızı ve iki ad", "Mail services", "offline",
     [{"label": "SMTP (25)", "ok": False}, {"label": "IMAP (143)", "ok": False},
      {"label": "POP3 (110)", "ok": False, "unknown": True}],
     [["err", "Mail services went offline · SMTP (25), IMAP (143)"]]),
]

# JS geçiş tablosu: önceki durum -> yeni durum
GECIS_VAKA = [
    ("çalışır -> sorunlu: sarı, sebepli", "cache", "operational", "degraded",
     ONBELLEK, [["warn", "Cache degraded · Redis · user (gama)"]]),
    ("sorunlu -> kullanılmıyor: HİÇBİR ŞEY yazılmaz", "cache", "degraded", "unused",
     [{"label": "Redis (6379)", "ok": False, "unknown": True}], []),
    ("kullanılmıyor -> çalışır: geri geldi", "cache", "unused", "operational",
     [{"label": "OPcache", "ok": True}], [["ok", "Cache restored"]]),
    ("çökmüş -> sorunlu: 'geri geldi' DEĞİL", "cache", "offline", "degraded",
     ONBELLEK, [["warn", "Cache degraded · Redis · user (gama)"]]),
    ("durum değişmedi: olay yok", "cache", "degraded", "degraded", ONBELLEK, []),
]

GIRDI = {
    "kontrol": [c for _, c, _ in KONTROL_VAKA],
    "tohum": [{"ad": a, "durum": d, "checks": c} for _, a, d, c, _ in TOHUM_VAKA],
    "gecis": [{"anahtar": k, "onceki": o, "simdi": s, "checks": c}
              for _, k, o, s, c, _ in GECIS_VAKA],
}
io.open(os.path.join(BURASI, "t_olaysatiri_in.json"), "w", encoding="utf-8").write(
    json.dumps(GIRDI, ensure_ascii=False))

# ── PHP tarafı: svcBadTxt + tohum döngüsü (ÜRÜNDEN) ───────────────────
php = NL.join([
    "<?php",
    "function t($s){ return $s; }",
    "function tf($s, ...$a){ return vsprintf($s, $a); }",
    cikar("function svcBadTxt("),
    "$in = json_decode(file_get_contents('t_olaysatiri_in.json'), true);",
    "$out = ['kontrol' => [], 'tohum' => []];",
    "foreach ($in['kontrol'] as $c) $out['kontrol'][] = svcBadTxt($c);",
    "foreach ($in['tohum'] as $k) {",
    "  $seedLogs = [];",
    "  $svcSeed  = [$k['ad'] => [$k['durum'], $k['checks']]];",
    cikar("foreach ($svcSeed as $sName => $sInf) {"),
    "  $out['tohum'][] = array_map(fn($l) => [$l['type'], $l['msg']], $seedLogs);",
    "}",
    "echo json_encode($out, JSON_UNESCAPED_UNICODE);",
])
io.open(os.path.join(BURASI, "t_olaysatiri.php"), "w", encoding="utf-8", newline=NL).write(php)
r = subprocess.run(["php", "t_olaysatiri.php"], capture_output=True, text=True,
                   encoding="utf-8", cwd=BURASI)
if r.returncode:
    sys.exit("php hatasi: " + (r.stderr or r.stdout)[:600])
php_sonuc = json.loads(r.stdout)

# ── JS tarafı: svcBad + geçiş tablosu (ÜRÜNDEN) ───────────────────────
js = NL.join([
    "function t(s){return s;}",
    "function tf(s,...a){let i=0;return s.replace(/%s/g,()=>a[i++]);}",
    cikar("function svcBad(g){"),
    "const inp=JSON.parse(require('fs').readFileSync('t_olaysatiri_in.json','utf8'));",
    "const out={kontrol:[],gecis:[]};",
    "for(const c of inp.kontrol) out.kontrol.push(svcBad({checks:c}));",
    "for(const g of inp.gecis){",
    "  const logs=[];",
    "  const addLog=(type,msg)=>logs.push([type,msg]);",
    "  const prev={}; prev[g.anahtar]=g.onceki;",
    "  const data={}; data[g.anahtar]={status:g.simdi,checks:g.checks};",
    "  const now='00:00';",
    satir("const names={web:'Web server'"),
    cikar("['web','mail','dns','sec','db','cache','ftp'].forEach(k=>{", NL + "  });"),
    "  out.gecis.push(logs);",
    "}",
    "console.log(JSON.stringify(out));",
])
io.open(os.path.join(BURASI, "t_olaysatiri.js"), "w", encoding="utf-8", newline=NL).write(js)
r = subprocess.run(["node", "t_olaysatiri.js"], capture_output=True, text=True,
                   encoding="utf-8", cwd=BURASI)
if r.returncode:
    sys.exit("node hatasi: " + (r.stderr or r.stdout)[:600])
js_sonuc = json.loads(r.stdout)

# ── Karşılaştırma ─────────────────────────────────────────────────────
gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-52s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s%s    beklenen=%r%s    gelen   =%r"
              % (ad, NL, beklenen, NL, gelen))


print("SEBEP LISTESI (PHP svcBadTxt)")
for (ad, _, bek), g in zip(KONTROL_VAKA, php_sonuc["kontrol"]):
    ck(ad, g, bek)

print()
print("SEBEP LISTESI (JS svcBad) — PHP ile AYNI olmali")
for (ad, _, bek), g in zip(KONTROL_VAKA, js_sonuc["kontrol"]):
    ck("ikiz: " + ad, g, bek)

print()
print("TOHUM DONGUSU (PHP, sayfa acilisinda yazilan olaylar)")
for (ad, _, _, _, bek), g in zip(TOHUM_VAKA, php_sonuc["tohum"]):
    ck(ad, [list(x) for x in g], [list(x) for x in bek])

print()
print("GECIS TABLOSU (JS, canli tick)")
for (ad, _, _, _, _, bek), g in zip(GECIS_VAKA, js_sonuc["gecis"]):
    ck(ad, [list(x) for x in g], [list(x) for x in bek])

print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
