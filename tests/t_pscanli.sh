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

# ELAPSED bicimi: ps'in kendi cikisiyla ayni mi.
# Iki alan TEK ps cagrisindan alinir (etimes + etime): ayri cagrilarda olcumler
# saniyeler ayri dusup dakika sinirini gecebiliyordu ve test ARA SIRA bicim
# hatasi diye bagiriyordu. Ayni andan okununca karsilastirma birebir olur.
PID=1
read ETS ESKI < <(ps -o etimes=,etime= -p $PID | awk '{print $1, $2}')
YENI=$(awk -v e="$ETS" 'BEGIN{
   e=e+0; d=int(e/86400); r=e%86400; h=int(r/3600); m=int((r%3600)/60); s=r%60;
   if(d>0) printf "%d-%02d:%02d:%02d",d,h,m,s;
   else if(h>0) printf "%02d:%02d:%02d",h,m,s;
   else printf "%02d:%02d",m,s}')
ck "ELAPSED bicimi ps ile ayni" "$YENI" "$ESKI"

# Sayimlar: eski komutlarla yeni turetim (ayni anda degil, 1-2 fark normal)
E_D=$(ps -eo state --no-headers | awk '$1 ~ /^D/{c++} END{print c+0}')
E_R=$(ps -eo state --no-headers | awk '$1 ~ /^R/{c++} END{print c+0}')
read Y_LT Y_LI Y_D Y_R < <(awk '
    $6=="lsphp" && $1 ~ /^[RD]/ {a++} $6=="lsphp" && $1 ~ /^S/ {b++}
    $1 ~ /^D/ {c++} $1 ~ /^R/ {d++} END{print a+0,b+0,c+0,d+0}' "$C")
ck "D sayimi makul (fark <=2)" "$([ $((E_D>Y_D?E_D-Y_D:Y_D-E_D)) -le 2 ] && echo evet || echo hayir)" "evet"
ck "R sayimi makul (fark <=2)" "$([ $((E_R>Y_R?E_R-Y_R:Y_R-E_R)) -le 2 ] && echo evet || echo hayir)" "evet"

# En cok CPU yiyen surec: eski ps sortu ile yeni sort ayni pid'i mi veriyor
# Siralama denkligi: "sort -k5,5 -rn" ile ps'in "--sort=-pcpu"su ayni mi?
#
# ONCE BOYLE DEGILDI ve testi guvenilmez yapiyordu: iki AYRI ps cagrisinin en
# tepedeki sureci karsilastiriliyordu. Bos bir makinede en cok CPU yiyen sey
# TESTIN KENDI alt surecleri (awk, sort) oluyor ve her cagrida degisiyor —
# dortte bir kosu yanlis alarm veriyordu.
#
# Simdi karsilastirma AYNI VERI uzerinde: dosyayi ps kendi siralamasiyla
# yaziyor, biz de kendi siralamamizi uyguluyoruz; ikisi ayni satiri basa
# koymali. Beraberlige takilmamak icin pid degil DEGER karsilastirilir.
ps axo pid=,state=,user:19=,etimes=,pcpu=,pmem=,rss=,args= --sort=-pcpu > "$S.cpu" 2>/dev/null
ck "pcpu siralamasi ps ile ayni" \
   "$(sort -k5,5 -rn "$S.cpu" | head -1 | awk '{print $5}')" \
   "$(head -1 "$S.cpu" | awk '{print $5}')"

# En cok RSS: ayni
ps axo pid=,state=,user:19=,etimes=,pcpu=,pmem=,rss=,args= --sort=-rss > "$S.rss" 2>/dev/null
ck "rss siralamasi ps ile ayni" \
   "$(sort -k7,7 -rn "$S.rss" | head -1 | awk '{print $7}')" \
   "$(head -1 "$S.rss" | awk '{print $7}')"

# Bosluklu comm gercekten var mi (varsa dosya bicimi onu tasiyabiliyor mu)
BOS=$(awk 'NF>6' "$C" | wc -l)
printf '  bilgi: bosluklu comm satiri sayisi = %s\n' "$BOS"
ck "bosluklu comm ilk alani bozulmadan okunuyor" \
   "$(awk 'NF>6{print $6; exit}' "$C" | grep -c '[a-z]')" "1"

# Maliyet: 14 tarama yerine 2
T0=$(date +%s%3N); for i in 1 2 3; do ps axo pid=,state=,user:19=,etimes=,pcpu=,pmem=,rss=,args= >/dev/null; done; T1=$(date +%s%3N)
printf '  bilgi: tarama basina ~%s ms\n' "$(( (T1-T0)/3 ))"

rm -f "$S" "$C" "$S.cpu" "$S.rss"
echo
echo "GECEN: $gecen  KALAN: $kalan"
[ "$kalan" -eq 0 ]
