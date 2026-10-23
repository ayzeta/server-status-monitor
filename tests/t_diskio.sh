#!/usr/bin/env bash
# Disk R/W hizi: KUMULATIF sayac farkindan dogru hesaplaniyor mu.
#
# Eskiden "sleep 1" ile anlik ornek aliniyordu (turun 1 saniyesi). Artik iki tur
# arasindaki fark kullaniliyor; bu testin sinadigi sey o aritmetik:
#   (sektor farki * 512 bayt) / 1024 = KB, / gecen saniye = KB/s
# Ayrica: ilk turda cikti OLMAMALI (taban yok) ve sayac geri giderse (disk
# degisimi / yeniden baslatma) deger yazilmamali.
set -u
KOK="$(cd "$(dirname "$0")/.." && pwd)"   # depo koku
BURASI="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$BURASI/t_diskio_data"; rm -rf "$DATA_DIR"; mkdir -p "$DATA_DIR"
DS="$BURASI/t_diskstats.txt"
gecen=0; kalan=0
ck(){ if [ "$2" = "$3" ]; then gecen=$((gecen+1)); printf '  %-44s -> %s\n' "$1" "${2:-(bos)}"
      else kalan=$((kalan+1)); printf '  BASARISIZ %s\n    beklenen: %s\n    gelen   : %s\n' "$1" "$3" "$2"; fi; }
# Hiz alani TOLERANSLI (%5): dt duvar saatinden geliyor, testin kendi adimlari
# arasinda bir saniye gecmesi urun hatasi degil. Ad ve sira birebir karsilastirilir.
ck_hiz(){ # ad, gelen, anahtar, beklenen_kbs
  local v; v=$(printf '%s\n' "$2" | awk -v k="$3" '$1==k{print $2}')
  if [ -n "$v" ] && [ "$v" -ge $(( $4 * 95 / 100 )) ] && [ "$v" -le $(( $4 * 105 / 100 )) ]; then
    gecen=$((gecen+1)); printf '  %-44s -> %s (hedef %s)\n' "$1" "$v" "$4"
  else
    kalan=$((kalan+1)); printf '  BASARISIZ %s: beklenen ~%s, gelen %s\n' "$1" "$4" "${v:-yok}"
  fi; }

# Blogu KAYNAKTAN cikar ve /proc/diskstats yerine ornek dosyayi okut
BLOK="$(sed -n "/^  DRE='/,/chmod 600 \"\$DIO_STATE\"/p" "$KOK/src/collector.sh" \
        | sed "s#/proc/diskstats#$DS#g")"
[ -n "$BLOK" ] || { echo "CIKARILAMADI"; exit 2; }

# /proc/diskstats bicimi: alan 3 = ad, 6 = okunan sektor, 10 = yazilan sektor
yaz(){ printf '   8       0 sda 100 0 %s 0 200 0 %s 0 0 0 0\n   8       1 sda1 1 0 999999 0 1 0 999999 0 0 0 0\n' "$1" "$2" > "$DS"; }

kosu(){ eval "$BLOK"; }

# ── Ilk tur: taban yok -> cikti yok ────────────────────────────
yaz 1000 2000
ck "ilk tur: deger yazilmaz" "$(kosu)" ""

# ── Ikinci tur: 60 sn'de 120000 sektor okuma = 1000 KB/s ───────
# (120000 * 512) / 1024 / 60 = 1000
printf '%s 1000 2000\n' "$(( $(date +%s) - 60 ))" > "$DATA_DIR/.diskio_state"
yaz 121000 2000
CIK="$(kosu)"
ck_hiz "okuma: 120000 sektor/60 sn" "$CIK" diskio_r 1000
ck_hiz "okuma yokken yazma sifir" "$CIK" diskio_w 0

# ── Yazma tarafi ve bolme ───────────────────────────────────────
printf '%s 1000 2000\n' "$(( $(date +%s) - 30 ))" > "$DATA_DIR/.diskio_state"
yaz 1000 62000
ck_hiz "yazma: 60000 sektor/30 sn" "$(kosu)" diskio_w 1000

# ── Sayac geri gitti (disk degisti / reboot) -> yazilmaz ───────
printf '%s 500000 500000\n' "$(( $(date +%s) - 60 ))" > "$DATA_DIR/.diskio_state"
yaz 1000 2000
ck "sayac geri giderse deger yazilmaz" "$(kosu)" ""

# ── Cok eski taban (600 sn ustu) -> yazilmaz ───────────────────
printf '%s 1000 2000\n' "$(( $(date +%s) - 3600 ))" > "$DATA_DIR/.diskio_state"
yaz 121000 2000
ck "cok eski taban kullanilmaz" "$(kosu)" ""

# ── Durum dosyasi her turda tazelenir ──────────────────────────
ck "durum dosyasi yazildi" "$(awk '{print NF}' "$DATA_DIR/.diskio_state")" "3"

# ── Bolum (partition) cift saymaz: sda1 satiri eklenmemeli ─────
printf '%s 1000 2000\n' "$(( $(date +%s) - 60 ))" > "$DATA_DIR/.diskio_state"
yaz 121000 2000
# sda1 satirinda 999999 sektor var: sayilsaydi deger ~1000 degil ~10000 olurdu.
ck_hiz "bolumler cift sayilmaz (sda1 haric)" "$(kosu)" diskio_r 1000

rm -rf "$DATA_DIR" "$DS"
echo
echo "GECEN: $gecen  KALAN: $kalan"
[ "$kalan" -eq 0 ]
