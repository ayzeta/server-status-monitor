#!/usr/bin/env bash
# CANLI karsilastirma (gercek Linux): eski "ps" komutlari ile yeni turetim ayni
# sonucu veriyor mu. Surecler iki olcum arasinda degisebilecegi icin KARARLI
# seyler karsilastirilir: bicim, alan sayisi, sayimlarin yakinligi, ELAPSED.
set -u
S=/tmp/ssm_ps_snap; C=/tmp/ssm_ps_comm
gecen=0; kalan=0
ck(){ if [ "$2" = "$3" ]; then gecen=$((gecen+1)); printf '  %-46s -> tamam (%s)\n' "$1" "$2"
      else kalan=$((kalan+1)); printf '  BASARISIZ %-36s beklenen=%s gelen=%s\n' "$1" "$3" "$2"; fi; }

ps axo pid=,state=,user:19=,etimes=,pcpu=,pmem=,rss=,args= > "$S" 2>/dev/null
ps axo state=,user:19=,etimes=,pcpu=,rss=,comm=  > "$C" 2>/dev/null

ck "snapshot bos degil" "$([ -s "$S" ] && echo evet || echo hayir)" "evet"
ck "her satirda en az 8 alan" "$(awk 'NF<8' "$S" | wc -l)" "0"
ck "comm dosyasinda en az 6 alan" "$(awk 'NF<6' "$C" | wc -l)" "0"
ck "pid alani sayisal" "$(awk '$1 !~ /^[0-9]+$/' "$S" | wc -l)" "0"
ck "etimes alani sayisal" "$(awk '$4 !~ /^[0-9]+$/' "$S" | wc -l)" "0"
ck "rss alani sayisal" "$(awk '$7 !~ /^[0-9]+$/' "$S" | wc -l)" "0"

# ELAPSED bicimi: ps'in kendi cikisiyla ayni mi. UZUN OMURLU bir surec secilir
# (pid 1) ve SANIYE alani atilarak karsilastirilir: iki olcum arasinda bir
# saniye gecmesi bicim hatasi degil, olcum kaymasidir.
PID=1
ESKI=$(ps -o etime= -p $PID | tr -d ' ')
ESKI=${ESKI%:*}
YENI=$(awk -v p=$PID '$1==p{
   e=$4+0; d=int(e/86400); r=e%86400; h=int(r/3600); m=int((r%3600)/60); s=r%60;
   if(d>0) printf "%d-%02d:%02d:%02d",d,h,m,s;
   else if(h>0) printf "%02d:%02d:%02d",h,m,s;
   else printf "%02d:%02d",m,s}' "$S")
ck "ELAPSED bicimi ps ile ayni" "${YENI%:*}" "$ESKI"

# Sayimlar: eski komutlarla yeni turetim (ayni anda degil, 1-2 fark normal)
E_D=$(ps -eo state --no-headers | awk '$1 ~ /^D/{c++} END{print c+0}')
E_R=$(ps -eo state --no-headers | awk '$1 ~ /^R/{c++} END{print c+0}')
read Y_LT Y_LI Y_D Y_R < <(awk '
    $6=="lsphp" && $1 ~ /^[RD]/ {a++} $6=="lsphp" && $1 ~ /^S/ {b++}
    $1 ~ /^D/ {c++} $1 ~ /^R/ {d++} END{print a+0,b+0,c+0,d+0}' "$C")
ck "D sayimi makul (fark <=2)" "$([ $((E_D>Y_D?E_D-Y_D:Y_D-E_D)) -le 2 ] && echo evet || echo hayir)" "evet"
ck "R sayimi makul (fark <=2)" "$([ $((E_R>Y_R?E_R-Y_R:Y_R-E_R)) -le 2 ] && echo evet || echo hayir)" "evet"

# En cok CPU yiyen surec: eski ps sortu ile yeni sort ayni pid'i mi veriyor
E_TOP=$(ps axo pid=,pcpu= --sort=-pcpu | head -1 | awk '{print $1}')
Y_TOP=$(sort -k5,5 -rn "$S" | head -1 | awk '{print $1}')
ck "en yuksek CPU ayni surec" "$([ "$E_TOP" = "$Y_TOP" ] && echo evet || echo "hayir($E_TOP/$Y_TOP)")" "evet"

# En cok RSS: ayni
E_TOPR=$(ps axo pid=,rss= --sort=-rss | head -1 | awk '{print $1}')
Y_TOPR=$(sort -k7,7 -rn "$S" | head -1 | awk '{print $1}')
ck "en yuksek RSS ayni surec" "$([ "$E_TOPR" = "$Y_TOPR" ] && echo evet || echo "hayir($E_TOPR/$Y_TOPR)")" "evet"

# Bosluklu comm gercekten var mi (varsa dosya bicimi onu tasiyabiliyor mu)
BOS=$(awk 'NF>6' "$C" | wc -l)
printf '  bilgi: bosluklu comm satiri sayisi = %s\n' "$BOS"
ck "bosluklu comm ilk alani bozulmadan okunuyor" \
   "$(awk 'NF>6{print $6; exit}' "$C" | grep -c '[a-z]')" "1"

# Maliyet: 14 tarama yerine 2
T0=$(date +%s%3N); for i in 1 2 3; do ps axo pid=,state=,user:19=,etimes=,pcpu=,pmem=,rss=,args= >/dev/null; done; T1=$(date +%s%3N)
printf '  bilgi: tarama basina ~%s ms\n' "$(( (T1-T0)/3 ))"

rm -f "$S" "$C"
echo
echo "GECEN: $gecen  KALAN: $kalan"
[ "$kalan" -eq 0 ]
