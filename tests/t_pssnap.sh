#!/usr/bin/env bash
# Tek/iki ps anlik goruntusunden uretilen bolumler DOGRU MU.
#
# Yontem: sahte ama gercekci iki surec tablosu yazilir (biri args'li, digeri
# comm'lu), collector.sh'teki donusumler KAYNAKTAN cikarilip uygulanir.
# Boylece "14 ps -> 2 ps" degisikligi ciktinin bicimini bozmus mu gorulur.
#
# Ornek tablolarda BOSLUKLU alanlar var ve bu kasitli: gercek sistemde olculdu,
# comm "lfd - sleeping" ya da "php74 <defunct>" olabiliyor, args zaten bosluklu.
set -u
KOK="$(cd "$(dirname "$0")/.." && pwd)"   # depo koku
BURASI="$(cd "$(dirname "$0")" && pwd)"
PS_SNAP="$BURASI/t_ps_snap.txt"
PS_COMM="$BURASI/t_ps_comm.txt"
cp "$BURASI/ornek/ps_args.txt" "$PS_SNAP"
cp "$BURASI/ornek/ps_comm.txt" "$PS_COMM"
gecen=0; kalan=0

ck(){
  if [ "$2" = "$3" ]; then gecen=$((gecen+1)); printf '  %-44s -> tamam\n' "$1"
  else kalan=$((kalan+1)); printf '  BASARISIZ %s\n    beklenen: %s\n    gelen   : %s\n' "$1" "$3" "$2"; fi
}

# ── Donusumleri KAYNAKTAN cikar ────────────────────────────────
PS_ELAPSED="$(sed -n "/^PS_ELAPSED='function gecen/,/^'$/p" "$KOK/src/collector.sh" \
              | sed "1s/^PS_ELAPSED='//; \$s/^'$//")"
CPU_PIPE="$(sed -n '/sort -k5,5 -rn "\$PS_SNAP" | head -15/,/cut -c1-280/p' "$KOK/src/collector.sh" | head -4)"
RSS_PIPE="$(sed -n '/sort -k7,7 -rn "\$PS_SNAP" | head -15/,/cut -c1-280/p' "$KOK/src/collector.sh" | head -3)"
LSPHP_PIPE="$(grep -F 'awk '"'"'$6=="lsphp"{c[$2]++}' "$KOK/src/collector.sh")"
SAYIM_PIPE="$(sed -n '/read PS_LT PS_LI PS_DS PS_RS/,/PS_COMM")/p' "$KOK/src/collector.sh")"
TOPP_PIPE="$(grep -F 'TOPP=$(sort -k4,4' "$KOK/src/collector.sh")"
TOPR_PIPE="$(grep -F 'TOPR=$(sort -k5,5' "$KOK/src/collector.sh")"
IOP_PIPE="$(sed -n '/awk .{a=\$8; for(i=9;i<=NF;i++) a=a " " \$i; print \$1, \$4, \$3, substr(a,1,160)}/,/"\$PS_SNAP" > "\$IOP_STATE.ps"/p' "$KOK/src/collector.sh")"
ETARGS="$(grep -F 'ps_etimes_args(){' "$KOK/src/collector.sh")"
ETCOMM="$(grep -F 'ps_etimes_comm(){' "$KOK/src/collector.sh")"

for d in PS_ELAPSED CPU_PIPE RSS_PIPE LSPHP_PIPE SAYIM_PIPE TOPP_PIPE TOPR_PIPE IOP_PIPE ETARGS ETCOMM; do
  eval "v=\$$d"
  [ -n "$v" ] || { echo "CIKARILAMADI: $d"; exit 2; }
done

# ── 1) CPU listesi ─────────────────────────────────────────────
CPU_OUT="$(eval "$CPU_PIPE")"
ck "CPU: en yuksek pcpu basta" "$(echo "$CPU_OUT" | head -1)" \
   "1234 alici 26.0 0.1 05:05 lsphp:/home/alici/public_html/index.php"
ck "CPU: 1 gun = 1-00:00:00" "$(echo "$CPU_OUT" | sed -n '2p')" \
   "2295514 mysql 19.2 6.1 1-00:00:00 /usr/sbin/mariadbd"
ck "CPU: 11 gunluk surec" "$(echo "$CPU_OUT" | sed -n '3p' | awk '{print $5}')" "11-13:46:40"
ck "CPU: satir sayisi" "$(echo "$CPU_OUT" | wc -l | tr -d ' ')" "8"
ck "CPU: bosluklu komut butun kaliyor" \
   "$(echo "$CPU_OUT" | sed -n '3p' | cut -d' ' -f6-)" "/usr/bin/imunify-resident --quiet"
ck "CPU: bosluklu args (lfd) bozulmuyor" \
   "$(echo "$CPU_OUT" | grep -c 'lfd - sleeping')" "1"

# ── 2) RSS listesi ─────────────────────────────────────────────
RSS_OUT="$(eval "$RSS_PIPE")"
ck "RSS: en buyuk basta, KB olarak" "$(echo "$RSS_OUT" | head -1)" \
   "2295514 mysql 19.2 6.1 8388608 /usr/sbin/mariadbd"

# ── 3) Hesap basina lsphp (comm dosyasindan) ───────────────────
ck "lsphp: alici 2, other 1" "$(eval "$LSPHP_PIPE" | tr '\n' '|')" "2 alici lsphp|1 other lsphp|"

# ── 4) Dort sayim tek geciste ──────────────────────────────────
eval "$SAYIM_PIPE"
ck "sayim: lsphp aktif (R/D)" "$PS_LT" "1"
ck "sayim: lsphp bosta (S)"   "$PS_LI" "2"
ck "sayim: D durumu"          "$PS_DS" "1"
ck "sayim: R durumu"          "$PS_RS" "1"

# ── 5) Tarihce kolonlari ───────────────────────────────────────
eval "$TOPP_PIPE"; eval "$TOPR_PIPE"
ck "TOPP: ad:cpu:kullanici" "$TOPP" "lsphp:26:alici"
ck "TOPR: ad:rss_mb:kullanici" "$TOPR" "mariadbd:8192:mysql"

# ── 6) Surec I/O python'una verilen bicim ──────────────────────
IOP_STATE="$BURASI/t_iop"
eval "$IOP_PIPE"
ck "ioproc girisi: pid etimes user args" "$(head -1 "$IOP_STATE.ps")" \
   "1234 305 alici lsphp:/home/alici/public_html/index.php"
rm -f "$IOP_STATE.ps"

# ── 7) Eski "ps axo" ciktilarinin ikizleri ─────────────────────
eval "$ETARGS"; eval "$ETCOMM"
ck "ps_etimes_args: etimes + tam args" "$(ps_etimes_args | sed -n '4p')" \
   "1000000 /usr/bin/imunify-resident --quiet"
ck "ps_etimes_comm: etimes + comm ilk alani" "$(ps_etimes_comm | sed -n '7p')" "12345 lfd"

rm -f "$PS_SNAP" "$PS_COMM"
echo
echo "GECEN: $gecen  KALAN: $kalan"
[ "$kalan" -eq 0 ]
