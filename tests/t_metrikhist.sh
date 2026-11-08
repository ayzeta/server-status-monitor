#!/usr/bin/env bash
# Metrik gecmisi (.metrics_history) yazimi: AYNI DAKIKAYA IKINCI SATIR DUSMESIN.
#
# Gercek olay (2026-11-08, uretim): pano guncellemesinin indigi dakikada
# toplayici iki tur kosmus ve gecmise iki "04:27" satiri dusmustu. Zararsiz
# gorunuyor ama "35 satir = 35 dakika" varsayimini SESSIZCE bozuyor: pencere
# kisaliyor ve sparkline o dakikayi iki nokta ciziyor.
#
# Yazim kodu KAYNAKTAN cikarilir; 'date' test icinde gölgelenir ki hangi
# dakikada oldugumuzu test belirlesin (gercek saate bagli = oynak test).
set -u
KOK="$(cd "$(dirname "$0")/.." && pwd)"
BURASI="$(cd "$(dirname "$0")" && pwd)"
HIST="$BURASI/t_mhist.txt"
gecen=0; kalan=0

ck(){
  if [ "$2" = "$3" ]; then gecen=$((gecen+1)); printf '  %-46s -> tamam\n' "$1"
  else kalan=$((kalan+1)); printf '  BASARISIZ %s\n    beklenen: %s\n    gelen   : %s\n' "$1" "$3" "$2"; fi
}

YAZ_SRC="$(sed -n '/^HSATIR="\$(date +%H:%M)/,/mv "\$HIST.tmp" "\$HIST"/p' "$KOK/src/collector.sh")"
[ -n "$YAZ_SRC" ] || { echo "CIKARILAMADI: gecmis yazimi"; exit 2; }

# Saat testin elinde: 'date' gölgelenir.
date(){ printf '%s\n' "$FAKE_HM"; }

yaz(){   # DAKIKA L1 -> bir tur yaz
  FAKE_HM="$1"; L1="$2"
  L5=1 L15=1 CPU=5 RAM=50 DSK=53 IOW=0 WRK=2 RXK=1 TXK=1 MQ=0
  TOPP="5:root:lsphp:" TOPR="10:mysql:mariadbd:" TOPIO="3::ayzeta"
  eval "$YAZ_SRC"
}

rm -f "$HIST"

# ── 1) Ilk satir yazilir ───────────────────────────────────────
yaz "04:26" 1.11
ck "ilk tur satiri yazar" "$(wc -l < "$HIST" | tr -d ' ')" "1"

# ── 2) AYNI dakikada ikinci tur: satir EKLENMEZ, DEGISIR ───────
yaz "04:26" 2.22
ck "ayni dakika satir sayisini artirmaz" "$(wc -l < "$HIST" | tr -d ' ')" "1"
ck "ayni dakikanin EN GUNCEL olcumu kalir" "$(awk '{print $2}' "$HIST")" "2.22"

# ── 3) Baska dakika eklenir ────────────────────────────────────
yaz "04:27" 3.33
ck "yeni dakika eklenir" "$(wc -l < "$HIST" | tr -d ' ')" "2"
ck "onceki dakika duruyor" "$(sed -n '1p' "$HIST" | awk '{print $1, $2}')" "04:26 2.22"

# ── 4) Pencere 35 satirda kaliyor ──────────────────────────────
rm -f "$HIST"
i=0
while [ $i -lt 40 ]; do
  yaz "$(printf '%02d:%02d' $((i / 60)) $((i % 60)))" "$i"
  i=$((i + 1))
done
ck "pencere 35 satirda kalir" "$(wc -l < "$HIST" | tr -d ' ')" "35"
ck "en eski satir dusmus (ilk kalan 5. tur)" "$(sed -n '1p' "$HIST" | awk '{print $2}')" "5"

# ── 5) Alan sayisi: 15 kolon (son uc fail alani dahil) ─────────
ck "satirda 15 alan var" "$(awk 'NR==1{print NF}' "$HIST")" "15"

rm -f "$HIST"
echo
echo "GECEN: $gecen  KALAN: $kalan"
[ "$kalan" -eq 0 ]
