#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# collector.sh — Server Status Monitor data collector (root cron)
# Install : /root/<dir>/collector.sh  (chmod 700), root crontab every minute.
# Consumer: <web_dir>/index.php  (root feed — CageFS blocks PHP from the full
#           process list, so root collects it and hands it to the web user).
# Config  : config.env in the same dir → WEB_USER (required) + DATA_DIR (caches).
# Note    : explicit PATH is required — whmapi1/cagefsctl/exim are not on cron's
#           default PATH. sleep 20 dodges the top-of-minute cron storm.
# ═══════════════════════════════════════════════════════════════
SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
[ -f "$SELF_DIR/config.env" ] && . "$SELF_DIR/config.env"
: "${WEB_USER:?config.env must define WEB_USER (e.g. WEB_USER=myuser)}"
DATA_DIR="${DATA_DIR:-$SELF_DIR}"
HOME_DIR="/home/$WEB_USER"
# Tek-örnek kilidi: priming (elle çalıştırma) cron ile aynı dakikaya denk gelince
# ya da bir çalışma sonraki cron'a taşınca, iki instance aynı .tmp dosyalarına
# yazıp "mv: cannot stat" üretmesin. Kilit alınamazsa (başka örnek çalışıyor)
# sessizce çık; kilit dosyası açılamazsa kilitsiz devam; flock yoksa atla.
#
# PROFIL MODU (SSM_PROFILE=1, "ssmon profile"): kilidi ve uykuyu atlar, her
# bolumun suresini stderr'e yazar. Kilidi atlamasinin sebebi olculdu: elle
# calistirilan bir olcum cron turuna denk geldiginde kilide takilip sessizce
# cikiyor ve "profil bos dondu" diye dakikalar kaybediliyordu. Veri normal
# akisiyla uretilir — yani olculen sey GERCEK turun maliyetidir.
# NOT: "exec 9>dosya 2>/dev/null" YANLISTI — exec'e komut verilmeyince yanindaki
# yonlendirme KABUGUN KENDISINE kalici uygulanir, yani o satirdan sonra betigin
# TUM stderr'i /dev/null'a gidiyordu. Hatalar sessizce kayboluyordu ve bash -x
# ile profil almak imkansizdi (iz tam burada kesiliyordu). Susturma artik
# yalnizca exec'in kendi hatasini kapsiyor.
if [ "${SSM_PROFILE:-0}" != "1" ] && command -v flock >/dev/null 2>&1 \
   && { exec 9>"/var/run/ssm-collector-$WEB_USER.lock"; } 2>/dev/null; then
  flock -n 9 || exit 0
fi
export PATH=/usr/local/cpanel/bin:/usr/local/cpanel/3rdparty/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Bolum suresi olcumu: yalniz profil modunda calisir, normal turda tek "if".
PROF_T0=0; PROF_TB=0
if [ "${SSM_PROFILE:-0}" = "1" ]; then
  PROF_T0=$(date +%s%3N); PROF_TB=$PROF_T0
  echo "profil modu: 20 sn uyku ve tek-ornek kilidi atlandi; veri normal akisiyla uretiliyor" >&2
fi
prof(){
  [ "${SSM_PROFILE:-0}" = "1" ] || return 0
  local n; n=$(date +%s%3N)
  printf '%7d ms  %s\n' "$(( n - PROF_T0 ))" "$1" >&2
  PROF_T0=$n
}
[ "${SSM_PROFILE:-0}" = "1" ] || sleep 20   # dodge the top-of-minute cron storm

# --- TEK SUREC ANLIK GORUNTUSU ----------------------------------------------
# Eskiden ayni turda ON BIR ayri "ps" calisiyordu ve her biri /proc'u bastan
# geziyordu. Uretimde olculdu (706 surec): tarama basina 50-100 ms, toplami
# ~0,8 sn. Artik tek tarama aliniyor, butun bolumler ondan besleniyor.
#
# YAN FAYDA DOGRULUK: bolumler artik AYNI ANI anlatiyor. Eskiden CPU listesi,
# lsphp sayimi ve surec I/O listesi saniyeler arayla alinmis AYRI anlardi;
# "su an calisanlar" diye yan yana gosterdigimiz seyler birbirini tutmuyordu.
#
# IKI dosya, cunku HEM args HEM comm bosluk icerebilir ve awk alanlari bosluga
# gore ayirir. Gercek sistemde olculdu: comm "lfd - sleeping", "php74 <defunct>"
# olabiliyor. Bu yuzden her dosyada bosluklu alan EN SONDA duruyor:
#   PS_SNAP: 1=pid 2=state 3=user 4=etimes 5=pcpu 6=pmem 7=rss 8+=args
#   PS_COMM: 1=state 2=user 3=etimes 4=pcpu 5=rss 6+=comm
# Iki tarama, on dort yerine (uretimde ~800 ms -> ~150 ms).
PS_SNAP="$DATA_DIR/.ps_snap"
PS_COMM="$DATA_DIR/.ps_comm"
ps axo pid=,state=,user:19=,etimes=,pcpu=,pmem=,rss=,args= 2>/dev/null > "$PS_SNAP.tmp" \
  && mv -f "$PS_SNAP.tmp" "$PS_SNAP"
ps axo state=,user:19=,etimes=,pcpu=,rss=,comm= 2>/dev/null > "$PS_COMM.tmp" \
  && mv -f "$PS_COMM.tmp" "$PS_COMM"
chmod 600 "$PS_SNAP" "$PS_COMM" 2>/dev/null
# "ps axo etimes=,args=" ve "ps axo etimes=,comm=" ciktilarinin birebir ayni
# bicimde yeniden uretimi — cagiran awk programlari degismeden calissin diye.
ps_etimes_args(){ awk '{a=$8; for(i=9;i<=NF;i++) a=a " " $i; print $4, a}' "$PS_SNAP"; }
ps_etimes_comm(){ awk '{print $3, $6}' "$PS_COMM"; }
ps_etimes_pcpu_args(){ awk '{a=$8; for(i=9;i<=NF;i++) a=a " " $i; print $4, $5, a}' "$PS_SNAP"; }
# etimes (saniye) -> ps'in ELAPSED bicimi ([[gg-]ss:]dd:ss). Anlik goruntude
# saniye tutuluyor (hesap yapilabilsin diye); CPU listesi insan bicimini yaziyor.
PS_ELAPSED='function gecen(e,  d,h,m,s,r){ e=e+0; d=int(e/86400); r=e%86400;
  h=int(r/3600); m=int((r%3600)/60); s=r%60;
  if(d>0) return sprintf("%d-%02d:%02d:%02d",d,h,m,s);
  if(h>0) return sprintf("%02d:%02d:%02d",h,m,s);
  return sprintf("%02d:%02d",m,s); }
'

# --- CPU / IO wait: GERCEK ~60 sn ORTALAMA -----------------------------------
# /proc/stat kumulatif sayaclarinin bir onceki cron calismasiyla farki = tum cron
# araligi boyunca ortalama. Anlik ornekleme (dashboard'da 250 ms) yogun paylasimli
# sunucuda surekli %100 gorur: bir lsphp dogar, bir cron tetiklenir, ornek oraya
# denk gelir; oysa gercek kullanim %25'tir. Sayac farki bu gurultuyu tamamen eler
# ve harici araclarla (cPanel 360 Monitoring vb.) ayni degeri uretir. Aralik tam
# 60 sn olmasa da (cron gecikmesi) hesap dogru kalir — fark her zaman gecen sureye
# gore normalize olur. Ilk calismada onceki sayac yok → deger bos, PHP canli
# olcumune duser.
CPU_STATE="$DATA_DIR/.cpu_state"
read CT CI CW < <(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5, $6}' /proc/stat)
CPU=""; IOW=""
if [ -r "$CPU_STATE" ]; then
  read PT PI PW < "$CPU_STATE" 2>/dev/null
  TD=$(( CT - ${PT:-0} )); IDL=$(( CI - ${PI:-0} )); WIO=$(( CW - ${PW:-0} ))
  # TD<=0: yeniden baslatma (sayaclar sifirlandi) veya bozuk state → atla
  if [ "$TD" -gt 0 ] && [ "$IDL" -ge 0 ] && [ "$WIO" -ge 0 ]; then
    CPU=$(( 100*(TD-IDL)/TD )); IOW=$(( 100*WIO/TD ))
    [ "$CPU" -lt 0 ] && CPU=0
    [ "$CPU" -gt 100 ] && CPU=100
    [ "$IOW" -lt 0 ] && IOW=0
  fi
fi
echo "$CT $CI $CW" > "$CPU_STATE" 2>/dev/null
chmod 600 "$CPU_STATE" 2>/dev/null

# --- AG HIZLARI: GERCEK ~60 sn ORTALAMA (arayuz bazinda) ---------------------
# CPU ile ayni mantik: /proc/net/dev kumulatif bayt sayaclarinin onceki calismayla
# farki / gecen sure. Dashboard'un 250 ms ornegi anlik bir aktarimi "hat doygun"
# sanip alarm uretebiliyordu. Arayuz BAZINDA cunku doygunluk her portun kendi link
# hizina oranlanir. Cikti: "net_rate eth0:RX:TX eth1:RX:TX" (bayt/sn, lo haric).
NET_STATE="$DATA_DIR/.net_state"
NOW_TS=$(date +%s)
# Ayristirma iki-nokta bazli: /proc/net/dev arayuz adini 6 karaktere SAGA yaslar,
# yani kisa adlarda basta bosluk VAR (alan kayar), uzun adlarda (enp0s31f6) YOK.
# "-F'[: ]+'" ile sabit alan numarasi kullanmak bu yuzden guvenilmez; ayrica cok
# buyuk sayac degerinde "eth0:12345678" gibi bosluksuz bicim de olusabilir.
NET_CUR=$(awk -F: 'NF>=2 { name=$1; gsub(/[ \t]/,"",name); if (name=="lo"||name=="") next;
                           nf=split($2, v, " "); if (nf>=9) print name, v[1], v[9] }' /proc/net/dev)
NET_RATE=""
if [ -r "$NET_STATE" ]; then
  NET_RATE=$(awk -v now="$NOW_TS" '
    NR==FNR { if ($1=="_ts") pts=$2; else if (NF>=3) { prx[$1]=$2; ptx[$1]=$3 } ; next }
    { if (pts=="" ) next; el = now - pts; if (el <= 0) next;
      # sayac geriye gittiyse (reboot/wrap) o arayuzu atla
      if (($1 in prx) && $2 >= prx[$1] && $3 >= ptx[$1])
        printf "%s%s:%d:%d", (c++?" ":""), $1, ($2-prx[$1])/el, ($3-ptx[$1])/el }
  ' "$NET_STATE" - <<< "$NET_CUR")
fi
{ echo "_ts $NOW_TS"; echo "$NET_CUR"; } > "$NET_STATE" 2>/dev/null
chmod 600 "$NET_STATE" 2>/dev/null

# --- Aktivite kampanya yasi --------------------------------------------------
# Cip yasi = max(surec etimes, kampanya yasi).
#   etimes  : KESIN olcum, ama yalnizca isi TEK uzun omurlu surec yurutuyorsa
#             kampanya yasina esittir (upcp; backup'ta cpbackup ebeveyni de eslesir).
#   kampanya: hesap hesap kisa surecler dogduran isler icin gerekli — wappspector
#             her hesapta yeniden dogar, kampanya 40 dk surse bile etimes 7 sn cikar.
# max() ikisini birlestirir: durum takibi etimes'i asla dusurmez, yalnizca tabandan
# yukseltir. Boylece hangi isin hangi surec topolojisiyle calistigini onceden bilmek
# gerekmez; cPanel tetikleyiciyi degistirse bile dogru olan otomatik kazanir.
#
# Kampanya SINIRI yalnizca kabul penceresiyle belirlenir. PPID'yi kampanya kimligi
# olarak kullanmayi denedik, CALISMIYOR: uzun omurlu wp-toolkit yurutuculeri (%0 CPU)
# pcpu esigine takilip elenir, eslesen tek surec o anki kisa gorev olur ve ONUN
# ebeveyni her gorevde degisir (olculdu: 2826046 -> 2826040 -> 2793733). Sonucta
# kampanya her turda sifirlanirdi. Ebeveynin YASI da kullanilamaz: kimligi
# tetikleyiciye gore degisir (wappspector'da gather_update_log_stats, gece cron'unda
# kalici bir kuyruk servisi -> "8 gundur tarama").
#
# Kabul penceresi: ornekleme dakikada bir, hesaplar arasi boslukta hic surec
# gorunmeyebilir. O aralikta cip SONMEZ — hem yas kesilmez hem de cipin sonup
# yanmasi Event log'unu spam'lemez (eskiden bu yuzden uc cip "sessiz" isaretliydi).
#
# 600 sn. Pencere artik yalnizca kampanya-omurlu bir sureci OLMAYAN isler icin
# gerekli: wappspector ve pkgacct hesap hesap kisa surecler doguruyor, dakikalik
# ornekleme cogunu kaciriyor. (wp-toolkit artik pencereye muhtac degil — partinin
# kendi sureci izleniyor, bkz. act_wpt.)
# Deger canlida wp-toolkit uzerinde olculdu: 180 sn iki kez yetmedi (05:32:57 ve
# 05:40:58'de parti ortasinda sonup sahte "basladi/bitti" cifti uretti), olculen
# gorulme araligi 228 sn'ydi. 300 denendi ama o son olcume gore ayar yapmakti;
# bir sonraki bosluk 310 olsa ayni sorun donerdi. 600 bosluk SINIFINI kapsar.
# Bedeli: gercekten biten bir is cipte 10 dk'ya kadar kalir — arka plan gostergesi
# icin kabul edilebilir, dogru isi parcalayip log'u sahte ciftlerle doldurmaktan iyi.
ACT_STATE="$DATA_DIR/.act_state"; ACT_GRACE=120   # 2 tik: olay kaydi kapanis debounce'u
ACT_NOW=$(date +%s); ACT_NEXT=""
# Sonuc $ACT_AGE'e yazilir, echo EDILMEZ: cagri komut ikamesiyle yapilsaydi
# ( A=$(act_age ...) ) fonksiyon alt kabukta calisir ve $ACT_NEXT birikimi ana
# kabuga donmezdi — durum dosyasi hep bos kalir, her tur "yeni kampanya" sayilirdi.
# BITIS de kaydedilir. Kampanya penceresi dolunca kaydi atmak yerine bitis anini
# saklariz: bitis = SON GORULME (pl), yani pencerenin basladigi an — pencerenin
# doldugu an degil. Boylece "bitti" satiri gercek zamani gosterir, 10 dakika geç
# degil. Bitmis kayit ACT_RETAIN boyunca saklanir ki pano ne zaman acilirsa acilsin
# yakin gecmisteki bitisi gorebilsin (eskiden bu satiri yalnizca o an ACIK olan
# tarayici yazabiliyordu).
# Kampanya yeniden basladiginda eski bitis kaydi dusurulur: ayni etkinlik icin
# ayni anda hem "basladi" hem "bitti" gostermek kafa karistirir.
ACT_RETAIN=3600
# ps|awk tespitlerinin ORTAK on-eki: komutu arama/goruntuleme/duzenleme araci olan
# satirlar hic degerlendirilmez. Bunlar is DEGIL, isin ADINI tasiyan sureclerdir:
# 'grep pkgacct', 'vim .../csf_autogroup.sh', 'tail -f ...', toplayicinin kendi
# awk'i. Her biri, desen metinde gectigi icin sahte "basladi" uretebiliyordu
# (en sinsisi awk'in kendisi: ps yuk altinda 1 sn gecikince kendi programini
# yas 1 ile goruyordu). Iki surum: komut 2. alanda (etimes,args) / 3. alanda
# (etimes,pcpu,args).
PS_SKIP_RE='(^|\/)(awk|gawk|mawk|grep|egrep|fgrep|rg|ack|vim|vi|view|nvim|nano|emacs|mcedit|less|more|cat|tail|head|sed|diff|tee|bat|strings|watch|git)$'
PS_SKIP2='$2 ~ /'"$PS_SKIP_RE"'/ { next }
'
PS_SKIP3='$3 ~ /'"$PS_SKIP_RE"'/ { next }
'
# IZ DOSYASI: ps-tabanli her tespit, ESLESTIGI komut satirini zaman damgasiyla
# buraya yazar (.act_matches.log, son 300 satir). "Bu 'basladi' nereden cikti?"
# sorusu artik tahminle degil kayitla cevaplanir:  tail /root/.../.act_matches.log
# awk'lara -v tr=... -v ts=... ile gecer; eslesen blok 'print ts, anahtar, $0 >> tr' yapar.
ACT_TRACE="$DATA_DIR/.act_matches.log"; ACT_TS="$(date '+%F %T')"
# KAPSAM ($3, opsiyonel: o an gorulen hesap): kampanya boyunca TEK hesap
# goruldiyse bitis kaydina tasinir ve "bitti" satirinda hesap adi yazilir
# (elle baslatilan tek hesap yedegi). Birden fazla hesap goruldiyse "*" olur ve
# bitiste ad yazilmaz — tam yedekte son paketlenen hesabi yazmak yaniltirdi.
act_age() {   # $1=anahtar  $2=etimes (bos = surec gorunmuyor)  $3=kapsam  $4=tur -> $ACT_AGE / $ACT_END / $ACT_END_P / $ACT_END_K
  local k="$1" et="$2" sc="$3" kd="$4" gr="${5:-$ACT_GRACE}" pf pl pc ps pk age pe pes pek
  ACT_AGE=""; ACT_END=""; ACT_END_P=""; ACT_END_K=""; ACT_LIVE=""
  read pf pl pc ps pk < <(awk -v k="$k" '$1==k{print $2, $3, $4, $5, $6; exit}' "$ACT_STATE" 2>/dev/null)
  # Saglik kontrolu: bozuk/eski bicimli kayit (30 gunden yasli "baslangic") atilir.
  # Onceki surumun durum dosyasi 'anahtar ppid ilk son' bicimindeydi; alan kaymasi
  # PPID'yi baslangic epoch'u sanmaya ve 50+ yillik yas gostermeye yol acardi.
  case "$pf" in ''|*[!0-9]*) pf=""; pl=""; pc=""; ps=""; pk="";; *) [ $(( ACT_NOW - pf )) -gt 2592000 ] && { pf=""; pl=""; pc=""; ps=""; pk=""; };; esac
  case "$pc" in ''|*[!0-9]*) pc=$pl;; esac                 # 3 alanli eski kayit

  # "?" = SONDA OKUYAMADI. "Is yok" ile ayni sey DEGIL ve hicbir sey cope atilmaz.
  # pl ILERLER: kampanya ayakta kalir, yoksa kor gecen sure paya sayilir ve suren bir
  # is sonda dondugunde yeni kampanya sanilip yasi sifirlanirdi (eski "1DK" hatasi).
  # pc'ye DOKUNULMAZ: is gercekten bitmisse "bitti" satiri son dogrulanmis ani
  # gosterir, kor gecen sureyi degil. Gecis YAZILMAZ — kor sure ne baslatir ne bitirir.
  if [ "$et" = "?" ]; then
    if [ -n "$pf" ]; then
      # Kor tik: sonda OKUYAMADI. Bu "kosuyor" KANITI degil, bilgisizliktir —
      # rozet gosterilmez (ACT_AGE atanmaz). Kampanya acik tutulur ki olay kaydi
      # kor gecen bir tik yuzunden sahte "bitti" yazmasin.
      ACT_NEXT="$ACT_NEXT$k $pf $ACT_NOW $pc $ps $pk"$'\n'
      ACT_LIVE=$pf
      return 0
    fi
    read pe pes pek < <(awk -v k="END:$k" '$1==k{print $2, $3, $4; exit}' "$ACT_STATE" 2>/dev/null)
    case "$pe" in ''|*[!0-9]*) return 0;; esac
    [ $(( ACT_NOW - pe )) -gt "$ACT_RETAIN" ] && return 0
    ACT_NEXT="$ACT_NEXT""END:$k $pe $pes $pek"$'\n'
    ACT_END=$pe; act_end_scope "$pes" "$pek"
    return 0
  fi

  if [ -n "$et" ]; then                                   # surec goruldu
    if [ -z "$pf" ] || [ $(( ACT_NOW - ${pl:-0} )) -gt "$gr" ]; then
      pf=$ACT_NOW; ps=""; pk=""                           # yeni kampanya
    fi
    pl=$ACT_NOW; pc=$ACT_NOW
    case "$sc" in ''|-) ;; *) if [ -z "$ps" ]; then ps=$sc; elif [ "$ps" != "$sc" ]; then ps="*"; fi;; esac
    # Tur de ayni kuralla tasinir: kampanya boyunca degismediyse bitise gider,
    # degistiyse "*" olur ve pano onu yazmaz (yanlis tur yazmaktansa hic yazma).
    case "$kd" in ''|-) ;; *) if [ -z "$pk" ]; then pk=$kd; elif [ "$pk" != "$kd" ]; then pk="*"; fi;; esac
    ACT_NEXT="$ACT_NEXT$k $pf $pl $pc $ps $pk"$'\n'
    age=$(( ACT_NOW - pf )); [ "$et" -gt "$age" ] && age=$et
    ACT_AGE=$age; ACT_LIVE=$pf
    return 0                                              # aktif: eski bitis dusurulur
  fi

  # SUREC GORUNMUYOR ama kampanya henuz kapanmadi.
  # ACT_AGE BURADA ATANMAZ — rozet yalnizca KANITA dayanir. Eskiden burada da
  # yas veriliyordu ve rozet, is bittikten sonra pay suresince ekranda kalip
  # sayaci buyutuyordu; gosterilen sey olcum degil cikarimdi (sunucuda olculdu:
  # cron */30, ps bos, rozet 5DK'dan 9DK'ya cikiyordu).
  # Kampanya yine de acik tutulur, cunku OLAY KAYDI ayri bir sey: "bitti" satirini
  # tek bir goremedigimiz tik yuzunden yazmak cop uretir. Kapanis art arda iki
  # olcum bekler (ACT_GRACE); bu bir durum iddiasi degil, kaydin debounce'u.
  if [ -n "$pf" ] && [ $(( ACT_NOW - ${pl:-0} )) -le "$gr" ]; then
    ACT_NEXT="$ACT_NEXT$k $pf $pl $pc $ps $pk"$'\n'
    ACT_LIVE=$pf
    return 0
  fi

  # Kampanya bitti (ya da hic yoktu): bitis anini kaydet/tasi
  if [ -n "$pc" ]; then
    pe=$pc; pes=$ps; pek=$pk                              # bitis = son DOGRULANMIS an
  else
    read pe pes pek < <(awk -v k="END:$k" '$1==k{print $2, $3, $4; exit}' "$ACT_STATE" 2>/dev/null)
  fi
  case "$pe" in ''|*[!0-9]*) return 0;; esac
  [ $(( ACT_NOW - pe )) -gt "$ACT_RETAIN" ] && return 0   # saklama suresi doldu
  ACT_NEXT="$ACT_NEXT""END:$k $pe $pes $pek"$'\n'
  ACT_END=$pe; act_end_scope "$pes" "$pek"
}
# Bitis kapsami: tek hesap ise adi, birden fazla hesap goruldiyse "*" (pano "tum
# hesaplar" yazar); "-" (hic bilinmedi) yayinlanmaz.
act_end_scope() { case "$1" in ''|-) ACT_END_P="";; *) ACT_END_P=$1;; esac
                  case "$2" in ''|-|'*') ACT_END_K="";; *) ACT_END_K=$2;; esac; }
# Cikti yardimcisi: yas ve/veya bitis satirini yazar.
act_emit() {  # $1=anahtar  $2=etimes
  act_age "$1" "$2"
  [ -n "$ACT_AGE" ] && echo "$1 $ACT_AGE"
  [ -n "$ACT_LIVE" ] && echo "${1}_live $ACT_LIVE"
  [ -n "$ACT_END" ] && echo "${1}_end $ACT_END"
  [ -n "$ACT_END_P" ] && echo "${1}_end_p $ACT_END_P"
  [ -n "$ACT_END_K" ] && echo "${1}_end_k $ACT_END_K"
  return 0
}

OUT="$HOME_DIR/.proc_snapshot"
{
  # Uc liste de TEK anlik goruntuden (bkz. PS_SNAP). Baslik satiri korunuyor:
  # ayristirici ilk satiri "ps basligi" diye atliyor ve guncelleme sirasindaki
  # bir turda diskte eski bicim kalabilir.
  prof "hazirlik (ps anlik goruntuleri, cpu/ag sayaclari)"
  echo "--- Top 15 by CPU ---"
  echo "PID USER %CPU %MEM ELAPSED COMMAND"
  sort -k5,5 -rn "$PS_SNAP" | head -15 | awk "$PS_ELAPSED"'{
      a=$8; for(i=9;i<=NF;i++) a=a " " $i;
      print $1, $3, $5, $6, gecen($4), a }' | cut -c1-280
  echo
  echo "--- Top 15 by RSS ---"
  echo "PID USER %CPU %MEM RSS COMMAND"
  sort -k7,7 -rn "$PS_SNAP" | head -15 | awk '{
      a=$8; for(i=9;i<=NF;i++) a=a " " $i;
      print $1, $3, $5, $6, $7, a }' | cut -c1-280
  echo
  echo "--- lsphp per user ---"
  awk '$6=="lsphp"{c[$2]++} END{for(u in c) printf "%d %s lsphp\n", c[u], u}' "$PS_COMM" | sort -rn | head -15
  echo
  prof "surec listeleri (cpu/rss/lsphp)"
  echo "--- Security checks ---"
  # CSF durumu TEK bir dosyadan okunamaz. "csf.disable yoksa acik" demek yetmiyor:
  # bir CSF yukseltmesi guvenlik duvarini YUKLENMEMIS birakabiliyordu (CSF 16.33-1
  # bunu duzeltti) ve o durumda hicbir kural yokken pano yesil gorunurdu.
  # Sira onemli, ilk tutan kazanir: kurulu mu > csf.disable > TESTING > kural yuklu mu.
  # Durum adlari csf-autogroup ile ORTAK (missing/off/testing/norules/unknown/ok) —
  # iki arac ayni duruma farkli ad vermesin; olcutleri o arac gercek CSF 16.33'te
  # (CloudLinux 8 ve AlmaLinux 9, iptables-nft) dogruladi.
  # systemd'nin csf servisine BAKILMAZ: kurallar yukluyken "failed" gorundugu oldu.
  if [ -d /etc/csf ] || command -v csf >/dev/null 2>&1; then
    CSF_ST=ok
    if [ ! -x /usr/sbin/csf ] && ! command -v csf >/dev/null 2>&1; then
      CSF_ST=missing
    elif [ -e /etc/csf/csf.disable ]; then
      CSF_ST=off
    elif [ "$(awk -F'"' '/^TESTING /{print $2; exit}' /etc/csf/csf.conf 2>/dev/null)" = "1" ]; then
      # TESTING kural kontrolunden ONCE: bu moddayken CSF kurallari cron ile
      # periyodik soker, yuklu gorunmesi kalici degil.
      CSF_ST=testing
    elif ! command -v iptables >/dev/null 2>&1; then
      CSF_ST=unknown
    elif iptables -S LOCALINPUT >/dev/null 2>&1; then
      CSF_ST=ok
    elif command -v iptables-legacy >/dev/null 2>&1 && iptables-legacy -S LOCALINPUT >/dev/null 2>&1; then
      CSF_ST=ok                       # kurallari legacy arka uctan yuklemis eski kurulum
    else
      # "Zincir yok" ile "okuyamadim" AYRI tutulur. Toplayici root cron'da kosar,
      # ama biri elle root disinda calistirirsa iptables yetki hatasi verir — bu
      # "duvar yuklenmemis" DEGIL, dogrulanamadidir. (csf-autogroup bu ayrimi
      # yapmiyor, hep root kostugu icin oraya gerek yok.)
      CSF_ERR=$(iptables -S LOCALINPUT 2>&1 >/dev/null)
      case "$CSF_ERR" in
        *[Pp]ermission*|*"not permitted"*|*"must be root"*) CSF_ST=unknown;;
        *) CSF_ST=norules;;
      esac
    fi
    # KOTU HABER TEK OLCUMLE YAZILMAZ. CSF yeniden yuklerken (csf -r, paket
    # yukseltmesi) once temizleyip sonra kuruyor; LOCALINPUT o arada kisa sure yok.
    # Dakikada bir kosan toplayici o ana denk gelse sahte alarm uretirdi. Ayni sey
    # 'missing' icin de gecerli (rpm ikiliyi degistirirken). Bu yuzden ikisi ancak
    # ART ARDA IKI olcumde gorulunce yayinlanir. Kasitli durumlar (off, testing)
    # boyle bir pencereye sahip degil — onlar aninda yazilir.
    CSF_SFILE="$DATA_DIR/.csf_state"
    read CSF_PREV CSF_PUB < <(cat "$CSF_SFILE" 2>/dev/null)
    CSF_OUT=$CSF_ST
    case "$CSF_ST" in
      norules|missing)
        # Ilk goruste onceki YAYINI koru; gecmis yoksa 'unknown' (dogrulanamadi),
        # 'ok' demek yanlis olurdu — henuz dogrulanmis bir sey yok.
        [ "$CSF_PREV" != "$CSF_ST" ] && CSF_OUT=${CSF_PUB:-unknown};;
    esac
    printf '%s %s\n' "$CSF_ST" "$CSF_OUT" > "$CSF_SFILE"
    chmod 600 "$CSF_SFILE" 2>/dev/null
    echo "csf $CSF_OUT"
    # Eski panolar bu satiri okuyor (guncelleme sirasinda sayfa yeni, anlik
    # goruntu bir dakika eski olabiliyor). Yeni pano durumu 'csf'den aliyor.
    T=$(awk -F'"' '/^TESTING /{print $2}' /etc/csf/csf.conf 2>/dev/null)
    [ -n "$T" ] && echo "csf_testing $T"
  fi
  M=$(awk '/^[[:space:]]*SecRuleEngine/{print $2; exit}' /etc/apache2/conf.d/modsec/modsec2.cpanel.conf 2>/dev/null)
  [ -n "$M" ] && echo "modsec $M"
  # cagefsctl python baslatiyor: olculdu, 814 ms. CageFS'in acik/kapali olmasi
  # dakikalik degisen bir sey degil; ayrica degistiginde /etc/cagefs altinda bir
  # seyler degisir. Bu yuzden DIZIN MTIME'I degistiginde (ya da en gec 15 dakikada
  # bir) soruluyor. Yaniti ne zaman aldigimiz cagefs_at ile yaziliyor ki ekran
  # "su an boyle" demek yerine ne zaman olculdugunu soyleyebilsin.
  CAG_CACHE="$DATA_DIR/.cagefs_cache"
  CAG_MARK="$DATA_DIR/.cagefs_mark"
  CAG_DIRT=$(stat -c %Y /etc/cagefs 2>/dev/null || echo 0)
  CAG_PREV=$(cat "$CAG_MARK" 2>/dev/null || echo "")
  CAG_AT=$(stat -c %Y "$CAG_CACHE" 2>/dev/null || echo 0)
  if [ ! -s "$CAG_CACHE" ] || [ "$CAG_DIRT" != "$CAG_PREV" ] \
     || [ $(( $(date +%s) - CAG_AT )) -gt 900 ]; then
    C=$(cagefsctl --cagefs-status 2>/dev/null | head -1)
    if [ -n "$C" ]; then
      printf '%s\n' "$C" > "$CAG_CACHE.tmp" && mv -f "$CAG_CACHE.tmp" "$CAG_CACHE"
      chmod 600 "$CAG_CACHE" 2>/dev/null
      printf '%s' "$CAG_DIRT" > "$CAG_MARK"; chmod 600 "$CAG_MARK" 2>/dev/null
      CAG_AT=$(date +%s)
    fi
  fi
  C=$(cat "$CAG_CACHE" 2>/dev/null)
  [ -n "$C" ] && echo "cagefs $C"
  [ -n "$C" ] && [ "$CAG_AT" != "0" ] && echo "cagefs_at $CAG_AT"
  echo
  prof "guvenlik denetimleri (csf, modsec, cagefs)"
  echo "--- WHM services ---"
  # whmapi1 servicestatus UCUZ DEGIL: uretimde olculdu, 2,86 saniye (bir turun
  # en pahali adimi). Ama verdigi sey chkservd'nin SON TURUNUN sonucu; chkservd
  # dakikada bir calismiyor (olculdu: durum dosyalarinin mtime'i 60 saniyede
  # degismedi). Yani her dakika sormak ayni cevabi tekrar satin almakti.
  #
  # Artik chkservd YENI OLCUM YAPTIGINDA soruyoruz: durum dosyalarinin en yeni
  # mtime'i degistiyse whmapi1 calisir, degismediyse onceki cevap aynen yazilir.
  # Bu BAYATLATMA DEGIL — ayni soruyu tekrar sormamak; altindaki olcum zaten o
  # anda yapilmis olan. Kart "ne zaman olculdu"yu svc_at'ten okuyup yaziyor.
  # Guvenlik agi: chkservd dursa bile (mtime donar) 15 dakikada bir yine sorulur.
  SVC_CACHE="$DATA_DIR/.svc_cache"
  SVC_MARK="$DATA_DIR/.svc_mark"
  CHK_AT=$(stat -c %Y /var/run/chkservd/* 2>/dev/null | sort -rn | head -1)
  [ -n "$CHK_AT" ] || CHK_AT=0
  SVC_PREV=$(cat "$SVC_MARK" 2>/dev/null || echo "")
  SVC_AGE=$(( $(date +%s) - $(stat -c %Y "$SVC_CACHE" 2>/dev/null || echo 0) ))
  if [ ! -s "$SVC_CACHE" ] || [ "$CHK_AT" != "$SVC_PREV" ] || [ "$SVC_AGE" -gt 900 ]; then
    SVC_NEW=$(whmapi1 servicestatus 2>/dev/null | awk '$1=="enabled:"{e=$2} $1=="installed:"{i=$2} $1=="name:"{n=$2} $1=="running:"{print "svc", n, e+0, i+0, $2+0}')
    if [ -n "$SVC_NEW" ]; then
      printf '%s\n' "$SVC_NEW" > "$SVC_CACHE.tmp" && mv -f "$SVC_CACHE.tmp" "$SVC_CACHE"
      chmod 600 "$SVC_CACHE" 2>/dev/null
      printf '%s' "$CHK_AT" > "$SVC_MARK"; chmod 600 "$SVC_MARK" 2>/dev/null
    fi
  fi
  cat "$SVC_CACHE" 2>/dev/null
  # Olcum ani: chkservd'nin kendi tur zamani (dosya yoksa 0 = bilinmiyor).
  [ "$CHK_AT" != "0" ] && echo "svc_at $CHK_AT"
  echo
  prof "whm servis durumlari"
  echo "--- Root checks ---"
  echo "acct $(find /var/cpanel/users -maxdepth 1 -type f ! -name system 2>/dev/null | wc -l)"
  MQN=$(exim -bpc 2>/dev/null || echo -1)
  echo "mailq $MQN"
  # KUYRUGU KIM DOLDURUYOR: yalnizca kuyruk >= 25 iken (en dusuk uyari esigi;
  # normal gunde hic calismaz), 5 dk onbellek, en fazla 500 baslik dosyasi.
  # Exim spool'undaki -H dosyalarinda "-auth_id" (SMTP kimligi: posta adresi ya
  # da hesap) ve "-ident" (yerel gonderen uid, PHP mail()) var. Hesaba cevrilir:
  # adres -> /etc/userdomains, uid -> kullanici adi; cPanel hesabi olmayan
  # (uzaktan gelen, bounce) "other". Satirlar: "mailq_acct hesap sayi" (ilk 3),
  # "mailq_sampled N" (ornek buyuklugu — pay buna gore).
  MQC="$DATA_DIR/.mailq_cache"
  if [ "${MQN:-0}" -ge 25 ] 2>/dev/null; then
    if [ ! -s "$MQC" ] || [ $(( ACT_NOW - $(stat -c %Y "$MQC" 2>/dev/null || echo 0) )) -gt 300 ]; then
      python3 -I - <<'PYEOF' > "$MQC.tmp" 2>/dev/null && mv "$MQC.tmp" "$MQC"
import os, re, pwd, collections
spool = '/var/spool/exim/input'
files = []
for root, dirs, fs in os.walk(spool):
    for f in fs:
        if f.endswith('-H'): files.append(os.path.join(root, f))
    if len(files) >= 500: break
files = files[:500]
dom = {}
try:
    for ln in open('/etc/userdomains', errors='replace'):
        if ':' in ln:
            d, u = ln.split(':', 1); dom[d.strip().lower()] = u.strip()
except Exception:
    pass
cp = set(os.listdir('/var/cpanel/users')) if os.path.isdir('/var/cpanel/users') else set()
ok = re.compile(r'^[a-z][a-z0-9_.-]{0,31}$')
cnt = collections.Counter(); n = 0
for p in files:
    auth = ident = None
    try:
        with open(p, errors='replace') as f:
            for i, ln in enumerate(f):
                if i > 80: break
                ln = ln.strip()
                if ln.startswith('-auth_id '):
                    a = ln[9:].strip().lower()
                    if '@' in a: auth = dom.get(a.split('@', 1)[1])
                    elif ok.match(a): auth = a
                elif ln.startswith('-ident '):
                    v = ln[7:].strip()
                    if v.isdigit():
                        try: ident = pwd.getpwuid(int(v)).pw_name if int(v) >= 1000 else None   # sistem kullanicisi (root, mailnull) hesap degil
                        except KeyError: ident = None
                    elif ok.match(v): ident = v
    except Exception:
        continue
    acct = auth or ident
    if acct and cp and acct not in cp: acct = None
    n += 1
    cnt[acct or 'other'] += 1
for a, c in cnt.most_common(3): print('mailq_acct %s %d' % (a, c))
print('mailq_sampled %d' % n)
PYEOF
    fi
    cat "$MQC" 2>/dev/null
  else
    rm -f "$MQC"
  fi
  echo "mysql_ping $(timeout 3 mysqladmin ping >/dev/null 2>&1 && echo 1 || echo 0)"
  echo "websrv $(pgrep -x litespeed >/dev/null 2>&1 && echo litespeed || echo apache)"
  # Inode kullanimi (%): disk ALANI bos olsa da inode tukenince sunucu coker
  # (dosya olusturulamaz). Milyonlarca kucuk dosya (LiteSpeed cache vb) tuketir.
  # PHP inode'u kolay okuyamaz; root df -i verir.
  echo "inode_pct $(df -iP / | awk 'NR==2{gsub("%","",$5); print $5+0}')"
  # RAID sagligi (/proc/mdstat): RAID5/1 dizisinde tek disk sessizce olunce dizi
  # calismaya devam eder — ikincisi olene kadar fark edilmez. SMART'i smartd
  # zaten maille izliyor; buradaki bosluk DIZI durumu. "[U_]" bloğunda _ =
  # degraded; recovery/resync = eslesme/rebuild (kendini onariyor). rebuild,
  # degraded'i onceler (onariliyor demek). Dizi yoksa satir cikmaz.
  if [ -r /proc/mdstat ]; then
    RAID=$(awk '
      match($0,/\[[U_]+\]/){b=substr($0,RSTART,RLENGTH);a++;if(b~/_/){d=1;bad=b}else ok=b}
      /(recovery|resync|reshape)[[:space:]]*=/{if(match($0,/[0-9.]+%/)){p=substr($0,RSTART,RLENGTH);r=1}}
      END{if(!a)exit; if(r)print "resync "p; else if(d)print "degraded "bad; else print "ok "ok}' /proc/mdstat)
    if [ -n "$RAID" ]; then
      echo "raid $RAID"
      # mismatch_cnt: son RAID check'inde (haftalik scrub) kopya/parite arasinda
      # UYUSMAYAN blok sayisi. Saglikli dizide 0; >0 = sessiz veri bozulmasi riski
      # ("bozuk birim"). Diziler ayakta ([UUU]) olsa bile veri tutarsiz olabilir.
      # 0 dahil her zaman yazilir (dashboard 0'i yesil, >0'i turuncu gosterir).
      MM=0; for f in /sys/block/md*/md/mismatch_cnt; do [ -r "$f" ] && MM=$((MM + $(cat "$f" 2>/dev/null || echo 0))); done
      echo "raid_mismatch $MM"
    fi
  fi
  # SMART on-arizasi (SAATLIK cache): smartd zaten mail atiyor — burada SADECE
  # sorunlu diski gosteririz (FAILED saglik / realloc / pending sektorler).
  # Saglikli disk hic gorunmez (alarm-only). smartctl yoksa sessizce atlanir.
  SMC=$DATA_DIR/.smart_cache
  if command -v smartctl >/dev/null 2>&1 && { [ ! -f "$SMC" ] || [ $(( $(date +%s) - $(stat -c %Y "$SMC" 2>/dev/null || echo 0) )) -gt 3600 ]; }; then
    : > "$SMC.tmp"
    for D in $(lsblk -dno NAME,TYPE 2>/dev/null | awk '$2=="disk"{print $1}'); do
      H=$(smartctl -H "/dev/$D" 2>/dev/null | awk -F: '/overall-health/{gsub(/[ !]/,"",$2);print $2}')
      A=$(smartctl -A "/dev/$D" 2>/dev/null)
      RA=$(echo "$A" | awk '$2=="Reallocated_Sector_Ct"{print $10+0; exit}')
      PE=$(echo "$A" | awk '$2=="Current_Pending_Sector"{print $10+0; exit}')
      ISS=""
      [ "$H" = "FAILED" ] && ISS="FAILING"
      [ -n "$RA" ] && [ "$RA" -gt 0 ] 2>/dev/null && ISS="${ISS:+$ISS, }${RA} realloc"
      [ -n "$PE" ] && [ "$PE" -gt 0 ] 2>/dev/null && ISS="${ISS:+$ISS, }${PE} pending"
      [ -n "$ISS" ] && echo "smart_bad $D $ISS" >> "$SMC.tmp"
    done
    mv "$SMC.tmp" "$SMC"
  fi
  cat "$SMC" 2>/dev/null
  # Ag hat hizi (Mbps): CageFS altinda PHP /sys/class/net'i okuyamaz (disk I/O gibi
  # root verir). SADECE up + fiziksel (device symlink'i olan) + gecerli hizli
  # (speed>0; -1 = down/virtio bildirmiyor) arayuzler. Cache YOK: cat bedava, link
  # hizi degisirse dakikada guncellenir. PHP her arayuzu KENDI hizina oranlar,
  # max'i alir (toplama degil) — atil port (IP'siz eth2 gibi) 0% cikar, sismez.
  for IF in /sys/class/net/*; do
    N=${IF##*/}; [ "$N" = lo ] && continue
    [ -e "$IF/device" ] || continue
    [ "$(cat "$IF/operstate" 2>/dev/null)" = up ] || continue
    SP=$(cat "$IF/speed" 2>/dev/null || echo -1)
    [ "$SP" -gt 0 ] 2>/dev/null && echo "netspeed $N $SP"
  done
  # Dort sayim TEK geciste, tek anlik goruntuden (eskiden 4 ayri "ps" idi).
  read PS_LT PS_LI PS_DS PS_RS < <(awk '
      $6=="lsphp" && $1 ~ /^[RD]/ {a++}
      $6=="lsphp" && $1 ~ /^S/    {b++}
      $1 ~ /^D/ {c++}
      $1 ~ /^R/ {d++}
      END{print a+0, b+0, c+0, d+0}' "$PS_COMM")
  echo "lsphp_total $PS_LT"
  echo "lsphp_idle $PS_LI"
  # D-state: diskte bloklanan surec sayisi — "load yuksek ama CPU dusuk" teshisinin anahtari
  echo "dstate $PS_DS"
  # rstate: kosan (R) surec sayisi. Load anatomisi: load ~ R + D (uninterruptible).
  # Root'tan alinir cunku CageFS surec sayimini cage'e sanallastirabilir.
  echo "rstate $PS_RS"
  # CPU/IO wait 60 sn ortalamasi (yukarida hesaplandi) — dashboard'un anlik
  # olcumunun yerine gecer; ilk calismada bos oldugu icin hic yazilmaz.
  [ -n "$CPU" ] && echo "cpu_pct $CPU"
  [ -n "$IOW" ] && echo "iowait_pct $IOW"
  [ -n "$NET_RATE" ] && echo "net_rate $NET_RATE"
  # Aktivite yaslari (dashboard cipleri): TUM surec listesinde en eski eslesen
  # surecin etimes'i — Top-15 CPU tablosundan hesaplamak yaniltiyordu (pkgacct
  # her hesapta yeniden dogar, "10 saatlik yedek" 1m gorunurdu). Koseli parantez
  # hilesi ([p]kgacct) awk'in kendi komut satirini eslemesini onler.
  # backup: gorev-omurlu surecler, dogrudan gozlem (esik gerekmez).
  # pkgacct cagrisinda o an paketlenen HESAP argumanda duruyor: 'pkgacct user ...'.
  # Olay kaydina yazilinca "yedekleme basladi" yerine kimin yedeklendigi gorunur.
  # Yalnizca cPanel kullanici adi bicimine uyan jeton kabul edilir (kucuk harf +
  # rakam, en fazla 16) — secenek/yol/cop deger rozete sizmasin.
  # TUR: orkestrator (cpbackup / bin/backup) gorunuyorsa bu cPanel'in TAM yedegi
  # (gece, tum hesaplar) -> act_backup_k full_backup; pano "yedekleme basladi ·
  # tam yedek" yazar, bitiste kapsam "*" oldugu icin "tum hesaplar" der. Hesap
  # (_p) o an paketlenen = en YENI pkgacct'in argumani; cip "· tam yedek · hesap"
  # gosterir. Tek pkgacct (elle tek hesap yedegi) ise tur yok, hesap yazilir.
  # HESAP YOKSA ne eslestigi yazilir (act_backup_k = programin adi, or. cpbackup_
  # transporter): "yedekleme basladi" tek basina neyin calistigini soylemiyordu.
  # KENDINI ESLEME: bu awk'in kendi komut satiri da ps ciktisinda gorunur (ps ile
  # awk ayni anda baslar, yaris). Programdaki HER desen koseli parantezli yazilir
  # ([p]kgacct) ki metin olarak "pkgacct" gecmesin; ek guvence olarak komutu awk
  # olan satirlar atlanir. Eskiden hesap deseni duz /pkgacct$/ idi ve yaris
  # kaybedilince yasi 0, hesabi olmayan sahte "yedekleme basladi/bitti" ciftleri
  # dusuyordu (takvim disi gunlerde gorulen anonim yedek satirlari).
  read A ABK AFULL < <(ps_etimes_args | awk -v tr="$ACT_TRACE" -v ts="$ACT_TS" "$PS_SKIP2"'
    /[p]kgacct|[c]pbackup|cpanel\/[b]in\/backup/ {
      print ts, "act_backup", $0 >> tr
      if ($1 > m) { m = $1
        for (i = 2; i <= NF; i++) if ($i ~ /[p]kgacct|[c]pbackup|cpanel\/[b]in\/backup/) { n = split($i, a, "/"); prog = a[n]; gsub(/[^A-Za-z0-9_.-]/, "_", prog); break } }
      if ($0 ~ /[c]pbackup( |$)|cpanel\/[b]in\/backup( |$)/) full = 1
      if ($0 ~ /[p]kgacct/)
        for (i = 2; i <= NF; i++)
          if ($i ~ /[p]kgacct$/) {
            for (j = i + 1; j <= NF; j++)
              if ($j ~ /^[a-z][a-z0-9]{0,15}$/) { if (pm == "" || $1 < pm) { pm = $1; u = $j }; break }
            break
          } }
    END { if (m) print m, (u == "" ? "-" : u), (full ? "full_backup" : (u == "" && prog != "" ? prog : "-")) }')
  act_age act_backup "$A" "$ABK" "$AFULL"
  [ -n "$ACT_AGE" ] && { echo "act_backup $ACT_AGE"; echo "act_backup_p ${ABK:--}"; [ "${AFULL:--}" != "-" ] && echo "act_backup_k $AFULL"; }
  [ -n "$ACT_LIVE" ] && echo "act_backup_live $ACT_LIVE"
  [ -n "$ACT_END" ] && echo "act_backup_end $ACT_END"
  [ -n "$ACT_END_P" ] && echo "act_backup_end_p $ACT_END_P"
      [ -n "$ACT_END_K" ] && echo "act_backup_end_k $ACT_END_K"
  # update: cPanel upcp/updatenow + sistem paket guncellemeleri (dnf/yum) —
  # gece yuku faillerinden; backup gibi gorev-omurlu, esik gerekmez.
  A=$(ps_etimes_args | awk -v tr="$ACT_TRACE" -v ts="$ACT_TS" "$PS_SKIP2"'/[u]pcp|[u]pdatenow|[d]nf (upgrade|update)|[y]um (upgrade|update)/{print ts, "act_update", $0 >> tr; if($1>m)m=$1} END{if(m)print m}')
  act_emit act_update "$A"
  # wpt: PARTININ KENDISI izlenir. execute-background-task.php parti basinda dogar,
  # parti bitince olur — yani etimes'i DOGRUDAN kampanya yasidir, esige de grace'e de
  # ihtiyac duymaz. Canlida olculdu: parti 930 sn kosuyordu, eski esik+grace yontemi
  # 780 sn buluyordu ve kisa gorevlerin CPU sicramalarini yakalamaya calistigi icin
  # arada sonup yaniyordu.
  # Kalici yurutuculer bu desene UYMAZ (scheduled-tasks-executor / background-tasks-
  # executor, 3.8 gunluk) — "execute-background-task" ikisinin de alt dizesi degil.
  # Ikinci sart parti disindaki WPT etkinligi icin eski sezgiseli korur: kalici
  # sw-engine-fpm havuzu bosta %0'da gezdigi icin CPU esigi onu eler.
  # HESAP ve IS TURU: partinin wp-cli cocugu "--path=/home/<hesap>/public_html
  # plugin update" tasir (iz dosyasinda goruldu). En YENI wp-cli = o an islenen
  # hesap; tur = --path'ten sonraki iki duz kelime ("plugin update"). Parti bircok
  # hesabi dolasir: baslangic satirina hesap yazilmaz (cipte gorunur), bitiste
  # kapsam "*" -> "birden fazla hesap"; tek hesaplik iste adi.
  read A AWP AWK < <(ps_etimes_pcpu_args | awk -v tr="$ACT_TRACE" -v ts="$ACT_TS" "$PS_SKIP3"'
    /[e]xecute-background-task/ || ($2>=15 && /[w]p-toolkit|[w]ordpress-toolkit/) {
      print ts, "act_wpt", $0 >> tr
      if ($1 > m) m = $1
      if ($0 ~ /[w]pt-wp-cli\.php/ && (pm == "" || $1 < pm))
        for (i = 3; i <= NF; i++)
          if ($i ~ /^--path=\/home[0-9]*\/[^\/]+/) {
            split($i, p, "/")
            if (p[3] ~ /^[a-z][a-z0-9]{0,15}$/) {
              pm = $1; u = p[3]; k = ""
              for (j = i + 1; j <= NF && j <= i + 2; j++) if ($j ~ /^[a-z][a-z0-9-]*$/) k = k (k == "" ? "" : "_") $j
            }
            break
          } }
    END { if (m) print m, (u == "" ? "-" : u), (k == "" ? "-" : k) }')
  act_age act_wpt "$A" "$AWP" "$AWK"
  [ -n "$ACT_AGE" ] && { echo "act_wpt $ACT_AGE"; echo "act_wpt_p ${AWP:--}"; [ "${AWK:--}" != "-" ] && echo "act_wpt_k $AWK"; }
  [ -n "$ACT_LIVE" ] && echo "act_wpt_live $ACT_LIVE"
  [ -n "$ACT_END" ] && echo "act_wpt_end $ACT_END"
  [ -n "$ACT_END_P" ] && echo "act_wpt_end_p $ACT_END_P"
      [ -n "$ACT_END_K" ] && echo "act_wpt_end_k $ACT_END_K"
  # appdisc: cPanel wappspector (uygulama kesfi, WP Toolkit envanterini besler) —
  # hesap hesap kisa turlarla doner; WPT gibi CPU esikli (pcpu>=15) surec sezgiseli.
  # Taranan hesap YOL argumanindan gelir: wappspector hesap adi almiyor,
  # 'wappspector:inspect [<path>]' aliyor ve cPanel onu /home/<hesap>/... uzerinde
  # kosturuyor. /home2 gibi ikincil koklar da kabul edilir. Yalnizca cPanel
  # kullanici adi bicimine uyan jeton alinir; yol parcasi rozete cop basmasin.
  read A APD < <(ps_etimes_pcpu_args | awk -v tr="$ACT_TRACE" -v ts="$ACT_TS" "$PS_SKIP3"'
    $2 >= 15 && /[w]appspector/ {
      print ts, "act_appdisc", $0 >> tr
      if ($1 > m) { m = $1; u = ""
        for (i = 3; i <= NF; i++)
          if ($i ~ /^\/home[0-9]*\/[^\/]+/) {
            split($i, p, "/")
            if (p[3] ~ /^[a-z][a-z0-9]{0,15}$/) u = p[3]
            break
          } } }
    END { if (m) print m, (u == "" ? "-" : u) }')
  act_age act_appdisc "$A" "$APD"
  [ -n "$ACT_AGE" ] && { echo "act_appdisc $ACT_AGE"; echo "act_appdisc_p ${APD:--}"; }
  [ -n "$ACT_LIVE" ] && echo "act_appdisc_live $ACT_LIVE"
  [ -n "$ACT_END" ] && echo "act_appdisc_end $ACT_END"
  [ -n "$ACT_END_P" ] && echo "act_appdisc_end_p $ACT_END_P"
  # ── Ayzeta Backup ───────────────────────────────────────────────
  # Kurulu degilse HICBIR SEY yayinlanmaz; pano da satiri hic gostermez.
  # OTORITER kaynak is kayitlari: ps sezgiseli burada yaniltir, cunku bir is
  # altinda pkgacct/tar/gzip/perl/php gibi bircok surec doguyor — surec sayisi da
  # etimes'i da isin yasi degildir. meta.json 'started' alani kesin baslangictir.
  # Canlilik olcutu aracin KENDI olcutu (ar_job_liveness): 'finished' dosyasi yok
  # VE pid canli VE /proc/<pid>/cmdline is kimligini tasiyor; pid 0 ise 'updated'
  # 600 sn'den yeni. Yalnizca "running" durumuna bakmak yetmez — isci oldurulurse
  # durum 'running'de kalir.
  # Yalnizca yedekleme turleri rozete girer; geri yukleme/okuma/tarama isleri degil.
  AYZ_MARK=/usr/local/cpanel/whostmgr/docroot/cgi/ayzeta_backup/version.json
  if [ -f "$AYZ_MARK" ]; then
    read AYZ_AGE AYZ_P AYZ_FIN AYZ_K < <(python3 - /var/cpanel/ayzeta_backup/jobs <<'PYEOF'
import json, os, sys, time

# Her is turu sayilir; tur gizlenmez, rozete yazilir. Gruplama yalnizca
# etiket okunur kalsin diye — PHP/JS tarafi bu jetonu ceviriyor.
GRUP = {
    "backup": "backup", "yapilandirma": "backup", "tamamla": "backup",
    "single": "restore", "batch": "restore", "dosya": "restore",
    "posta": "restore", "vt": "restore", "cron_uygula": "restore",
    "scan": "archive check", "indir": "download",
    "liste": "read", "vt_oku": "read", "cron_oku": "read",
}
root = sys.argv[1]
now = int(time.time())
best_started, best_scope, best_kind = None, "", ""
# Yakin zamanda BITEN isin otoriter bitis damgasi. Kampanya durumundan cikarilan
# "son gorulme" bir dakikaya kadar sapabiliyor; meta.json'daki finished_at kesin.
# Arsive bakmiyoruz: arsive tasima varsayilani 30 gun, panonun ilgilendigi pencere
# bir saat — yakin isler her zaman jobs/ altinda.
latest_fin = None
# Son biten isin tur/hesabi: canli is yokken rozet bunlarla dolar.
fin_kind, fin_scope = "", ""

def canli(pid, job_id, updated):
    if not pid:                                   # pid 0: son yazma taze mi
        return updated and (now - updated) <= 600
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return job_id.encode() in f.read()
    except Exception:
        return False

try:
    girisler = os.listdir(root)
except Exception:
    girisler = []

for ad in girisler:
    d = os.path.join(root, ad)
    if not os.path.isdir(d):
        continue
    bitti = os.path.join(d, "finished")
    if os.path.exists(bitti):
        # 'finished' dosyasinin mtime'i ucuz on eleme: yalnizca son bir saatte
        # biten islerin meta.json'u okunur, 30 gunluk arsiv taranmaz.
        try:
            if now - int(os.stat(bitti).st_mtime) <= 3600:
                with open(os.path.join(d, "meta.json"), "rb") as f:
                    mb = json.load(f)
                fa = mb.get("finished_at")
                if mb.get("kind") in GRUP and isinstance(fa, int) and 0 < fa <= now:
                    if latest_fin is None or fa > latest_fin:
                        latest_fin = fa
                        fin_kind = GRUP[mb["kind"]]
                        fin_scope = (mb.get("current") or mb.get("user") or "").strip()
        except Exception:
            pass
        continue
    try:
        with open(os.path.join(d, "meta.json"), "rb") as f:
            m = json.load(f)
    except Exception:
        continue
    grup = GRUP.get(m.get("kind"))
    if grup is None:
        continue          # bilinmeyen tur: sessizce atla
    started = m.get("started")
    if not isinstance(started, int) or started <= 0 or started > now:
        continue
    if not canli(int(m.get("pid") or 0), str(m.get("id") or ad), m.get("updated")):
        continue
    # En ESKI canli is kazanir: "ne zamandir yedekleme suruyor" sorusunun cevabi o.
    if best_started is None or started < best_started:
        best_started = started
        best_scope = (m.get("current") or m.get("user") or "").strip()
        best_kind = grup

# Anlik goruntu satiri BOSLUKLA ayrilir, bu yuzden bosluk kalamaz. Virgul korunur:
# kuyrukta 'current' "hesap1, hesap2" olabiliyor, virgulu atmak iki hesap adini tek
# kelimeye yapistirip okunaksiz yapiyordu. Uc alan: yas, kapsam, otoriter bitis.
# Canli is yoksa son biten isin bilgisi kullanilir (kampanya payi penceresi).
if best_started is None:
    best_scope = best_scope or fin_scope
    best_kind = best_kind or fin_kind
kapsam = "".join(c for c in best_scope if c.isalnum() or c in "._-, ")[:28].strip()
kapsam = kapsam.replace(", ", ",").replace(" ", "_")
print("%s %s %s %s" % (
    (now - best_started) if best_started is not None else "-",
    kapsam or "-",
    latest_fin if latest_fin is not None else "-",
    best_kind.replace(" ", "_") or "-"))
PYEOF
)
    [ "$AYZ_AGE" = "-" ] && AYZ_AGE=""
    [ "$AYZ_FIN" = "-" ] && AYZ_FIN=""
    act_age act_ayzbackup "$AYZ_AGE" "$AYZ_P" "$AYZ_K"
    [ -n "$ACT_AGE" ] && { echo "act_ayzbackup $ACT_AGE"; echo "act_ayzbackup_p ${AYZ_P:--}"; echo "act_ayzbackup_k ${AYZ_K:--}"; }
    [ -n "$ACT_LIVE" ] && echo "act_ayzbackup_live $ACT_LIVE"
    if [ -n "$ACT_END" ]; then
      # OTORITER bitis varsa onu yaz. Guard IKI YONLU: damga bizim cikardigimiz
      # bitisin +/-2 dk'si icinde VE gelecekte olmamali. Ust sinir sart: bitis
      # kaydi bir saat saklaniyor, o surede YAKALANMAMIS kisa bir is (okuma,
      # indirme) bitse onun finished_at'i eski kampanyanin "bitti" satirina
      # yazilirdi. Alt sinir da baska/eski bir isin damgasini eler. Durdurulan ya
      # da coken iste finished_at hic yazilmaz; o zaman son gorulme ani kullanilir.
      AYZ_END=$ACT_END
      if [ -n "$AYZ_FIN" ] && [ "$AYZ_FIN" -ge $(( ACT_END - 120 )) ] \
         && [ "$AYZ_FIN" -le $(( ACT_END + 120 )) ] \
         && [ "$AYZ_FIN" -le "$ACT_NOW" ]; then AYZ_END=$AYZ_FIN; fi
      echo "act_ayzbackup_end $AYZ_END"
      [ -n "$ACT_END_P" ] && echo "act_ayzbackup_end_p $ACT_END_P"
      [ -n "$ACT_END_K" ] && echo "act_ayzbackup_end_k $ACT_END_K"
    fi
  fi
  # ── csf-autogroup ───────────────────────────────────────────────
  # KURULU MU: root crontab'indaki satir. Durum dizini (/var/lib/csf_autogroup)
  # olcut DEGIL — kaldirilmis kurulumdan kalabiliyor. Crontab satiri ayrica
  # betigin tam yolunu veriyor; yol sabit degil, depo nereye klonlandiysa orada.
  CAG_SH=$(awk '/[c]sf_autogroup\.sh/ && $0 !~ /^[[:space:]]*#/ {
      for (i = 1; i <= NF; i++) if ($i ~ /[c]sf_autogroup\.sh$/) { print $i; exit } }' \
    /var/spool/cron/root 2>/dev/null)
  A=""
  if [ -n "$CAG_SH" ]; then
    # CALISIYOR MU: yalnizca betigin GERCEKTEN calistirildigi bicim sayilir:
    # '/bin/bash <yol>' (shebang, NF=3) ya da argv[0] olarak '<yol>' (NF=2), baska
    # argumansiz. Gercek tur argumansiz kosar; '--status --json' (eklenti
    # sayfasi), '--lookup', '--dry-run' tur degildir ve elenir. Kilide BAKILMAZ:
    # panelden yapilan elle islemler de ayni kilidi birkac saniye tutuyor.
    # ESKIDEN "yol ile biten her satir" sayiliyordu: 'vim <yol>', 'cat <yol>' ve
    # (ps satir sonunu ham basan surumlerde) bu awk'in kendi '-v sh=<yol>' argumani
    # da eslesiyor, takvim disi sahte "csf-autogroup basladi" dusuyordu.
    A=$(ps_etimes_args | awk -v sh="$CAG_SH" -v tr="$ACT_TRACE" -v ts="$ACT_TS" "$PS_SKIP2"'
      (NF <= 2 && $2 == sh) || (NF <= 3 && $2 ~ /(^|\/)(bash|sh|dash)$/ && $3 == sh) { print ts, "act_csfag", $0 >> tr; if ($1 > m) m = $1 }
      END { if (m) print m }')
    # SON TAMAMLANAN TUR: events.jsonl'in son '"type":"run"' satiri. Satir tur
    # BITINCE yazilir, yani 't' gercek bitis ani. Yarim yazilmis satira karsi tam
    # JSON desenine capalanir. Sayac dosyasinin mtime'i OLCUT DEGIL: panelden
    # yapilan elle islemler (ban, kaldirma) de onu degistiriyor.
    CAG_EV=$(awk -F= '/^EVENTS_FILE=/{gsub(/"/, "", $2); print $2; exit}' \
      "${CAG_SH%/*}/config.env" 2>/dev/null)
    if [ -z "$CAG_EV" ]; then
      CAG_EV=$(awk -F= '/^SAYAC_FILE=/{gsub(/"/, "", $2); print $2; exit}' \
        "${CAG_SH%/*}/config.env" 2>/dev/null)
      case "$CAG_EV" in */*) CAG_EV="${CAG_EV%/*}";; *) CAG_EV="";; esac
      CAG_EV="${CAG_EV:-/var/lib/csf_autogroup}/events.jsonl"
    fi
    CAG_T=""; CAG_BLK=0
    if [ -r "$CAG_EV" ]; then
      read -r CAG_T CAG_BLK < <(grep '"type":"run"' "$CAG_EV" 2>/dev/null \
        | grep -E '^\{"t":[0-9]+,.*\}$' | tail -1 | awk '
            { t = ""; b = 0
              if (match($0, /"t":[0-9]+/))          t  = substr($0, RSTART+4,  RLENGTH-4)
              if (match($0, /"added":[0-9]+/))      b += substr($0, RSTART+8,  RLENGTH-8)
              if (match($0, /"temp_added":[0-9]+/)) b += substr($0, RSTART+13, RLENGTH-13)
              if (match($0, /"promoted":[0-9]+/))   b += substr($0, RSTART+11, RLENGTH-11)
              if (t != "") print t, b }')
      case "$CAG_T" in ''|*[!0-9]*) CAG_T=""; CAG_BLK=0;; esac
      case "$CAG_BLK" in ''|*[!0-9]*) CAG_BLK=0;; esac
    fi
  fi
  # Turlar 4-25 sn suruyor ve cron varsayilani 30 dk: dakikada bir bakan toplayici
  # cogu turu kacirir. Amac zaten TAKILIP KALAN turu gostermek — o durumda surec
  # ayakta kalir, rozet durur ve yasi buyur. YAKALANAN turun bitisi ise tur
  # kaydindan gercek damgayi ve o turda konan engel sayisini alir; kacirilan tur
  # hic yazilmaz, yani olay kaydi 30 dakikalik rutinle dolmaz.
  # Burada artık özel bir ayar yok: rozet BÜTÜN etkinliklerde kanıta bağlı, yani
  # yalnızca süreç o tikte görüldüğünde çıkıyor. Bu turu 5DK/9DK diye gösteren
  # kusur (ölçüldü 2026-10-21: cron */30, 'ps' boş, rozet büyüyordu) oradan geliyordu.
  act_age act_csfag "$A"
  [ -n "$ACT_AGE" ] && echo "act_csfag $ACT_AGE"
  [ -n "$ACT_LIVE" ] && echo "act_csfag_live $ACT_LIVE"
  if [ -n "$ACT_END" ]; then
    # Guard IKI YONLU: kayit bu kampanyanin bitisine +/-2 dk icinde olmali. Tek
    # yonlu olsa (yalnizca "gelecekte degil") bitis kaydi bir saat saklandigi icin
    # arada YAKALANMAMIS bir tur kosunca onun damgasi eski "bitti" satirina yazilirdi.
    # Tur sona erdikten saniyeler sonra kayda dusuyor, pencere bu yuzden dar.
    CAG_END=$ACT_END
    if [ -n "${CAG_T:-}" ] && [ "$CAG_T" -ge $(( ACT_END - 120 )) ] \
       && [ "$CAG_T" -le $(( ACT_END + 120 )) ]; then
      CAG_END=$CAG_T
      [ "${CAG_BLK:-0}" -gt 0 ] && echo "act_csfag_fb $CAG_BLK"
    fi
    echo "act_csfag_end $CAG_END"
  fi
  # ── Guncelleme durumu ───────────────────────────────────────────
  # REPO_DIR config.env'den gelir (kurulumun calistigi git kopyasi). Yoksa bu blok
  # tamamen atlanir — panoda guncelleme satiri hic gorunmez.
  if [ -n "${REPO_DIR:-}" ] && [ -d "$REPO_DIR/.git" ] && command -v git >/dev/null 2>&1; then
    UPD_CACHE="$DATA_DIR/.upd_cache"; UPD_STATE="$DATA_DIR/.upd_state"
    # Yerel revizyon HER TURDA okunur. Agsiz, yerel bir git cagrisi (~10 ms) —
    # guncelleme ELLE de yapilabildigi icin degisimi yakalamanin tek guvenilir
    # yolu bu; dosya tarihine bakmak config yeniden yazilinca da tetiklenirdi.
    LREV=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null)
    read SREV SAT SOLD < <(cat "$UPD_STATE" 2>/dev/null)
    if [ -n "$LREV" ]; then
      echo "upd_rev $LREV"
      if [ -z "$SREV" ]; then
        # Ilk calisma: taban kaydedilir, guncelleme olayi URETILMEZ.
        printf '%s %s\n' "$LREV" "$ACT_NOW" > "$UPD_STATE"
      elif [ "$SREV" != "$LREV" ]; then
        printf '%s %s %s\n' "$LREV" "$ACT_NOW" "$SREV" > "$UPD_STATE"
        SAT=$ACT_NOW; SOLD=$SREV
      fi
      chmod 600 "$UPD_STATE" 2>/dev/null
    else
      # git bir tur okunamadi (update.sh calisirken index.lock, gecici hata):
      # kayitli durumdan yayinlamaya devam. Eskiden bu turda upd_at hic
      # yayinlanmiyor, sayfa "guncelleme yok" sayip bir sonraki turda AYNI
      # guncellemeyi ikinci kez yaziyordu.
      [ -n "${SREV:-}" ] && echo "upd_rev $SREV"
    fi
    # Son guncelleme ACT_RETAIN (1 sa) icindeyse olay kaydina dussun: sayfayi
    # sonradan acan da gorsun, act_*_end ile ayni mantik.
    if [ -n "${SOLD:-}" ] && [ $(( ACT_NOW - ${SAT:-0} )) -le "$ACT_RETAIN" ]; then
      echo "upd_at $SAT"; echo "upd_from $SOLD"
    fi
    # Uzaktaki surum: GUNDE BIR (tek ag erisimi). Basarisiz olursa eski cache
    # korunur; "guncel" diye yanlis bilgi vermektense bayat bilgi daha iyi.
    if [ ! -f "$UPD_CACHE" ] \
       || [ $(( ACT_NOW - $(stat -c %Y "$UPD_CACHE" 2>/dev/null || echo 0) )) -gt 86400 ]; then
      UPD_BR=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null)
      if [ -n "$UPD_BR" ] && timeout 60 git -C "$REPO_DIR" fetch --quiet origin "$UPD_BR" 2>/dev/null; then
        UPD_RREV=$(git -C "$REPO_DIR" rev-parse --short "origin/$UPD_BR" 2>/dev/null)
        UPD_BEH=$(git -C "$REPO_DIR" rev-list --count "HEAD..origin/$UPD_BR" 2>/dev/null)
        printf '%s %s\n' "${UPD_RREV:--}" "${UPD_BEH:-0}" > "$UPD_CACHE.tmp" \
          && mv "$UPD_CACHE.tmp" "$UPD_CACHE"
        chmod 600 "$UPD_CACHE" 2>/dev/null
      fi
    fi
    read UPD_RREV UPD_BEH < <(cat "$UPD_CACHE" 2>/dev/null)
    # GERIDE KALINAN TUR SAYISI HER TURDA YENIDEN SAYILIR — ag erisimi YOK, yalnizca
    # yereldeki 'origin/<dal>' isaretcisi okunur. Fetch gunde bir yeterli ama SAYI
    # oyle degil: guncelleme uygulanir uygulanmaz 0'a dusmesi gerekiyor. Eskiden sayi
    # da onbellekten geliyordu ve kullanici guncelledikten sonra footer 24 saate kadar
    # "guncelleme var" demeye devam ediyordu.
    UPD_BRL=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [ -n "$UPD_BRL" ]; then
      UPD_BEHL=$(git -C "$REPO_DIR" rev-list --count "HEAD..origin/$UPD_BRL" 2>/dev/null)
      case "${UPD_BEHL:-}" in ''|*[!0-9]*) ;; *) UPD_BEH=$UPD_BEHL;; esac
    fi
    case "${UPD_BEH:-0}" in ''|*[!0-9]*) UPD_BEH=0;; esac
    if [ "$UPD_BEH" -gt 0 ]; then
      echo "upd_behind $UPD_BEH"
      # Otomatik uygulama: VARSAYILAN KAPALI, yalnizca config.env acikca 1 ise.
      # Ayrik surec (setsid): toplayici kendi turunu bitirir; install.sh dosyalari
      # atomik degistirdigi icin calisan betik etkilenmez. flock ust uste
      # calismayi onler — update.sh ~20 sn surer, cron ise dakikada bir koser.
      if [ "${AUTO_UPDATE:-0}" = "1" ] && command -v flock >/dev/null 2>&1; then
        flock -n "$DATA_DIR/.upd_run.lock" \
          setsid bash "$REPO_DIR/update.sh" >/dev/null 2>&1 &
      fi
    fi
  fi
  # imunify: OTORITER kaynak — ajanin kendi kayitlari (running durumundaki en eski
  # taramanin yasi). Surec sezgiseli burada calismaz: tarama kalici rustbolit
  # --resident icinde kosar, ps pcpu'su omur-boyu ortalama oldugundan iki yonde
  # de yanilir. CLI ~1-2 sn python; timeout korumali, dakikada bir kabul edilebilir.
  # Gercek cikti dogrulamasi (Tem 2026): ust seviye {"max_count":N,"items":[...]},
  # durum alani "scan_status" (dokumantasyondaki "status" DEGIL), "started" epoch sn.
  # Cikti: "yas dosya_sayisi" — dosya sayisi KAPSAM'i verir (haftalik tam sweep
  # binlerce dosya, artimli/degisen-dosya taramasi bir avuc). Kapsami temsil eden
  # tarama = kosanlar icinde en cok total_resources'lu olan.
  # Cikti: "yas dosya_sayisi tip". Kosan taramada total_resources genelde 0
  # (Imunify saymayi bitirince dolar), o yuzden asil ayirt edici PATH:
  # /home/<hesap> = o hesabin taramasi (hesap adini goster), sistem yolu =
  # degisen-dosya gurultusu (incremental).
  # 5 DK CACHE: CLI ~1.2 sn CPU/dakika ederdi; tarama yasi/hedefi yavas degisir,
  # 5 dk bayat veri sorun degil. Cache "yas dosya tip" satiri tutar (bos olabilir).
  IMC=$DATA_DIR/.imunify_cache
  if [ ! -f "$IMC" ] || [ $(( $(date +%s) - $(stat -c %Y "$IMC" 2>/dev/null || echo 0) )) -gt 300 ]; then
    if timeout 10 imunify360-agent malware on-demand list --json 2>/dev/null | python3 -c '
import sys, json, time
try:
    d = json.load(sys.stdin)
    items = d if isinstance(d, list) else d.get("items", d.get("data", []))
    run = [s for s in items if s.get("scan_status", s.get("status")) == "running" and s.get("started")]
    if run:
        top = max(run, key=lambda s: (s.get("total_resources") or s.get("total") or 0))
        age = int(time.time() - min(s["started"] for s in run))
        n = top.get("total_resources") or top.get("total") or 0
        # Tip etiketi: /home/<hesap>/... ise hesap adi (gercek hesap taramasi),
        # degilse incremental (degisen sistem dosyasi gurultusu). Imunify kosan
        # taramada haftalik/artimli ayrimini temiz vermez; taranan hedefi gosteririz.
        parts = [x for x in (top.get("path") or "").split("/") if x]
        if len(parts) >= 2 and parts[0] == "home":
            p = "".join(c for c in parts[1] if c.isalnum() or c in "._-")[:20] or "-"
        else:
            p = "incremental"
        print("%d %d %s" % (age, n, p), end="")
    else:
        print("none", end="")           # sorgu BASARILI, kosan tarama yok
except Exception:
    sys.exit(1)                         # sorgu BASARISIZ — ikisi ayni sey degil
' > "$IMC.tmp" 2>/dev/null; then
      mv "$IMC.tmp" "$IMC"
    else
      # Sondaya guvenilemez: eski cache'e DOKUNMA. mtime eski kaldigi icin hem
      # bir sonraki dakikada tekrar denenir, hem de "tazelenemedi" sinyali olur.
      rm -f "$IMC.tmp"
    fi
  fi
  # Yas ajanin kendi kaydindan gelir — TEK tarama icin kesin. Ama sweep hesap hesap
  # ayri kayitlar uretiyorsa her hesapta sifirlanir; act_age tabandan yukseltir.
  # BASARILI sorgu cache'i HER ZAMAN yeniden yazar; dolayisiyla cache'in hala eski
  # olmasi "tazelenemedi"nin ta kendisidir. Bayat icerigi guncelmis gibi okumak yerine
  # act_age'e "?" verip onceki durumu tasiyoruz (hesap adi/dosya sayisi korunur).
  # IM_BLIND_MAX: korlugu sonsuza kadar surdurup "hep tarama var" demeyelim diye ust
  # sinir. Asilirsa bilinmeyen birakmayiz — son DOGRULANMIS goruntuye gore kesin
  # sonuclandiririz (act_age normal yoluyla bitisi pl anina yazar). Bu sinir sondanin
  # kac dakikadir okuyamadigiyla ilgilidir; ISIN suresiyle degil — sonda calistigi
  # surece 40 saatlik bir tarama da sorunsuz izlenir.
  IM_BLIND_MAX=3600
  IMT=$(stat -c %Y "$IMC" 2>/dev/null || echo 0)
  IMC_AGE=$(( ACT_NOW - IMT ))
  A=$(cat "$IMC" 2>/dev/null)
  IM_AGE=""; IM_N=""; IM_P=""
  case "$A" in none|'') ;; *) read IM_AGE IM_N IM_P <<< "$A" ;; esac
  if [ "$IMT" -eq 0 ] || [ "$IMC_AGE" -gt 300 ]; then
    if [ "$IMC_AGE" -le "$IM_BLIND_MAX" ]; then IM_AGE="?"; else IM_AGE=""; fi
  fi
  act_age act_imunify "$IM_AGE" "$IM_P"; IM_AGE=$ACT_AGE
  [ -n "$IM_AGE" ] && { echo "act_imunify $IM_AGE"; echo "act_imunify_n $IM_N"; echo "act_imunify_p $IM_P"; }
  [ -n "$ACT_LIVE" ] && echo "act_imunify_live $ACT_LIVE"
  [ -n "$ACT_END" ] && echo "act_imunify_end $ACT_END"
  [ -n "$ACT_END_P" ] && echo "act_imunify_end_p $ACT_END_P"
  # Threads_running: o an sorgu isleyen thread — "kisa ama cok sorgu" senaryosunu gosterir
  THR=$(timeout 3 mysqladmin extended-status 2>/dev/null | awk '$2=="Threads_running"{print $4}')
  [ -n "$THR" ] && echo "mysql_thr $THR"
  # Disk R/W hizi (KB/s, 1 sn ornek): CageFS icindeki PHP /proc/diskstats'i
  # GOREMIYOR (canli testte dogrulandi) — IO Wait metasinin R/W kismi root'tan gelir.
  # Sadece tam diskler (partition cift sayar); sektor = 512 bayt.
  DRE='^(sd[a-z]+|nvme[0-9]+n[0-9]+|vd[a-z]+|xvd[a-z]+)$'
  read R1 W1 < <(awk -v re="$DRE" '$3 ~ re {r+=$6; w+=$10} END{print r+0, w+0}' /proc/diskstats)
  sleep 1
  read R2 W2 < <(awk -v re="$DRE" '$3 ~ re {r+=$6; w+=$10} END{print r+0, w+0}' /proc/diskstats)
  echo "diskio_r $(( (R2-R1)*512/1024 ))"
  echo "diskio_w $(( (W2-W1)*512/1024 ))"
  echo
  prof "root denetimleri (mailq, mysql, disk, smart, etkinlikler)"
  echo "--- Service ages ---"
  # Ana daemon'larin calisma suresi (etimes, sn). Coklu surecte en eskisi = daemon.
  # Dashboard <1 saatlik servisi "restarted X ago" notuyla gosterir (renk yok).
  # NOT: perl daemon'lari (lfd, cpsrvd) $0 uzerinden comm'unu degistirir
  # ("lfd - sleeping", "cpsrvd (SSL) - ..."), bu yuzden ps -C tam eslesmesi
  # onlari bulamaz — "isim" veya "isim + bosluk" on-ek eslesmesi kullanilir.
  ps_etimes_comm | awk '
    { e=$1+0; c=$2; for(i=3;i<=NF;i++) c=c" "$i
      n=split("mariadbd mysqld litespeed lshttpd httpd exim dovecot named pdns_server pure-ftpd proftpd cpsrvd cpsrvd-dormant lfd imunify360-agen imunify-residen redis-server memcached", L, " ")
      for(j=1;j<=n;j++){ p=L[j]; if(c==p || index(c, p " ")==1){ if(e>m[p]) m[p]=e } } }
    END{ for(p in m) print "svcage", p, m[p] }'
  echo
  prof "servis yaslari"
  echo "--- Versions ---"
  # Kart basliklarinin altinda gosterilen surumler — CSF mail ekinde
  # guncelleme-sonrasi teshis icin ("hangi surumdeyken bozuldu").
  # Format: "ver <anahtar> <Etiket> <surum>". Bulunamayan sessizce atlanir.
  # SAATLIK CACHE: surumler dakikada degismez; agir olan imunify360-agent
  # CLI'sini (~1-2 sn python) her dakika calistirmamak icin.
  VC=$DATA_DIR/.ver_cache
  if [ ! -s "$VC" ] || [ $(( $(date +%s) - $(stat -c %Y "$VC" 2>/dev/null || echo 0) )) -gt 3600 ]; then
    {
      V=$(/usr/local/lsws/bin/lshttpd -v 2>/dev/null | head -1 | awk -F/ '{print $2}' | awk '{print $1}'); [ -n "$V" ] && echo "ver web LiteSpeed $V"
      [ -z "$V" ] && { V=$(httpd -v 2>/dev/null | awk -F/ '/Server version/{print $2}' | awk '{print $1}'); [ -n "$V" ] && echo "ver web Apache $V"; }
      V=$(awk 'NR==1{print $1}' /usr/local/cpanel/version 2>/dev/null); [ -n "$V" ] && echo "ver cpanel cPanel $V"
      V=$(timeout 3 mysqladmin version 2>/dev/null | awk '/Server version/{print $3}' | sed 's/-MariaDB.*//'); [ -n "$V" ] && echo "ver db MariaDB $V"
      V=$(exim -bV 2>/dev/null | awk 'NR==1{print $3}'); [ -n "$V" ] && echo "ver exim Exim $V"
      V=$(dovecot --version 2>/dev/null | awk '{print $1}'); [ -n "$V" ] && echo "ver dovecot Dovecot $V"
      V=$(named -v 2>/dev/null | awk '{print $2}' | sed 's/-RedHat.*//'); [ -n "$V" ] && echo "ver named BIND $V"
      # LFD ayni csf paketinden gelir — ayni surumu tasir
      V=$(csf -v 2>/dev/null | awk 'NR==1{print $2}'); [ -n "$V" ] && { echo "ver csf CSF $V"; echo "ver lfd LFD $V"; }
      V=$(timeout 5 imunify360-agent version 2>/dev/null | head -1 | awk '{print $NF}'); [ -n "$V" ] && echo "ver imunify Imunify360 $V"
      V=$(cagefsctl --version 2>/dev/null | awk '{print $NF}' | sed -E 's/-[0-9]+\.el[0-9].*$//'); [ -n "$V" ] && echo "ver cagefs CageFS $V"
      V=$(rpm -q --qf '%{VERSION}' ea-apache24-mod_security2 2>/dev/null) && [ -n "$V" ] && echo "ver modsec ModSecurity $V"
      V=$(rpm -q --qf '%{VERSION}' pure-ftpd 2>/dev/null | grep -v 'not installed')
      [ -z "$V" ] && V=$(/usr/sbin/pure-ftpd --help 2>&1 | awk 'NR==1 && $2 ~ /^v?[0-9]/{sub(/^v/,"",$2); print $2}')
      [ -n "$V" ] && echo "ver ftp Pure-FTPd $V"
      V=$(redis-server --version 2>/dev/null | awk -F'v=' 'NF>1{print $2}' | awk '{print $1}'); [ -n "$V" ] && echo "ver redis Redis $V"
      V=$(memcached -h 2>/dev/null | awk 'NR==1{print $2}'); [ -n "$V" ] && echo "ver memcached Memcached $V"
    } > "$VC.tmp" && mv "$VC.tmp" "$VC"
  fi
  cat "$VC" 2>/dev/null
  # Kernel cache disinda: uname bedava ve reboot sonrasi aninda dogru olmali
  echo "ver kernel Linux $(uname -r)"
  echo
  prof "surumler"
  echo "--- Top disk accounts ---"
  # En cok disk kullanan 5 cPanel HESABI (sistem kullanicilari haric). Kaynak:
  # repquota CSV (kota dosyasini okur, filesystem gezmez → ucuz). SAATLIK cache
  # cunku disk kullanimi dakikada degismez. BlockUsed KB → GB.
  DAC=$DATA_DIR/.diskacct_cache
  if [ ! -s "$DAC" ] || [ $(( $(date +%s) - $(stat -c %Y "$DAC" 2>/dev/null || echo 0) )) -gt 3600 ]; then
    ls /var/cpanel/users/ 2>/dev/null > "$DAC.users"
    # TUM hesaplar once ara dosyaya: ayni gecisten hem ilk 15'lik cip listesi hem
    # de gunluk buyume kaydi cikiyor, repquota ikinci kez kosmuyor.
    repquota -a -O csv 2>/dev/null | awk -F, '
      NR==FNR{cp[$1]=1; next}
      FNR>1 && ($1 in cp) && $4+0>0 {printf "%d %s\n", $4, $1}
    ' "$DAC.users" - | sort -rn > "$DAC.all"
    head -15 "$DAC.all" | awk '{printf "diskacct %s %.1f\n", $2, $1/1048576}' > "$DAC.tmp" \
      && mv "$DAC.tmp" "$DAC"

    # --- Hesap basina buyume gecmisi (GUNDE bir satir) -----------------------
    # Bicim: "YYYY-MM-DD hesap:gb hesap:gb ..." — gunde TEK satir, cunku pano her
    # render'da yalnizca IKI satir okuyacak (en yeni + pencerenin basi); hesap
    # basina satir yazsak 371 hesap x 40 gun = 15 bin satir ayristirmak gerekirdi.
    # COZUNURLUK 0.01 GB (10 MB). Once 0.1 idi ve bir gunluk pencerede cogu hesabin
    # buyumesi o adimin altinda kaldigi icin liste 14 satir "+0.1" diye kilitleniyordu:
    # 50 MB ile 149 MB ayirt edilemiyordu, yani siralama siralama degildi. Ek maliyet
    # hesap basina gunde bir karakter.
    # ALT SINIR YOK, kucuk hesaplar da yazilir: 0.05 GB'den 30 GB'ye firlayan
    # hesap tam da yakalanmasi gereken sey, listede yoksa "yeni" sanilip elenirdi.
    # Kota kapali sunucuda repquota bos/sifir doner — o zaman HIC YAZILMAZ:
    # sahte sifirlarla "kimse buyumuyor" demektense veri yok demek dogru.
    DAH="$HOME_DIR/.diskacct_history"
    DAHTODAY=$(date +%F)
    if [ -s "$DAC.all" ] \
       && [ "$(tail -1 "$DAH" 2>/dev/null | awk '{print $1}')" != "$DAHTODAY" ]; then
      awk -v d="$DAHTODAY" '{printf "%s%s:%.3f", (NR==1?d FS:FS), $2, $1/1048576}
                            END{if (NR) print ""}' "$DAC.all" >> "$DAH"
      tail -40 "$DAH" > "$DAH.tmp" && mv "$DAH.tmp" "$DAH"   # 30 gunluk pencere + pay
      chown "$WEB_USER:$WEB_USER" "$DAH"; chmod 640 "$DAH"
    fi
    rm -f "$DAC.users" "$DAC.all"
  fi
  cat "$DAC" 2>/dev/null
  echo
  prof "disk hesaplari (kota)"
  echo "--- Top IO accounts ---"
  # Hesap basina DISK I/O (KB/s, okuma+yazma, son 1 dakikanin ortalamasi).
  # KAYNAK 1 — /proc/lve/list (CEKIRDEK ARAYUZU). Eskiden burada "lveinfo"
  # calisiyordu: lvestats VERITABANINI sorguluyor, uretimde 1205 ms suruyor ve
  # SON TAMAMLANAN dakikayi veriyordu. Yani hesap listesi ile surec listesi
  # komsu iki dakikayi anlatiyor, toplamlari tutmuyordu.
  #
  # /proc/lve/list ayni cekirdek sayaclarini dogrudan veriyor; fark iki tur
  # arasinda aliniyor (CPU'da /proc/stat icin yaptigimizin aynisi). Boylece
  # pencere TOPLAYICININ KENDI ARALIGI olur — surec listesiyle AYNI 60 saniye.
  #
  # BICIM: dosya SEKME ile ayrilmis ve bos alanlar var; bosluga gore ayirmak
  # sutunlari kaydirir. 25 sutun: 1=ID("0,<uid>") 16=IO 23=IOPS.
  # BIRIM: uretimde olculdu — IO sayaci KB. Iki hesapta lveinfo ile karsilastirildi
  # (136 KB/60 sn = 2,3 KB/s <-> lveinfo aIO 2; 104/60 = 1,7 <-> 1).
  IO_OUT=""
  if [ -r /proc/lve/list ]; then
    IO_OUT=$(python3 -I - "$DATA_DIR/.lve_state" /proc/lve/list <<'PYEOF'
import os, sys, time, pwd, re
state = sys.argv[1]; now = time.time()
cp = set(os.listdir('/var/cpanel/users')) if os.path.isdir('/var/cpanel/users') else None
ok = re.compile(r'^[a-z][a-z0-9_.-]{0,31}$')
cur = {}
# Veri dosyasi ARGUMAN olarak gelir: stdin'i python'un kendisi (program metni)
# kullaniyor, oraya ayrica veri beslenemez.
try:
    satirlar = open(sys.argv[2]).read().splitlines()
except Exception:
    sys.exit(0)
for ln in satirlar:
    f = ln.split('\t')
    if len(f) < 23 or ',' not in f[0]: continue          # baslik satiri ve bozuklar
    try:
        uid = int(f[0].split(',')[1]); io = int(f[15]); iops = int(f[22])
    except (ValueError, IndexError):
        continue
    cur[uid] = (io, iops)
prev = {}; pt = None
try:
    with open(state) as fh:
        for ln in fh:
            p = ln.split()
            if len(p) == 2 and p[0] == 't': pt = float(p[1])
            elif len(p) == 3: prev[int(p[0])] = (int(p[1]), int(p[2]))
except Exception:
    pass
try:
    with open(state + '.tmp', 'w') as fh:
        fh.write('t %f\n' % now)
        for u, (io, iops) in cur.items(): fh.write('%d %d %d\n' % (u, io, iops))
    os.chmod(state + '.tmp', 0o600); os.replace(state + '.tmp', state)
except Exception:
    pass
# Ilk tur / cok eski ornek: olcum YOK demektir, isaret de yazilmaz.
if pt is None or now - pt < 5 or now - pt > 600: sys.exit(0)
dt = now - pt
out = []
for uid, (io, iops) in cur.items():
    if uid not in prev: continue                 # ilk gorulen hesap
    pio, piops = prev[uid]
    d = io - pio
    if d < 0: continue                           # sayac sifirlanmis (LVE yeniden kuruldu)
    try: name = pwd.getpwuid(uid).pw_name
    except KeyError: continue
    if not ok.match(name) or (cp is not None and name not in cp): continue
    out.append((d / dt, name, max(0, iops - piops) / dt))
# Olcum yapildi isareti: satir cikmasa bile yazilir ("yapan yok" != "olculemedi").
print("io_src lve 1m")
out.sort(reverse=True)
for kb, name, iops in out[:15]:
    if kb <= 0: continue                         # sifir satiri yazilmaz
    print("ioacct %s %.1f %d" % (name, kb, round(iops)))
PYEOF
)
  fi
  if [ -z "$IO_OUT" ]; then
    IO_OUT=$(python3 -I - "$DATA_DIR/.io_state" <<'PYEOF'
import os, sys, time, pwd, re
state = sys.argv[1]; now = time.time()
cp = set(os.listdir('/var/cpanel/users')) if os.path.isdir('/var/cpanel/users') else set()
ok = re.compile(r'^[a-z][a-z0-9_.-]{0,31}$')
cur = {}
for pid in os.listdir('/proc'):
    if not pid.isdigit(): continue
    try:
        uid = None
        with open('/proc/%s/status' % pid) as f:
            for ln in f:
                if ln.startswith('Uid:'): uid = int(ln.split()[1]); break
        if uid is None or uid < 1000: continue
        rb = wb = 0
        with open('/proc/%s/io' % pid) as f:
            for ln in f:
                if ln.startswith('read_bytes:'): rb = int(ln.split()[1])
                elif ln.startswith('write_bytes:'): wb = int(ln.split()[1])
        cur[uid] = cur.get(uid, 0) + rb + wb
    except Exception:
        continue
prev = {}; pt = None
try:
    with open(state) as f:
        for ln in f:
            p = ln.split()
            if len(p) != 2: continue
            if p[0] == 't': pt = float(p[1])
            else: prev[int(p[0])] = int(p[1])
except Exception:
    pass
try:
    with open(state + '.tmp', 'w') as f:
        f.write('t %f\n' % now)
        for u, b in cur.items(): f.write('%d %d\n' % (u, b))
    os.chmod(state + '.tmp', 0o600); os.replace(state + '.tmp', state)
except Exception:
    pass
if pt is None or now - pt < 5 or now - pt > 600: sys.exit(0)   # ilk tur / cok eski ornek
dt = now - pt; out = []
for u, b in cur.items():
    if u not in prev: continue                 # ilk gorulen kullanici: omur boyu sayaci bu dakikaya yazma
    d = max(0, b - prev[u])
    try: name = pwd.getpwuid(u).pw_name
    except KeyError: continue
    if not ok.match(name) or (cp and name not in cp): continue
    if d > 0: out.append((d / dt / 1024.0, name))
# LVE dalindaki ile ayni kural: olcum yapildi isareti + sifir satiri yok.
# Pencere burada her zaman bir tur (yaklasik 1 dakika).
print("io_src proc 1m")
out.sort(reverse=True)
for kb, name in out[:15]: print("ioacct %s %.1f -" % (name, kb))
PYEOF
)
  fi
  [ -n "$IO_OUT" ] && printf '%s\n' "$IO_OUT"
  echo
  prof "hesap I/O (lve)"
  echo "--- Top IO processes ---"
  # SUREC basina disk I/O (KB/s). Kaynak /proc/<pid>/io: read_bytes+write_bytes
  # BLOK katmanindan okunur (sayfa onbelleginden degil), yani IO beklemeyi ureten
  # seyle ayni sey olculur. Fark iki olcum arasinda alinir.
  #
  # KAPSAM, hesap gorunumunden FARKLI ve ikisi birbirini tamamlar:
  #   - Hesap (LVE): cgroup duzeyinde sayar, tur arasinda olen kisa omurlu
  #     surecleri (istek basina lsphp) de kapsar; ama yalnizca cPanel hesaplari.
  #   - Surec (/proc): root dahil HER SEYI gorur; ama iki olcum arasinda dogup
  #     olen sureci goremez.
  # Bu yuzden iki listenin toplamlari birbirini TUTMAZ ve biri otekinin yerine
  # gecmez. Pano ikisini birlikte gosterir.
  #
  # PID YENIDEN KULLANIMI: biten bir surecin pid'i yenisine verilirse eski sayac
  # yeni surece yazilir ve ucuk bir hiz cikardi. Kimlik pid + surecin YASI ile
  # dogrulanir: yas gecen sureden kucukse o surec yeni dogmustur, atlanir.
  IOP_STATE="$DATA_DIR/.ioproc_state"
  # Ayni anlik goruntuden; python'un bekledigi "pid etimes user args" bicimine
  # cevriliyor (eskiden burada 14. bir "ps" taramasi vardi).
  awk '{a=$8; for(i=9;i<=NF;i++) a=a " " $i; print $1, $4, $3, substr(a,1,160)}' \
      "$PS_SNAP" > "$IOP_STATE.ps"
  IOP_OUT=$(python3 - "$IOP_STATE" <<'PYEOF'
import os, sys, time
state = sys.argv[1]; now = time.time()
cur = {}            # pid -> (etimes, bytes, user, komut)
try:
    with open(state + ".ps") as f:
        for ln in f:
            p = ln.split(None, 3)
            if len(p) < 4: continue
            try: pid = int(p[0]); et = int(p[1])
            except ValueError: continue
            rb = wb = 0
            try:
                with open("/proc/%d/io" % pid) as g:
                    for l2 in g:
                        if l2.startswith("read_bytes:"): rb = int(l2.split()[1])
                        elif l2.startswith("write_bytes:"): wb = int(l2.split()[1])
            except Exception:
                continue    # surec oldu ya da okunamadi
            cur[pid] = (et, rb + wb, p[2], p[3].strip())
except Exception:
    sys.exit(0)

prev = {}; pt = None
try:
    with open(state) as f:
        for ln in f:
            p = ln.split()
            if len(p) == 2 and p[0] == "t": pt = float(p[1])
            elif len(p) == 3: prev[int(p[0])] = (int(p[1]), int(p[2]))
except Exception:
    pass
try:
    with open(state + ".tmp", "w") as f:
        f.write("t %f\n" % now)
        for pid, (et, b, u, c) in cur.items(): f.write("%d %d %d\n" % (pid, et, b))
    os.chmod(state + ".tmp", 0o600); os.replace(state + ".tmp", state)
except Exception:
    pass
if pt is None or now - pt < 5 or now - pt > 600: sys.exit(0)   # ilk tur / cok eski ornek
# Olcum YAPILDI isareti (hesap tarafindaki io_src ile ayni mantik): tek satir
# cikmasa bile "I/O yapan surec yok" ile "henuz olculemedi" ayrilabilsin.
print("ioproc_ok 1m")
dt = now - pt
out = []
for pid, (et, b, u, c) in cur.items():
    if pid not in prev: continue               # ilk gorulen surec: omur boyu sayaci bu dakikaya yazma
    pet, pb = prev[pid]
    if et < pet or et < dt - 5: continue       # pid yeniden kullanilmis: bu BASKA bir surec
    d = b - pb
    if d <= 0: continue
    out.append((d / dt / 1024.0, u, c, pid))
out.sort(reverse=True)
# Komut tek satira sigsin; bosluk alan ayiraci oldugu icin ciktida bosluk kalamaz.
# Alanlar: ioproc PID KULLANICI KBPS KOMUT — PID, CPU/RAM kartlariyla ayni
# sutun dilini kurmak icin tasiniyor (surec orada da PID'iyle listeleniyor).
for kb, u, c, pid in out[:10]:
    c = "_".join(c.split())[:70]
    print("ioproc %d %s %.1f %s" % (pid, u, kb, c))
PYEOF
  )
  rm -f "$IOP_STATE.ps"
  [ -n "$IOP_OUT" ] && printf '%s\n' "$IOP_OUT"
  # Tarihce 15. kolonu icin: o dakikanin en cok I/O yapan hesabi "hesap:kbps".
  TOPIO=$(printf '%s\n' "$IO_OUT" | awk 'NR==1 && $1=="ioacct" && $3+0 > 0 {printf "%s:%d", $2, int($3+0.5)}')
  echo
  prof "surec I/O (/proc io)"
  echo "--- MySQL queries ---"
  timeout 3 mysql -N -B -e "SELECT id, user, IFNULL(db,'-'), time, IFNULL(state,'-'), REPLACE(REPLACE(REPLACE(LEFT(info,150),'\n',' '),'\r',' '),'\t',' ') FROM information_schema.PROCESSLIST WHERE command <> 'Sleep' AND info IS NOT NULL AND time >= 5 AND id <> CONNECTION_ID() ORDER BY time DESC LIMIT 10" 2>/dev/null || true
} > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
prof "mysql sorgulari + anlik goruntuyu yaz"
chown "$WEB_USER:$WEB_USER" "$OUT"
chmod 640 "$OUT"

# Kampanya durumu: yalnizca bu turda act_age'in canli saydigi anahtarlar yazilir,
# suresi dolanlar dosyadan dogal olarak dusmus olur. Root'a ozel (600) — web
# kullanicisinin okumasina gerek yok, yaslar zaten .proc_snapshot'ta.
printf '%s' "$ACT_NEXT" > "$ACT_STATE" 2>/dev/null && chmod 600 "$ACT_STATE" 2>/dev/null
# Iz dosyasi: son 300 satir kalsin (dakikada en fazla birkac satir yazilir).
if [ -f "$ACT_TRACE" ] && [ "$(wc -l < "$ACT_TRACE" 2>/dev/null || echo 0)" -gt 300 ]; then
  tail -300 "$ACT_TRACE" > "$ACT_TRACE.tmp" 2>/dev/null && mv "$ACT_TRACE.tmp" "$ACT_TRACE"
fi
chmod 600 "$ACT_TRACE" 2>/dev/null

# --- sparkline gecmisi (35 satir tampon) ---
# CPU/IOW yukaridaki 60 sn ortalamasindan gelir (eskiden burada ayri bir 3 sn
# ornek aliniyordu): grafik ile kart artik AYNI metrigi gosterir, ustelik cron
# calismasi 3 sn kisalir.
HIST="$HOME_DIR/.metrics_history"
read L1 L5 L15 _ < /proc/loadavg
# YUVARLA, kirpma: PHP tarafi round() kullaniyor (index.php, $memUsagePercent).
# Kirpinca kivilcim grafiginin son noktasi kartin buyuk rakamindan 1 eksik cikiyordu
# — ayni metrigi gosterdikleri halde farkli gorunuyorlardi.
# ISLEM SIRASI da PHP ile ayni: ((t-a)/t)*100. Kayan noktada (t-a)*100/t farkli
# sonuc verebiliyor — %56.5 sinirinda biri 57 digeri 56 yaziyordu.
RAM=$(awk '/^MemTotal/{t=$2} /^MemAvailable/{a=$2} END{printf "%d", int(((t-a)/t)*100 + 0.5)}' /proc/meminfo)
# df'in HAZIR Use% sutunu KULLANILMAZ: POSIX onu YUKARI yuvarlar (ceiling), PHP
# tarafi ise round() yapiyor — olculdu, xfs'te bile 1 puan ayrisiyordu (df 54,
# PHP 53.18). Kart ile grafik ayni metrigi gostersin diye yuzde burada da PHP'nin
# formuluyle hesaplanir: (toplam - kullanilabilir) / toplam, yarim yukari.
# df -P sutunlari: $2=1024-blok toplam, $3=kullanilan, $4=kullanilabilir.
DSK=$(df -P / | awk 'NR==2 && $2>0 {printf "%d", int((($2-$4)/$2)*100 + 0.5)}')
WRK=$PS_LT   # lsphp_total ile AYNI sayi; ikinci kez saymaya gerek yok
# Ag hizi (KB/s): yukaridaki 60 sn ortalamasinin arayuz toplami — eskiden burada
# ayri bir 1 sn ornek aliniyordu; grafik artik kartla ayni metrigi gosterir ve
# cron calismasi 1 sn daha kisalir.
# YUVARLA, kirpma: PHP tarafi (int)round($rxRate/1024) yapiyor — ayni veriden
# farkli sayi cikmasin diye burada da yarim yukari yuvarlanir.
read RXK TXK < <(awk '{r=0;t=0; n=split($0,f," "); for(i=1;i<=n;i++){split(f[i],p,":"); r+=p[2]; t+=p[3]} printf "%d %d", int(r/1024 + 0.5), int(t/1024 + 0.5)}' <<< "$NET_RATE")
RXK=${RXK:-0}; TXK=${TXK:-0}
MQ=$(exim -bpc 2>/dev/null || echo 0)
# 13. kolon: o dakikanin en cok CPU yiyen sureci ("comm:cpu"). Dashboard bunu
# yuk uyarilarina iliştirir ("High load ... — top: pigz 72%"); ayni satirda
# yazildigi icin metrikle zaman uyumu birebir. Bosluk/iki-nokta alt cizgiye cevrilir.
# TOPP: "ad:cpu:kullanici" — kullanici alani 1.4.1'de eklendi. cPanel'de bir
# lsphp surecinin kullanicisi ZATEN hesap adidir; "top: lsphp 76%" neredeyse
# bilgi vermezken "top: lsphp . enesoto 76%" dogrudan eyleme donusur. Eski
# satirlar iki alanli kalir, PHP tarafi ucuncuyu yoksa atlar.
TOPP=$(sort -k4,4 -rn "$PS_COMM" | head -1 | awk '{u=$2; n=$6; for(i=7;i<=NF;i++) n=n"_"$i; gsub(/:/,"_",n); gsub(/:/,"_",u); printf "%s:%d:%s", n, $4, u}')
# 14. kolon: en cok BELLEK (RSS) tutan surec "ad:rss_mb:kullanici". RAM uyarisinin
# faili top-CPU sureci degildir; sayfa acilisinda tarihceden uretilen RAM satiri
# bu sayede canli satirla ayni bilgiyi tasir ("— top: mariadbd · mysql 8.3 GB").
TOPR=$(sort -k5,5 -rn "$PS_COMM" | head -1 | awk '{u=$2; n=$6; for(i=7;i<=NF;i++) n=n"_"$i; gsub(/:/,"_",n); gsub(/:/,"_",u); printf "%s:%d:%s", n, int($5/1024), u}')
# 15. kolon: en cok I/O yapan HESAP "hesap:kbps" (Top IO accounts bolumunden).
# IO wait uyarisinin faili top-CPU sureci degil, en cok disk I/O yapan hesaptir.
echo "$(date +%H:%M) $L1 $L5 $L15 ${CPU:-0} $RAM $DSK ${IOW:-0} $WRK $RXK $TXK $MQ ${TOPP:--} ${TOPR:--} ${TOPIO:--}" >> "$HIST"
tail -35 "$HIST" > "$HIST.tmp" && mv "$HIST.tmp" "$HIST"
chown "$WEB_USER:$WEB_USER" "$HIST"; chmod 640 "$HIST"

# --- Disk buyume gecmisi (GUNDE bir satir: "YYYY-MM-DD kullanilan_gb") ---
# Kapasite planlamasi icin: dashboard ilk/son noktadan GB/hafta hesaplar ve
# %80'e kalan sureyi tahmin eder. Ayni gun tekrar yazilmaz; ~1 yil = 365 satir.
DHIST="$HOME_DIR/.disk_history"
DTODAY=$(date +%F)
if [ "$(tail -1 "$DHIST" 2>/dev/null | awk '{print $1}')" != "$DTODAY" ]; then
  # ONDALIKLI GB: tam sayi yazmak felaketti — 500+ GB'lik diskte gunluk buyume
  # ~0.1 GB, yani 1 GB'lik cozunurlugun ALTINDA kaliyor; egim hesabi tamamen
  # yuvarlama gurultusune donusuyordu (projeksiyon 4 ay <-> 70 ay ziplamasi).
  DUSED=$(df -P / | awk 'NR==2{printf "%.2f", $3/1048576}')  # kullanilan GB
  echo "$DTODAY $DUSED" >> "$DHIST"
  tail -400 "$DHIST" > "$DHIST.tmp" && mv "$DHIST.tmp" "$DHIST"
  chown "$WEB_USER:$WEB_USER" "$DHIST"; chmod 640 "$DHIST"
fi
# Profil modunda toplam: bolum sureleri ile uyumlu olsun diye en sonda.
if [ "${SSM_PROFILE:-0}" = "1" ]; then
  prof "tarihce satirlari"
  printf '%7d ms  TOPLAM (uyku haric)\n' "$(( $(date +%s%3N) - PROF_TB ))" >&2
fi
