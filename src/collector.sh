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
export PATH=/usr/local/cpanel/bin:/usr/local/cpanel/3rdparty/bin:/usr/sbin:/usr/bin:/sbin:/bin
sleep 20   # dodge the top-of-minute cron storm

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
  # Aktivite yaslari (dashboard cipleri): TUM surec listesinde en eski eslesen
  # surecin etimes'i — Top-15 CPU tablosundan hesaplamak yaniltiyordu (pkgacct
  # her hesapta yeniden dogar, "10 saatlik yedek" 1m gorunurdu). Koseli parantez
  # hilesi ([p]kgacct) awk'in kendi komut satirini eslemesini onler.
  # backup: gorev-omurlu surecler, dogrudan gozlem (esik gerekmez).
  A=$(ps axo etimes=,pcpu=,args= | awk '/[p]kgacct|[c]pbackup|cpanel\/[b]in\/backup/{if($1>m)m=$1} END{if(m)print m}'); [ -n "$A" ] && echo "act_backup $A"
  # update: cPanel upcp/updatenow + sistem paket guncellemeleri (dnf/yum) —
  # gece yuku faillerinden; backup gibi gorev-omurlu, esik gerekmez.
  A=$(ps axo etimes=,pcpu=,args= | awk '/[u]pcp|[u]pdatenow|[d]nf (upgrade|update)|[y]um (upgrade|update)/{if($1>m)m=$1} END{if(m)print m}'); [ -n "$A" ] && echo "act_update $A"
  # wpt: gorev kuyrugunu listeleyen belgelenmis CLI yok — CPU esikli (pcpu>=15)
  # surec sezgiseli kalir. Kalici sw-engine-fpm havuzu bosta %0'da gezdigi icin
  # esik onu eler; WPT gorevleri kisa omurlu oldugundan pcpu ortalamasi guvenilir.
  A=$(ps axo etimes=,pcpu=,args= | awk '$2>=15 && /[w]p-toolkit|[w]ordpress-toolkit/{if($1>m)m=$1} END{if(m)print m}'); [ -n "$A" ] && echo "act_wpt $A"
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
  A=$(cat "$IMC" 2>/dev/null)
  [ -n "$A" ] && { read IM_AGE IM_N IM_P <<< "$A"; echo "act_imunify $IM_AGE"; echo "act_imunify_n $IM_N"; echo "act_imunify_p $IM_P"; }
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

# --- sparkline gecmisi (3 sn pencere, dakika ortasi, 35 satir tampon) ---
HIST="$HOME_DIR/.metrics_history"
S1=($(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5, $6}' /proc/stat))
sleep 3
S2=($(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5, $6}' /proc/stat))
TD=$(( S2[0]-S1[0] )); IDL=$(( S2[1]-S1[1] )); WIO=$(( S2[2]-S1[2] ))
CPU=0; IOW=0
if [ "$TD" -gt 0 ]; then CPU=$(( 100*(TD-IDL)/TD )); IOW=$(( 100*WIO/TD )); fi
read L1 L5 L15 _ < /proc/loadavg
RAM=$(awk '/^MemTotal/{t=$2} /^MemAvailable/{a=$2} END{printf "%d",(t-a)*100/t}' /proc/meminfo)
DSK=$(df -P / | awk 'NR==2{gsub("%","",$5);print $5}')
WRK=$(ps -eo state,comm --no-headers | awk '$2=="lsphp" && ($1 ~ /^R/ || $1 ~ /^D/){c++} END{print c+0}')
# Ağ hızı: 1 sn arayla /proc/net/dev toplamı (lo hariç), KB/s
read RX1 TX1 < <(awk -F'[: ]+' '!/lo:/ && /:/{rx+=$3; tx+=$11} END{print rx, tx}' /proc/net/dev)
sleep 1
read RX2 TX2 < <(awk -F'[: ]+' '!/lo:/ && /:/{rx+=$3; tx+=$11} END{print rx, tx}' /proc/net/dev)
RXK=$(( (RX2 - RX1) / 1024 )); TXK=$(( (TX2 - TX1) / 1024 ))
MQ=$(exim -bpc 2>/dev/null || echo 0)
# 13. kolon: o dakikanin en cok CPU yiyen sureci ("comm:cpu"). Dashboard bunu
# yuk uyarilarina iliştirir ("High load ... — top: pigz 72%"); ayni satirda
# yazildigi icin metrikle zaman uyumu birebir. Bosluk/iki-nokta alt cizgiye cevrilir.
TOPP=$(ps axo pcpu,comm --sort=-pcpu --no-headers | head -1 | awk '{n=$2; for(i=3;i<=NF;i++) n=n"_"$i; gsub(/:/,"_",n); printf "%s:%d", n, $1}')
echo "$(date +%H:%M) $L1 $L5 $L15 $CPU $RAM $DSK $IOW $WRK $RXK $TXK $MQ ${TOPP:--}" >> "$HIST"
tail -35 "$HIST" > "$HIST.tmp" && mv "$HIST.tmp" "$HIST"
chown "$WEB_USER:$WEB_USER" "$HIST"; chmod 640 "$HIST"

# --- Disk buyume gecmisi (GUNDE bir satir: "YYYY-MM-DD kullanilan_gb") ---
# Kapasite planlamasi icin: dashboard ilk/son noktadan GB/hafta hesaplar ve
# %80'e kalan sureyi tahmin eder. Ayni gun tekrar yazilmaz; ~1 yil = 365 satir.
DHIST="$HOME_DIR/.disk_history"
DTODAY=$(date +%F)
if [ "$(tail -1 "$DHIST" 2>/dev/null | awk '{print $1}')" != "$DTODAY" ]; then
  DUSED=$(df -P / | awk 'NR==2{printf "%d", $3/1048576}')  # kullanilan GB
  echo "$DTODAY $DUSED" >> "$DHIST"
  tail -400 "$DHIST" > "$DHIST.tmp" && mv "$DHIST.tmp" "$DHIST"
  chown "$WEB_USER:$WEB_USER" "$DHIST"; chmod 640 "$DHIST"
fi