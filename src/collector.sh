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
if command -v flock >/dev/null 2>&1 && exec 9>"/var/run/ssm-collector-$WEB_USER.lock" 2>/dev/null; then
  flock -n 9 || exit 0
fi
export PATH=/usr/local/cpanel/bin:/usr/local/cpanel/3rdparty/bin:/usr/sbin:/usr/bin:/sbin:/bin
sleep 20   # dodge the top-of-minute cron storm

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
ACT_STATE="$DATA_DIR/.act_state"; ACT_GRACE=600
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
act_age() {   # $1=anahtar  $2=etimes (bos = surec gorunmuyor) -> $ACT_AGE / $ACT_END
  local k="$1" et="$2" pf pl age pe
  ACT_AGE=""; ACT_END=""
  read pf pl < <(awk -v k="$k" '$1==k{print $2, $3; exit}' "$ACT_STATE" 2>/dev/null)
  # Saglik kontrolu: bozuk/eski bicimli kayit (30 gunden yasli "baslangic") atilir.
  # Onceki surumun durum dosyasi 'anahtar ppid ilk son' bicimindeydi; alan kaymasi
  # PPID'yi baslangic epoch'u sanmaya ve 50+ yillik yas gostermeye yol acardi.
  case "$pf" in ''|*[!0-9]*) pf=""; pl="";; *) [ $(( ACT_NOW - pf )) -gt 2592000 ] && { pf=""; pl=""; };; esac

  if [ -n "$et" ]; then                                   # surec goruldu
    if [ -z "$pf" ] || [ $(( ACT_NOW - ${pl:-0} )) -gt "$ACT_GRACE" ]; then
      pf=$ACT_NOW                                         # yeni kampanya
    fi
    pl=$ACT_NOW
    ACT_NEXT="$ACT_NEXT$k $pf $pl"$'\n'
    age=$(( ACT_NOW - pf )); [ "$et" -gt "$age" ] && age=$et
    ACT_AGE=$age
    return 0                                              # aktif: eski bitis dusurulur
  fi

  if [ -n "$pf" ] && [ $(( ACT_NOW - ${pl:-0} )) -le "$ACT_GRACE" ]; then
    ACT_NEXT="$ACT_NEXT$k $pf $pl"$'\n'                   # pencere icinde: suruyor say
    ACT_AGE=$(( ACT_NOW - pf ))
    return 0
  fi

  # Kampanya bitti (ya da hic yoktu): bitis anini kaydet/tasi
  if [ -n "$pl" ]; then
    pe=$pl                                                # bu turda bitti
  else
    pe=$(awk -v k="END:$k" '$1==k{print $2; exit}' "$ACT_STATE" 2>/dev/null)
  fi
  case "$pe" in ''|*[!0-9]*) return 0;; esac
  [ $(( ACT_NOW - pe )) -gt "$ACT_RETAIN" ] && return 0   # saklama suresi doldu
  ACT_NEXT="$ACT_NEXT""END:$k $pe"$'\n'
  ACT_END=$pe
}
# Cikti yardimcisi: yas ve/veya bitis satirini yazar.
act_emit() {  # $1=anahtar  $2=etimes
  act_age "$1" "$2"
  [ -n "$ACT_AGE" ] && echo "$1 $ACT_AGE"
  [ -n "$ACT_END" ] && echo "${1}_end $ACT_END"
  return 0
}

OUT="$HOME_DIR/.proc_snapshot"
{
  echo "--- Top 15 by CPU ---"
  ps axo pid,user:19,pcpu,pmem,etime,args --sort=-pcpu | head -16 | cut -c1-280
  echo
  echo "--- Top 15 by RSS ---"
  ps axo pid,user:19,pcpu,pmem,rss,args --sort=-rss | head -16 | cut -c1-280
  echo
  echo "--- lsphp per user ---"
  ps axo user:19,comm --no-headers | awk '$2=="lsphp"{c[$1]++} END{for(u in c) printf "%d %s lsphp\n", c[u], u}' | sort -rn | head -15
  echo
  echo "--- Security checks ---"
  if [ -d /etc/csf ]; then
    [ -e /etc/csf/csf.disable ] && echo "csf disabled" || echo "csf enabled"
    T=$(awk -F'"' '/^TESTING /{print $2}' /etc/csf/csf.conf 2>/dev/null)
    [ -n "$T" ] && echo "csf_testing $T"
  fi
  M=$(awk '/^[[:space:]]*SecRuleEngine/{print $2; exit}' /etc/apache2/conf.d/modsec/modsec2.cpanel.conf 2>/dev/null)
  [ -n "$M" ] && echo "modsec $M"
  C=$(cagefsctl --cagefs-status 2>/dev/null | head -1)
  [ -n "$C" ] && echo "cagefs $C"
  echo
  echo "--- WHM services ---"
  whmapi1 servicestatus 2>/dev/null | awk '$1=="enabled:"{e=$2} $1=="installed:"{i=$2} $1=="name:"{n=$2} $1=="running:"{print "svc", n, e+0, i+0, $2+0}'
  echo
  echo "--- Root checks ---"
  echo "acct $(find /var/cpanel/users -maxdepth 1 -type f ! -name system 2>/dev/null | wc -l)"
  echo "mailq $(exim -bpc 2>/dev/null || echo -1)"
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
  echo "lsphp_total $(ps -eo state,comm --no-headers | awk '$2=="lsphp" && ($1 ~ /^R/ || $1 ~ /^D/){c++} END{print c+0}')"
  echo "lsphp_idle $(ps -eo state,comm --no-headers | awk '$2=="lsphp" && $1 ~ /^S/{c++} END{print c+0}')"
  # D-state: diskte bloklanan surec sayisi — "load yuksek ama CPU dusuk" teshisinin anahtari
  echo "dstate $(ps -eo state --no-headers | awk '$1 ~ /^D/{c++} END{print c+0}')"
  # rstate: kosan (R) surec sayisi. Load anatomisi: load ~ R + D (uninterruptible).
  # Root'tan alinir cunku CageFS surec sayimini cage'e sanallastirabilir.
  echo "rstate $(ps -eo state --no-headers | awk '$1 ~ /^R/{c++} END{print c+0}')"
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
  A=$(ps axo etimes=,pcpu=,args= | awk '/[p]kgacct|[c]pbackup|cpanel\/[b]in\/backup/{if($1>m)m=$1} END{if(m)print m}')
  act_emit act_backup "$A"
  # update: cPanel upcp/updatenow + sistem paket guncellemeleri (dnf/yum) —
  # gece yuku faillerinden; backup gibi gorev-omurlu, esik gerekmez.
  A=$(ps axo etimes=,pcpu=,args= | awk '/[u]pcp|[u]pdatenow|[d]nf (upgrade|update)|[y]um (upgrade|update)/{if($1>m)m=$1} END{if(m)print m}')
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
  A=$(ps axo etimes=,pcpu=,args= | awk '/[e]xecute-background-task/ || ($2>=15 && /[w]p-toolkit|[w]ordpress-toolkit/){if($1>m)m=$1} END{if(m)print m}')
  act_emit act_wpt "$A"
  # appdisc: cPanel wappspector (uygulama kesfi, WP Toolkit envanterini besler) —
  # hesap hesap kisa turlarla doner; WPT gibi CPU esikli (pcpu>=15) surec sezgiseli.
  A=$(ps axo etimes=,pcpu=,args= | awk '$2>=15 && /[w]appspector/{if($1>m)m=$1} END{if(m)print m}')
  act_emit act_appdisc "$A"
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
    timeout 10 imunify360-agent malware on-demand list --json 2>/dev/null | python3 -c '
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
except Exception:
    pass' > "$IMC.tmp" 2>/dev/null && mv "$IMC.tmp" "$IMC"
  fi
  # Yas ajanin kendi kaydindan gelir — TEK tarama icin kesin. Ama sweep hesap hesap
  # ayri kayitlar uretiyorsa her hesapta sifirlanir; act_age tabandan yukseltir.
  A=$(cat "$IMC" 2>/dev/null)
  IM_AGE=""; IM_N=""; IM_P=""
  [ -n "$A" ] && read IM_AGE IM_N IM_P <<< "$A"
  act_age act_imunify "$IM_AGE"; IM_AGE=$ACT_AGE
  [ -n "$IM_AGE" ] && { echo "act_imunify $IM_AGE"; echo "act_imunify_n $IM_N"; echo "act_imunify_p $IM_P"; }
  [ -n "$ACT_END" ] && echo "act_imunify_end $ACT_END"
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
  echo "--- Service ages ---"
  # Ana daemon'larin calisma suresi (etimes, sn). Coklu surecte en eskisi = daemon.
  # Dashboard <1 saatlik servisi "restarted X ago" notuyla gosterir (renk yok).
  # NOT: perl daemon'lari (lfd, cpsrvd) $0 uzerinden comm'unu degistirir
  # ("lfd - sleeping", "cpsrvd (SSL) - ..."), bu yuzden ps -C tam eslesmesi
  # onlari bulamaz — "isim" veya "isim + bosluk" on-ek eslesmesi kullanilir.
  ps axo etimes=,comm= | awk '
    { e=$1+0; c=$2; for(i=3;i<=NF;i++) c=c" "$i
      n=split("mariadbd mysqld litespeed lshttpd httpd exim dovecot named pdns_server pure-ftpd proftpd cpsrvd cpsrvd-dormant lfd imunify360-agen imunify-residen redis-server memcached", L, " ")
      for(j=1;j<=n;j++){ p=L[j]; if(c==p || index(c, p " ")==1){ if(e>m[p]) m[p]=e } } }
    END{ for(p in m) print "svcage", p, m[p] }'
  echo
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
  echo "--- Top disk accounts ---"
  # En cok disk kullanan 5 cPanel HESABI (sistem kullanicilari haric). Kaynak:
  # repquota CSV (kota dosyasini okur, filesystem gezmez → ucuz). SAATLIK cache
  # cunku disk kullanimi dakikada degismez. BlockUsed KB → GB.
  DAC=$DATA_DIR/.diskacct_cache
  if [ ! -s "$DAC" ] || [ $(( $(date +%s) - $(stat -c %Y "$DAC" 2>/dev/null || echo 0) )) -gt 3600 ]; then
    ls /var/cpanel/users/ 2>/dev/null > "$DAC.users"
    repquota -a -O csv 2>/dev/null | awk -F, '
      NR==FNR{cp[$1]=1; next}
      FNR>1 && ($1 in cp) && $4+0>0 {printf "%d %s\n", $4, $1}
    ' "$DAC.users" - | sort -rn | head -15 | awk '{printf "diskacct %s %.1f\n", $2, $1/1048576}' > "$DAC.tmp" && mv "$DAC.tmp" "$DAC"
    rm -f "$DAC.users"
  fi
  cat "$DAC" 2>/dev/null
  echo
  echo "--- MySQL queries ---"
  timeout 3 mysql -N -B -e "SELECT id, user, IFNULL(db,'-'), time, IFNULL(state,'-'), REPLACE(REPLACE(REPLACE(LEFT(info,150),'\n',' '),'\r',' '),'\t',' ') FROM information_schema.PROCESSLIST WHERE command <> 'Sleep' AND info IS NOT NULL AND time >= 5 AND id <> CONNECTION_ID() ORDER BY time DESC LIMIT 10" 2>/dev/null || true
} > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
chown "$WEB_USER:$WEB_USER" "$OUT"
chmod 640 "$OUT"

# Kampanya durumu: yalnizca bu turda act_age'in canli saydigi anahtarlar yazilir,
# suresi dolanlar dosyadan dogal olarak dusmus olur. Root'a ozel (600) — web
# kullanicisinin okumasina gerek yok, yaslar zaten .proc_snapshot'ta.
printf '%s' "$ACT_NEXT" > "$ACT_STATE" 2>/dev/null && chmod 600 "$ACT_STATE" 2>/dev/null

# --- sparkline gecmisi (35 satir tampon) ---
# CPU/IOW yukaridaki 60 sn ortalamasindan gelir (eskiden burada ayri bir 3 sn
# ornek aliniyordu): grafik ile kart artik AYNI metrigi gosterir, ustelik cron
# calismasi 3 sn kisalir.
HIST="$HOME_DIR/.metrics_history"
read L1 L5 L15 _ < /proc/loadavg
RAM=$(awk '/^MemTotal/{t=$2} /^MemAvailable/{a=$2} END{printf "%d",(t-a)*100/t}' /proc/meminfo)
DSK=$(df -P / | awk 'NR==2{gsub("%","",$5);print $5}')
WRK=$(ps -eo state,comm --no-headers | awk '$2=="lsphp" && ($1 ~ /^R/ || $1 ~ /^D/){c++} END{print c+0}')
# Ag hizi (KB/s): yukaridaki 60 sn ortalamasinin arayuz toplami — eskiden burada
# ayri bir 1 sn ornek aliniyordu; grafik artik kartla ayni metrigi gosterir ve
# cron calismasi 1 sn daha kisalir.
read RXK TXK < <(awk '{r=0;t=0; n=split($0,f," "); for(i=1;i<=n;i++){split(f[i],p,":"); r+=p[2]; t+=p[3]} printf "%d %d", r/1024, t/1024}' <<< "$NET_RATE")
RXK=${RXK:-0}; TXK=${TXK:-0}
MQ=$(exim -bpc 2>/dev/null || echo 0)
# 13. kolon: o dakikanin en cok CPU yiyen sureci ("comm:cpu"). Dashboard bunu
# yuk uyarilarina iliştirir ("High load ... — top: pigz 72%"); ayni satirda
# yazildigi icin metrikle zaman uyumu birebir. Bosluk/iki-nokta alt cizgiye cevrilir.
# TOPP: "ad:cpu:kullanici" — kullanici alani 1.4.1'de eklendi. cPanel'de bir
# lsphp surecinin kullanicisi ZATEN hesap adidir; "top: lsphp 76%" neredeyse
# bilgi vermezken "top: lsphp . enesoto 76%" dogrudan eyleme donusur. Eski
# satirlar iki alanli kalir, PHP tarafi ucuncuyu yoksa atlar.
TOPP=$(ps axo pcpu,user:32,comm --sort=-pcpu --no-headers | head -1 | awk '{u=$2; n=$3; for(i=4;i<=NF;i++) n=n"_"$i; gsub(/:/,"_",n); gsub(/:/,"_",u); printf "%s:%d:%s", n, $1, u}')
echo "$(date +%H:%M) $L1 $L5 $L15 ${CPU:-0} $RAM $DSK ${IOW:-0} $WRK $RXK $TXK $MQ ${TOPP:--}" >> "$HIST"
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