"""YOKLUK ARIZA DEĞİLDİR — önbellek kontrollerinin karar tablosu.

Pano eskiden "port kapalı = hata" diyordu. Redis ya da Memcached kullanmayan
her sunucuda kart kırmızı yanıyor, başlıkta "Sorun tespit edildi · Önbellek
Çevrimdışı" yazıyordu — kullanılmayan bir şey için. Artık kapalı portun anlamı
systemd'nin NİYETİNE bakılarak belirleniyor.

Sınananlar:
  A) collector: "unit <ad> <dosya> <etkinlik>" satırı. systemctl özellikleri
     verilen sırayla basmıyor; satır blok bitince yazılmalı (bu hata bir kez
     yapıldı: UnitFileState okunmadan basılıyordu, alan boş kalıyordu).
  B) pano: port kapalı +
        enabled        -> ARIZA (kırmızı)
        disabled/yok   -> kullanılmıyor (gri, sayımdan düşer)
        bilgi yok      -> doğrulanamadı (gri) — kırmızı DEĞİL
     ve hepsi grideyse grup rozeti 'Kullanılmıyor', başlık kırmızıya dönmez.
  C) kullanıcı başına Redis: tam sayıda yeşil, eksikse SARI ve yanıt vermeyen
     hesapların adı, hiçbiri yanıtlamıyorsa kırmızı.
"""
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys

import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NL = chr(10)
BURASI = os.path.dirname(os.path.abspath(__file__))
IS = os.path.join(BURASI, "t_onbellek_is")
gecen = kalan = atlanan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-50s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s:\n    beklenen=%r\n    gelen   =%r" % (ad, beklenen, gelen))


# ════════ A) collector'un awk'ı ════════════════════════════════
src = io.open(KOK + "src/collector.sh", encoding="utf-8", errors="replace").read()
b = src.index("    | awk '# Ozellikler VERILEN SIRAYLA")
e = src.index("END             {bas()}'", b) + len("END             {bas()}")
awk_prog = src[b + src[b:].index("'") + 1:e]
AWKF = os.path.join(BURASI, "t_unit.awk")
io.open(AWKF, "w", encoding="utf-8", newline=NL).write(awk_prog)


def awk_calistir(metin):
    r = subprocess.run(["awk", "-f", AWKF], input=metin, capture_output=True, text=True)
    return r.stdout.strip()


ck("awk: normal sıra", awk_calistir(NL.join([
    "Id=redis.service", "UnitFileState=enabled", "ActiveState=active", ""])),
   "unit redis enabled active")
# Asıl tuzak: özellikler ters sırada gelirse eski kod alanı boş bırakıyordu.
ck("awk: ters sıra (UnitFileState sonra)", awk_calistir(NL.join([
    "Id=redis.service", "ActiveState=inactive", "UnitFileState=disabled", ""])),
   "unit redis disabled inactive")
ck("awk: kurulu olmayan birim -> notfound", awk_calistir(NL.join([
    "Id=memcached.service", "UnitFileState=", "ActiveState=inactive", ""])),
   "unit memcached notfound inactive")
ck("awk: iki birim, son blokta boş satır yok", awk_calistir(NL.join([
    "Id=redis.service", "UnitFileState=disabled", "ActiveState=inactive", "",
    "Id=memcached.service", "UnitFileState=masked", "ActiveState=inactive"])),
   NL.join(["unit redis disabled inactive", "unit memcached masked inactive"]))
os.remove(AWKF)

# ════════ A2) userredis: ps görüntüsünden sayım ════════════════
# SOKET YOKLAMASI YOK. Eski sürüm 371 sokete tek tek PING atıyordu: sağlıklı
# halde ~0.1 s ama yanıt vermeyen her örnek 0.3 s eklediği için en kötü hal
# 111 saniyeydi — dakikalık cron için kabul edilemez. Şimdi tanımlı sayısı
# dizinden, ayakta sayısı ve bellek zaten alınmış ps görüntüsünden geliyor.
b = src.index('awk -v tanimli="$UR_UNITS" ' + chr(39))
b = src.index(chr(39), b) + 1
e = src.index("}" + chr(39) + ' "$PS_SNAP"', b) + 1
URF = os.path.join(BURASI, "t_userredis.awk")
PSF = os.path.join(BURASI, "t_userredis.ps")
io.open(URF, "w", encoding="utf-8", newline=NL).write(src[b:e])


def ur(tanimli, satirlar):
    io.open(PSF, "w", encoding="utf-8", newline=NL).write(NL.join(satirlar) + NL)
    r = subprocess.run(["awk", "-v", "tanimli=" + tanimli, "-f", URF, PSF],
                       capture_output=True, text=True)
    return r.stdout.strip()


def pr(pid, user, rss, args):
    """PS_SNAP biçimi: pid state user etimes pcpu pmem rss args"""
    return "%d S %s 5000 0.1 0.2 %d %s" % (pid, user, rss, args)


KUL = ("/usr/bin/redis-server --port 0 --unixsocketperm 700 "
       "--unixsocket /home/%s/.cagefs/tmp/redis.sock --maxmemory 64mb")
# Ortak Redis de "redis-server" adıyla koşar; kullanıcı örnekleriyle
# KARIŞMAMALI (bu yüzden eşleşme --unixsocket + cagefs yolu üzerinden).
ORTAK = pr(999, "redis", 10240, "/usr/bin/redis-server 127.0.0.1:6379")

ck("userredis: tam + bellek (ortak Redis sayılmaz)",
   ur("alfa beta gama", [ORTAK,
                         pr(1, "alfa", 6400, KUL % "alfa"),
                         pr(2, "beta", 6400, KUL % "beta"),
                         pr(3, "gama", 6400, KUL % "gama")]),
   NL.join(["userredis 3 3", "userredis_mem 18"]))
ck("userredis: duranın ADI",
   ur("alfa beta gama", [pr(1, "alfa", 6400, KUL % "alfa"),
                         pr(2, "beta", 6400, KUL % "beta")]),
   NL.join(["userredis 2 3", "userredis_mem 12", "userredis_bad gama"]))
ck("userredis: tanımlı yoksa bölen 0",
   ur("", [pr(1, "alfa", 6400, KUL % "alfa"), pr(2, "beta", 6400, KUL % "beta")]),
   NL.join(["userredis 2 0", "userredis_mem 12"]))
ck("userredis: böyle bir yapı yoksa çıktı yok", ur("", [ORTAK]), "")
# Hesap adı SOKET YOLUNDAN okunur: süreç başka kullanıcıyla koşsa da (ya da
# ikinci ev dizinindeyse) birim adıyla eşleşmeli. Yoksa pano ayakta olan
# herkesi "çalışmıyor" sanar — en kötü türden yanlış alarm.
ck("userredis: ad ps kullanıcısından değil yoldan",
   ur("delta", [pr(1, "root", 6400,
                   KUL.replace("/home/%s/", "/home3/delta/"))]),
   NL.join(["userredis 1 1", "userredis_mem 6"]))
os.remove(URF)
os.remove(PSF)

# ════════ B/C) panonun kararı (ürün render edilerek) ═══════════
# Gerçekten 6379/11211 dinleyen bir makinede bu durumlar oluşmaz; o zaman
# iddia ürünü değil makineyi ölçerdi.
def port_acik(p):
    s = socket.socket(); s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", p)); return True
    except Exception:
        return False
    finally:
        s.close()


if port_acik(6379) or port_acik(11211):
    print("  ATLANDI: bu makinede 6379/11211 dinleniyor, kapalı port durumu kurulamıyor")
    atlanan = 1
else:
    taban = io.open(KOK + "demo/seed.snapshot", encoding="utf-8", errors="replace").read()
    # Tohumun KENDI "Root checks" bolumu atilir: test kendi satirlarini koyuyor.
    # (Tohuma bolum eklenince iki bolum birden okunuyordu ve test, urun degil
    #  tohum degisikligi yuzunden kirmizi yaniyordu.)
    taban = re.sub(r"\n--- Root checks ---\n(?:.|\n)*$", "\n", taban)

    def render(root_satirlari):
        shutil.rmtree(IS, ignore_errors=True)
        seed = os.path.join(IS, "seed")
        os.makedirs(seed)
        snap = taban + NL + "--- Root checks ---" + NL + NL.join(root_satirlari) + NL
        io.open(os.path.join(seed, ".proc_snapshot"), "w", encoding="utf-8",
                newline=NL).write(snap)
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
        g = r.stdout.decode("utf-8", "replace")
        import html as _h
        i = g.index('id="ch-cache"')
        kart = _h.unescape(g[i:i + 2600])
        rozet = re.search(r'id="bd-cache"[^>]*>([^<]*)<', _h.unescape(g))
        sinif = re.search(r'class="badge ([a-z-]+)" id="bd-cache"', g)
        sayac = re.search(r'id="sk-cache">([^<]*)<', _h.unescape(g))
        return kart, (rozet.group(1) if rozet else ""), (sinif.group(1) if sinif else ""), \
               (sayac.group(1).strip() if sayac else "")

    def chip(kart, etiket):
        """O etikete ait satırın nokta sınıfı ve notu."""
        m = re.search(r'<span class="sub-dot ([a-z]+)"></span>'
                      r'<span class="sub-lbl">' + re.escape(etiket) +
                      r'(?:<[^>]*>[^<]*</span>)?</span><span class="sub-note"[^>]*>([^<]*)<', kart)
        return (m.group(1), m.group(2)) if m else ("YOK", "YOK")

    def ipucu(kart, etiket):
        """Notun title'ı — kısaltılan listenin tamamı orada durmalı."""
        m = re.search(r'<span class="sub-lbl">' + re.escape(etiket) +
                      r'(?:<[^>]*>[^<]*</span>)?</span><span class="sub-note" title="([^"]*)"', kart)
        return m.group(1) if m else ""

    # 1) enabled ama cevap yok -> ARIZA
    kart, rozet, sinif, sayac = render(["unit redis enabled inactive",
                                        "unit memcached disabled inactive"])
    ck("enabled + yanıt yok -> kırmızı", chip(kart, "Redis (6379)"), ("err", "no response"))
    ck("disabled -> gri, 'kullanılmıyor'", chip(kart, "Memcached (11211)"),
       ("muted", "not in use"))
    ck("grup: biri arızalı -> Offline", rozet, "Offline")

    # 2) ikisi de kullanılmıyor -> grup 'Kullanılmıyor', kırmızı yok
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive"])
    ck("ikisi de gri", (chip(kart, "Redis (6379)")[0], chip(kart, "Memcached (11211)")[0]),
       ("muted", "muted"))
    ck("grup rozeti 'Not in use'", rozet, "Not in use")
    ck("rozet sınıfı renksiz", sinif, "badge-muted")
    ck("sayaç 'kullanılmıyor' diyor", sayac, "2 not in use")

    # 3) niyet bilgisi hiç yok -> doğrulanamadı (gri), kırmızı DEĞİL
    kart, rozet, sinif, sayac = render(["acct 5"])
    ck("unit satırı yok -> 'unverified'", chip(kart, "Redis (6379)"),
       ("muted", "unverified"))
    ck("grup yine kırmızı değil", sinif, "badge-muted")

    # 4) kullanıcı başına Redis: tam. Satırda SAĞLIK + BELLEK (örnek başına
    #    64 MB tavan var, büyüyen sayı bellek).
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "userredis 180 180", "userredis_mem 1126"])
    ck("180/180 + bellek -> yeşil", chip(kart, "Redis · user"),
       ("ok", "180/180 up · 1.1 GB"))
    ck("grup: ölçülen tek şey sağlam -> Operational", rozet, "Operational")

    # 5) eksik olanlar: SARI + adlar
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "userredis 177 180", "userredis_mem 1126",
                                        "userredis_bad alfa beta gama"])
    nokta, not_ = chip(kart, "Redis · user")
    ck("177/180 -> sarı", nokta, "warn")
    # Not SATIRA SIĞMALI: iki ad + "+N" (üç adın tamamı etiketi kırpıyordu,
    # satırda yalnız not kalıyordu). Tamamı ipucunda durur.
    ck("notta ilk adlar ve +N", "alfa beta +1" in not_, True)
    # Sorun varken SATIRDA adlar, bellek ipucuna iner.
    ck("sorun varken bellek satırda değil", "1.1 GB" in not_, False)
    ck("ipucunda tam liste + bellek", ipucu(kart, "Redis · user"),
       "not running: alfa beta gama · 1.1 GB")
    # Kısmi arıza = uyarı: kart düşmez, sarı olur (kırmızı/Offline DEĞİL).
    ck("tek hesap kartı düşürmez: Degraded", rozet, "Degraded")
    ck("ve kırmızı rozet yok", sinif, "badge-warn")

    # 6) hiçbiri ayakta değil -> kırmızı
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "userredis 0 180"])
    ck("0/180 -> kırmızı", chip(kart, "Redis · user")[0], "err")
    ck("grup: tek ölçülen kontrol çökmüş -> Offline", rozet, "Offline")

    # 7) TANIMLI SAYISI YOKSA ORAN YAZILMAZ. "N/N" demek için önce "N olması
    #    gerekiyordu" kanıtı lazım; systemd kaydı olmayan kurulumda o kanıt
    #    yok. Eski sürüm payla böleni aynı listeden alıyordu, bu yüzden oran
    #    hep doluydu ve hiçbir zaman uyarı üretmiyordu.
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "userredis 180 0", "userredis_mem 900"])
    ck("tanımlı yok -> oransız", chip(kart, "Redis · user"), ("ok", "180 up · 900 MB"))

    # 8) KULLANIM ipucunda ve YAŞIYLA: ayakta olmak kullanıldığı anlamına
    #    gelmez (boş Redis de ayakta durur) ve bu sayı yarım saatte bir
    #    ölçülüyor — bayat bir sayıyı taze gibi göstermeyiz.
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "userredis 180 180", "userredis_mem 1126",
                                        "userredis_use 150 170",
                                        "userredis_use_age 600"])
    ck("ipucunda kurulum/hesap ve yaş", ipucu(kart, "Redis · user"),
       "170 installs · 150 accounts in use, 10m ago")
    ck("kullanım uyarı üretmez", chip(kart, "Redis · user")[0], "ok")

print()
print("GECEN: %d  KALAN: %d%s" % (gecen, kalan, "  ATLANDI: 1" if atlanan else ""))
sys.exit(1 if kalan else 0)
