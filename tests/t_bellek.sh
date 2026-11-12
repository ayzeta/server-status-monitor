# t_bellek.sh — "kullanilan bellek" hesabi: MemAvailable yedegi ve WHM farki.
#
# NEDEN: 2026-11-12'de kullanici WHM'in %33, panonun %48 yazdigini sordu. Ayni
# dakikada sunucuda olculdu: WHM = MemTotal-MemFree-Buffers-Cached (31,1 GB),
# pano = MemTotal-MemAvailable (44,5 GB). Ikisi de dogru hesapliyor, farkin
# sebebi Cached'in icindeki shmem (20,4 GB). Pano MemAvailable'i kullaniyor
# cunku shmem geri kazanilamaz; WHM'in formulu 2026-08'deki OPcache kacagini
# gizlerdi. Bu test o formulleri ve MemAvailable YOKSA devreye giren yedegi
# kilitler — ayrica PHP ile toplayicinin ayni sayiyi uretmesini.
#
# FIKSTUR GERCEK: tests/ornek/meminfo.txt gercek bir Linux cekirdeginin
# /proc/meminfo ciktisidir (WSL, 53 satir, oldugu gibi). Ikinci dosya ayni
# ciktidan YALNIZCA MemAvailable satiri silinerek uretildi — 3.14 oncesi
# cekirdegi boyle taklit ediyoruz, baska hicbir alan ellenmedi.

PASS=0; FAIL=0
ck(){ if [ "$2" = "$3" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "  BASARISIZ $1: beklenen=[$3] gelen=[$2]"; fi; }

KOK="$(cd "$(dirname "$0")/.." && pwd)"
IYI="$KOK/tests/ornek/meminfo.txt"
ESKI="$KOK/tests/ornek/meminfo_memavailablesiz.txt"
TMP="$KOK/tests/t_bellek_tmp.php"

# --- Fikstur gercekten bekledigimiz sey mi --------------------------------
ck "gercek ornekte MemAvailable var"   "$(grep -c '^MemAvailable:' "$IYI")"  "1"
ck "eski cekirdek ornekte yok"         "$(grep -c '^MemAvailable:' "$ESKI")" "0"
ck "digerleri ayni dosya"              "$(grep -vc '^MemAvailable:' "$IYI")" "$(wc -l < "$ESKI" | tr -d ' ')"

# --- PHP tarafi: blogu KAYNAKTAN cikarip kosar ----------------------------
# Kopyasini degil urunun kendi satirlarini kosar; index.php degisince test de
# onu gorur. Yalniz /proc/meminfo yolu fiksture cevrilir.
php_kos(){
  # Yol PHP'nin anladigi bicime cevrilir: Git Bash'in /d/... yolunu Windows
  # PHP'si acamiyor (olculdu — butun sayilar 0 donuyordu). Linux'ta cygpath
  # yok, orada yol zaten oldugu gibi gecerli.
  YOL="$(cygpath -m "$1" 2>/dev/null || printf '%s' "$1")"
  printf '%s\n' '<?php' > "$TMP"
  sed -n '/^\$meminfo      = @file/,/^\$memAvailPct/p' "$KOK/src/index.php" \
    | sed "s#/proc/meminfo#$YOL#" >> "$TMP"
  printf '%s\n' 'echo $memUsagePercent, " ", $memTotalGB, " ", $memUsedGB, " ", $shmemGB, " ", $memAvailPct, " ", round($memFreeStyle/1024/1024,1), " ", (int)round($memFreeStyle/$memTotal*100);' >> "$TMP"
  php "$TMP"
}

IYI_OUT="$(php_kos "$IYI")"
ESKI_OUT="$(php_kos "$ESKI")"
rm -f "$TMP"

ck "cikarma tuttu (bos degil)" "$([ -n "$IYI_OUT" ] && echo var)" "var"

# Beklenenler fiksturun KENDI sayilarindan: t=10066476 a=8499780 f=7292856
# b=118252 c=1455280 s=54048 sh=245908 (hepsi kB).
set -- $IYI_OUT
ck "kullanilan yuzde (MemTotal-MemAvailable)" "$1" "16"
ck "toplam GB"                                "$2" "9.6"
ck "kullanilan GB"                            "$3" "1.5"
ck "shmem GB"                                 "$4" "0.2"
ck "available yuzde"                          "$5" "84"
# free tarzi = t-f-b-c. SwapCached'e DEGIL Cached'e bakmali; yanlis alani
# okusaydi bu iki sayi tutmazdi.
ck "free tarzi GB (WHM'in yazdigi)"           "$6" "1.1"
ck "free tarzi yuzde"                         "$7" "12"

set -- $ESKI_OUT
ck "MemAvailable yokken yuzde 100 DEGIL"      "$([ "$1" = "100" ] && echo evet || echo hayir)" "hayir"
ck "yedek hesap: kullanilan yuzde"            "$1" "14"
ck "yedek hesap: kullanilan GB"               "$3" "1.3"
ck "yedek hesap: available yuzde"             "$5" "86"
# Yedek iyimser (cekirdegin rezerv payini bilmiyor) ama gercege yakin durmali:
# ayni ornekte 16 ve 14, yani 2 puan. Acilirsa yedek bozulmustur.
ck "yedek gercekten 3 puandan yakin" \
   "$(awk -v a=16 -v b="$1" 'BEGIN{d=a-b; if (d<0) d=-d; print (d<=3 ? "yakin" : "uzak " d)}')" "yakin"

# --- Toplayici tarafi: ayni satiri KAYNAKTAN cikarip kosar ----------------
RAM_SATIR="$(grep -F 'RAM=$(awk' "$KOK/src/collector.sh")"
ck "RAM satiri bulundu" "$([ -n "$RAM_SATIR" ] && echo var)" "var"

ram_kos(){ eval "$(printf '%s' "$RAM_SATIR" | sed "s#/proc/meminfo#$1#")"; printf '%s' "$RAM"; }

ck "toplayici gercek ornekte"        "$(ram_kos "$IYI")"  "16"
ck "toplayici yedekte"               "$(ram_kos "$ESKI")" "14"
# IKIZ KURALI: pano ile gecmis grafigi ayni metrigi gostermeli. Biri yedege
# girip digeri girmezse kart ile grafik ayrisir — en zor fark edilen hata.
set -- $IYI_OUT
ck "PHP ile toplayici ayni (gercek)" "$(ram_kos "$IYI")"  "$1"
set -- $ESKI_OUT
ck "PHP ile toplayici ayni (yedek)"  "$(ram_kos "$ESKI")" "$1"

# --- Ipucu cumlesi urunde duruyor mu --------------------------------------
ck "free tarzi cumlesi sozlukte" \
   "$(grep -c "A free-style count says" "$KOK/src/index.php")" "2"
ck "cumle shmem ipucuna ekleniyor" \
   "$(grep -c 'shmemTip .= .* tf(.A free-style count' "$KOK/src/index.php")" "1"
ck "sayi olculmediyse cumle kurulmaz" \
   "$(grep -c 'memTotal > 0 && \$memCached > 0 && \$memFreeStyle > 0' "$KOK/src/index.php")" "1"

echo; echo "GECEN: $PASS  KALAN: $FAIL"; [ $FAIL -eq 0 ]
