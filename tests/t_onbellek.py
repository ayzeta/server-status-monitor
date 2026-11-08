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


# ÜRETİMDE ÖLÇÜLEN komut satırı: argümanda ne soket yolu var ne --unixsocket,
# yalnız "*:0" (TCP portu yok). Birim ayarları kendi betiğinden veriyor ve
# "User=%i" ile koşuyor, yani eşleştirmenin dayanağı KULLANICI kolonu.
# İlk sürüm tam soket yoluna dayanmıştı: hiçbir satır eşleşmedi ve pano
# ayakta olan bütün örneklere "çalışmıyor" dedi.
KUL = "/usr/bin/redis-server *:0"
# Ortak Redis de "redis-server" adıyla koşar; kullanıcı örnekleriyle
# KARIŞMAMALI (bu yüzden eşleşme --unixsocket + cagefs yolu üzerinden).
ORTAK = pr(999, "redis", 10240, "/usr/bin/redis-server 127.0.0.1:6379")

ck("userredis: tam + bellek + yaş (ortak Redis sayılmaz)",
   ur("alfa beta gama", [ORTAK,
                         pr(1, "alfa", 6400, KUL),
                         pr(2, "beta", 6400, KUL),
                         pr(3, "gama", 6400, KUL)]),
   NL.join(["userredis 3 3", "userredis_mem 18", "userredis_age 5000"]))
ck("userredis: duranın ADI",
   ur("alfa beta gama", [pr(1, "alfa", 6400, KUL), pr(2, "beta", 6400, KUL)]),
   NL.join(["userredis 2 3", "userredis_mem 12", "userredis_age 5000",
            "userredis_bad gama"]))
# Birim kaydı varken ÖLÇÜT kullanıcı kolonudur: tanımlı olmayan birinin
# redis'i hesap sayılmaz (ortak Redis de böyle eleniyor).
ck("userredis: tanımlı olmayan kullanıcı sayılmaz",
   ur("alfa", [pr(1, "alfa", 6400, KUL), pr(2, "baskasi", 6400, KUL)]),
   NL.join(["userredis 1 1", "userredis_mem 6", "userredis_age 5000"]))
# Birim kaydı yoksa ayırt edici olarak TCP portsuzluk ("*:0") kalır.
ck("userredis: tanımlı yoksa bölen 0",
   ur("", [ORTAK, pr(1, "alfa", 6400, KUL), pr(2, "beta", 6400, KUL)]),
   NL.join(["userredis 2 0", "userredis_mem 12", "userredis_age 5000"]))
ck("userredis: böyle bir yapı yoksa çıktı yok", ur("", [ORTAK]), "")
# ── GERÇEK ps çıktısıyla ───────────────────────────────────────
# Yukarıdakilerin hepsini BEN yazdım; ürünü yalnız kendi varsayımıma karşı
# sınarlar. İlk sürüm argümandaki tam soket yoluna dayanıyordu, test de aynı
# varsayımla yazıldığı için yeşil yandı — ürün üretimde hiçbir satırla
# eşleşmedi. Bu yüzden biçim artık sunucudan alınmış örnek dosyadan geliyor.
GERCEK = [s for s in io.open(os.path.join(BURASI, "ornek", "ps_redis.txt"),
                             encoding="utf-8", errors="replace").read().splitlines()
          if s and not s.startswith("#")]
ck("userredis: GERÇEK ps biçimi (ortak Redis elenir)",
   ur("acmeco bluewave shopfast", GERCEK),
   NL.join(["userredis 3 3", "userredis_mem 18", "userredis_age 7200"]))
ck("userredis: gerçek biçimde duranın adı",
   ur("acmeco bluewave shopfast kayip", GERCEK),
   NL.join(["userredis 3 4", "userredis_mem 18", "userredis_age 7200",
            "userredis_bad kayip"]))

# ── ORTAK Redis'in yaşı: kullanıcı örnekleri karışmamalı ───────
# Üretimde ortak Redis satırı "kullanılmıyor" derken yanında "4sa" yazıyordu:
# yaş yalnız SÜREÇ ADINDAN seçiliyordu ve 371 kullanıcı Redis'i de aynı adı
# taşıdığı için onlardan birinin yaşı yapışıyordu.
b = src.index("awk '$8 ~ /redis-server$/")
b = src.index(chr(39), b) + 1
e = src.index("}" + chr(39), b) + 1
YASF = os.path.join(BURASI, "t_redisyas.awk")
io.open(YASF, "w", encoding="utf-8", newline=NL).write(src[b:e])


def yas(satirlar):
    io.open(PSF, "w", encoding="utf-8", newline=NL).write(NL.join(satirlar) + NL)
    r = subprocess.run(["awk", "-f", YASF, PSF], capture_output=True, text=True)
    return r.stdout.strip()


ck("ortak Redis yaşı: kullanıcı örnekleri (*:0) elenir",
   yas(GERCEK), "svcage redis-server 86400")
ck("yalnız kullanıcı örnekleri varsa ortak Redis'in yaşı YOK",
   yas([s for s in GERCEK if ":6379" not in s]), "")
os.remove(YASF)
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
        render.sayfa = g          # kart dışını da sınayabilmek için (bkz. 10)
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

    def sag(kart, etiket):
        """Sağdaki dar sütun — UPTIME sütunu (başka birim oraya girmez)."""
        m = re.search(r'<span class="sub-lbl">' + re.escape(etiket) +
                      r'(?:<[^>]*>[^<]*</span>)?</span><span class="sub-note"[^>]*>[^<]*</span>'
                      r'<span class="sub-age"[^>]*>([^<]*)<', kart)
        return m.group(1) if m else "YOK"

    def ipucu(kart, etiket):
        """Notun title'ı — kısaltılan listenin tamamı orada durmalı."""
        m = re.search(r'<span class="sub-lbl">' + re.escape(etiket) +
                      r'(?:<[^>]*>[^<]*</span>)?</span><span class="sub-note" title="([^"]*)"', kart)
        return m.group(1) if m else ""

    # 1) enabled ama cevap yok -> ARIZA
    kart, rozet, sinif, sayac = render(["unit redis enabled inactive",
                                        "unit memcached disabled inactive",
                                        "--- Service ages ---", "svcage redis-server 15000"])
    ck("enabled + yanıt yok -> kırmızı", chip(kart, "Redis (6379)"), ("err", "no response"))
    ck("disabled -> gri, 'kullanılmıyor'", chip(kart, "Memcached (11211)"),
       ("muted", "not in use"))
    ck("grup: biri arızalı -> Offline", rozet, "Offline")
    # ÇALIŞMASI BEKLENEN ama cevapsız satırda yaş KALIR (ne zamandır böyle
    # olduğunu söyler); kullanılmayan satırda ise yazılmaz (bir alttaki iddia).
    ck("arızalı satırda yaş var", sag(kart, "Redis (6379)"), "4h")
    ck("kullanılmayan satırda yaş yok", sag(kart, "Memcached (11211)"), "")

    # 2) kurulu ama kapalı -> gri satır; HİÇ KURULU DEĞİL -> satır YOK.
    #    (2026-11-02: memcached sunucudan kaldırıldı, kart onu "kuruluymuş da
    #    kapatılmış" gibi göstermeye devam etti. Pano herkese yazıldığı için
    #    kurulmamış yazılımın satırı da olmamalı.)
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "--- Service ages ---", "svcage redis-server 15000"])
    ck("kurulu ama kapalı -> gri satır", chip(kart, "Redis (6379)")[0], "muted")
    ck("kurulu değil -> satır hiç yok", chip(kart, "Memcached (11211)"), ("YOK", "YOK"))
    # ÜRETİMDE GÖRÜLEN HATA: satır "kullanılmıyor" derken yanında "4sa",
    # ipucunda "4sa 21dk ayakta" yazıyordu. Çalışmayan şeyin yaşı olmaz.
    ck("kullanılmıyorsa yaş yazılmaz", sag(kart, "Redis (6379)"), "")
    ck("grup rozeti 'Not in use'", rozet, "Not in use")
    ck("rozet sınıfı renksiz", sinif, "badge-muted")
    # SAYIM DA FİLTREDEN SONRA: gizlenen satır sayılmaz, yoksa kart "2" deyip
    # tek satır gösterirdi.
    ck("sayaç yalnız görünen satırı sayar", sayac, "1 not in use")

    # 3) niyet bilgisi hiç yok -> doğrulanamadı (gri), kırmızı DEĞİL
    kart, rozet, sinif, sayac = render(["acct 5"])
    ck("unit satırı yok -> 'unverified'", chip(kart, "Redis (6379)"),
       ("muted", "unverified"))
    ck("grup yine kırmızı değil", sinif, "badge-muted")

    # 4) kullanıcı başına Redis: tam. Satırda SAĞLIK, sağ sütunda UPTIME,
    #    bellek ipucunda (sütun uptime sütunu, başka birim girmez).
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "userredis 180 180", "userredis_mem 1126",
                                        "userredis_age 15000"])
    ck("180/180 -> yeşil", chip(kart, "Redis · user"), ("ok", "180/180 up"))
    ck("sağ sütunda uptime", sag(kart, "Redis · user"), "4h")
    ck("bellek ipucunda", ipucu(kart, "Redis · user"), "1.1 GB")
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
    ck("sorun varken not adlara ayrılır", "1.1 GB" in not_, False)
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
    ck("tanımlı yok -> oransız", chip(kart, "Redis · user"), ("ok", "180 up"))
    ck("1 GB altı MB yazar (ipucunda)", ipucu(kart, "Redis · user"), "900 MB")
    ck("yaş ölçülmediyse sütun boş", sag(kart, "Redis · user"), "")

    # 8) KULLANIM ipucunda ve YAŞIYLA: ayakta olmak kullanıldığı anlamına
    #    gelmez (boş Redis de ayakta durur) ve bu sayı yarım saatte bir
    #    ölçülüyor — bayat bir sayıyı taze gibi göstermeyiz.
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "unit memcached notfound inactive",
                                        "userredis 180 180", "userredis_mem 1126",
                                        "userredis_use 150 170", "userredis_cap 11520 0 0"])
    # KULLANIM SATIRDA: ipucuna konunca üretimde kimse görmedi. db ayrıntısı
    # ipucunda kalır — satırda herkeste anlamı aynı olan sayı durur.
    ck("satırda kullanımdaki örnek sayısı", chip(kart, "Redis · user"),
       ("ok", "180/180 up · 150 in use"))
    # ÖLÇÜMÜN YAŞI YAZILMAZ: o yaş bizim önbellek dosyamızın yaşıydı, sunucu
    # hakkında hiçbir şey söylemiyordu ("16dk ne alaka" diye soruldu).
    # "kurulum" DEĞİL: ölçülen şey INFO keyspace'teki boş olmayan db sayısı.
    # Sitelerin ayrı db'lere bağlanması bu sunucunun kendi yapılandırmasıydı.
    ck("ipucunda hesap, dolu db ve tavan", ipucu(kart, "Redis · user"),
       "150 accounts in use, 170 non-empty databases · 1.1 GB of 11.3 GB ceiling")
    ck("ipucunda önbellek yaşı YOK", "ago" in (ipucu(kart, "Redis · user") or ""), False)
    ck("kullanım uyarı üretmez", chip(kart, "Redis · user")[0], "ok")

    # 9) TAVAN ANCAK TAM ÖLÇÜLDÜYSE YAZILIR. maxmemory 0 olan (sınırsız) ya da
    #    okunamayan örnek varsa toplam gerçek tavandan küçük kalır; eksik bir
    #    toplamı "tavan" diye yazmak ölçmeden yazmaktır.
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "userredis 180 180", "userredis_mem 1126",
                                        "userredis_use 150 170", "userredis_cap 11520 3 0"])
    ck("sınırsız örnek varsa tavan yazılmaz", ipucu(kart, "Redis · user"),
       "150 accounts in use, 170 non-empty databases · 1.1 GB · 3 unlimited")
    kart, rozet, sinif, sayac = render(["unit redis disabled inactive",
                                        "userredis 180 180", "userredis_mem 1126",
                                        "userredis_use 150 170", "userredis_cap 11520 0 2"])
    ck("okunamayan varsa tavan da sınırsız da yazılmaz", ipucu(kart, "Redis · user"),
       "150 accounts in use, 170 non-empty databases · 1.1 GB")

    # 9b) TAVAN TOPLAMI FİZİKSEL RAM'İ AŞIYOR MU (aşırı taahhüt).
    #     maxmemory bir SINIR, ayrılmış bellek değil: örnekler aynı anda
    #     dolmadıkça sorun çıkmaz, o yüzden kırmızı değil SARI. Hesap başına
    #     Redis'te kolay oluşur — 50 hesaplı 8 GB makinede 512 MB'lık tavanlar
    #     RAM'in üç katıdır; hepsi dolarsa tek hesap kısıtlanmaz, çekirdek
    #     OOM'a girer.
    #     TAM SAYFA RENDER'IYLA SINANAMAZ: $memTotal doğrudan /proc/meminfo'dan
    #     okunuyor, bu testler Windows'ta koşuyor ve dosya yok (0 kalır, dal hiç
    #     çalışmaz). O yüzden karar satırı KAYNAKTAN çıkarılıp doğrudan
    #     koşuluyor — fikstür uydurmak yerine ürünün kendi ifadesi.
    kaynak = io.open(KOK + "src/index.php", encoding="utf-8", errors="replace").read()
    kb = kaynak.index("        $urAsim = $urCap > 0")
    ke = kaynak.index("$memTotalGB . ' GB');", kb) + len("$memTotalGB . ' GB');")
    karar = kaynak[kb:ke]

    def asim(cap_mb, mem_kb):
        kod = "\n".join([
            "function t($s){return $s;}",
            "function tf($s){$a=func_get_args();array_shift($a);"
            "return preg_replace_callback('/%s/',function($m)use(&$a){return array_shift($a);},$s);}",
            "$urCap=%d; $memTotal=%d;" % (cap_mb, mem_kb),
            "$urCapT = $urCap >= 1024 ? round($urCap/1024,1).' GB' : $urCap.' MB';",
            "$memTotalGB = $memTotal > 0 ? round($memTotal/1024/1024,1) : 0;",
            "$urTips=[];",
            karar.strip(),
            "echo ($urAsim ? '1' : '0').'|'.implode(' · ', $urTips);",
        ])
        r = subprocess.run(["php", "-r", kod], capture_output=True, text=True,
                           encoding="utf-8")
        return r.stdout.strip()

    LIN = 98355136          # lin.ayzeta.net, ölçüldü 2026-11-08 (93.8 GB)
    ck("lin'in gerçek sayıları: aşım yok", asim(11520, LIN), "0|")
    ck("tavan RAM'i aşarsa işaretlenir", asim(98304, LIN).split("|")[0], "1")
    # Koşucuda çeviri sözlüğü yok (t() birebir döner), yani burada İngilizce
    # anahtar görünür. TR karşılığının varlığı ayrıca çapalanıyor.
    ck("aşım metni iki sayıyı da yazar", asim(98304, LIN).split("|")[1],
       "ceiling 96 GB exceeds physical RAM 93.8 GB")
    ck("TR çevirisi tanımlı",
       "'ceiling %s exceeds physical RAM %s' =>" in kaynak, True)
    # Ölçülemeyen iki durumda SUSAR: tavan eksik toplanmışsa (0) ya da RAM
    # okunamamışsa (0). "Ölçmediğimiz şeyi gösterme" kuralı.
    ck("tavan ölçülmediyse susar", asim(0, LIN), "0|")
    ck("RAM okunamadıysa susar", asim(98304, 0), "0|")

    # 10) HAYALET SATIR OLMAYACAK. Güvenlik satırları koşullu (CSF/ModSecurity/
    #     CageFS kurulu değilse satır yok) ama sürüm etiketleme indisle
    #     yapılıyordu ve tagVer parametreyi REFERANSLA alıyor: olmayan indise
    #     yazınca PHP indisi YARATTI, ortaya etiketsiz-notsuz satır çıktı ve
    #     renderChecks ona "fail" dedi. Üretimde görüldü (2026-11-02): kartta
    #     "v16.33 · başarısız" diye üç satır. Kurulu olanda sürüm yine yazmalı.
    render(["acct 5"])
    i = render.sayfa.find('id="ch-sec"')
    sec = render.sayfa[i:render.sayfa.find('</div>', render.sayfa.find('</div>', i) + 6)] if i >= 0 else ""
    ck("güvenlik kartında etiketsiz satır yok", '<span class="sub-lbl"></span>' in sec, False)
    ck("yokken satır da yok", "CSF firewall" in sec, False)
    render(["acct 5", "csf ok", "modsec On", "cagefs Enabled"])
    i = render.sayfa.find('id="ch-sec"')
    sec = render.sayfa[i:i + 2000] if i >= 0 else ""
    ck("varken satır yerinde", "CSF firewall" in sec, True)
    ck("varken de etiketsiz satır yok", '<span class="sub-lbl"></span>' in sec, False)

print()
print("GECEN: %d  KALAN: %d%s" % (gecen, kalan, "  ATLANDI: 1" if atlanan else ""))
sys.exit(1 if kalan else 0)
