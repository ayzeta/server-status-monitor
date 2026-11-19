#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# tests/calistir.sh — butun testleri kosar, tek ozet basar.
#
#   bash tests/calistir.sh            hepsi
#   bash tests/calistir.sh lve io     adinda "lve" ya da "io" gecenler
#
# Testler URUN KODUNU KAYNAKTAN CIKARIP kosar (kopyasini degil): bir awk
# programi, gomulu python ya da JS govdesi degistiginde test onu goru"r.
# Bu yuzden "kodu da teste yazdik, tabii ki geciyor" tuzagi yok.
#
# Gereksinimler: bash, awk, python3. PHP ve node olmayan makinede onlara
# ihtiyac duyan testler ATLANIR (sessizce degil — ozette "atlandi" yazar).
# ════════════════════════════════════════════════════════════════════════
cd "$(dirname "$0")" || exit 2
KOK="$(cd .. && pwd)"

# Yorumlayicilar VARLIKLA degil CALISMAYLA secilir: Windows'ta "python3" adi
# Microsoft Store kisayoluna gidip hata basiyor, "command -v" ise onu bulunmus
# sayiyordu — butun python testleri bu yuzden hata veriyordu.
PY=""; for c in python3 python py; do
  command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -n "$PY" ] || { echo "python3 gerekli"; exit 2; }
HAS_PHP=0; command -v php  >/dev/null 2>&1 && HAS_PHP=1
HAS_NODE=0; command -v node >/dev/null 2>&1 && HAS_NODE=1

# PHP ve/veya node isteyen testler (gomulu ikizleri calistiriyorlar)
PHP_GEREK=" t_growikiz.py t_ioikiz.py t_lveikiz.py t_sslikiz.py t_bosdurum.py t_snapkoprusu.py t_sslonbellek.py t_olaysatiri.py "
NODE_GEREK=" t_growikiz.py t_ioikiz.py t_lveikiz.py t_sslikiz.py t_olaysatiri.py "
# Gercek Linux "ps" isteyenler. Git Bash'te /proc taklidi VAR ama ps Windows'un
# ps'i: "--sort" yok. O yuzden olcut dosya degil, procps'in kendisi.
LINUX_GEREK=" t_pscanli.sh t_updself.sh "
HAS_PROCPS=0
ps --version 2>&1 | grep -qi procps && HAS_PROCPS=1

# Gercek Linux yoksa ama WSL varsa, o testi WSL ICINDE kosariz: korumayi
# "bu makinede calismiyor" diye kaybetmeyelim. Dagitim adi SABIT DEGIL —
# varsayilan dagitim kullanilir, istenirse WSL_DISTRO ile secilir.
WSL_KOK=""
if [ "$HAS_PROCPS" = "0" ] && command -v wsl.exe >/dev/null 2>&1; then
  WSL_SEC=""; [ -n "${WSL_DISTRO:-}" ] && WSL_SEC="-d $WSL_DISTRO"
  # cygpath -w DEGIL -m: ters boluleri Git Bash yolda yutuyor ("D:Projelerdepo"
  # cikiyordu). Egik bolulu Windows yolunu wslpath sorunsuz ceviriyor.
  if command -v cygpath >/dev/null 2>&1; then
    WSL_KOK="$(wsl.exe $WSL_SEC wslpath -a "$(cygpath -m "$KOK")" 2>/dev/null | tr -d '\r')"
  else
    WSL_KOK="/mnt${KOK}"      # /d/depo -> /mnt/d/depo
  fi
  wsl.exe $WSL_SEC -e bash -lc "[ -r /proc/stat ] && [ -d '$WSL_KOK' ]" >/dev/null 2>&1 || WSL_KOK=""
fi

# ── Testlerin temp'i AYRI ──────────────────────────────────────────────
# Urun gecici dosyalarini sys_get_temp_dir()'e koyuyor (azTmp): yoklama
# onbellegi, donanim kusagi. Testler oraya yazarsa CANLI panonun onbellegine
# karisirlar — bu depo sunucuda da duruyor ve pano oradan kosuyor. Ayri dizin
# hem onu onler hem isitmayi (asagi) mumkun kilar.
# Windows PHP TMPDIR'i YOK SAYAR, TMP/TEMP'e bakar; Linux'ta tersi. Ucu de.
export TMPDIR="${TMPDIR_TEST:-${TMP:-/tmp}/az_test_tmp}"
mkdir -p "$TMPDIR" 2>/dev/null
export TMP="$TMPDIR" TEMP="$TMPDIR"

# ── Yoklama onbellegini isit ───────────────────────────────────────────
# Urun kapali her portu 1 sn zaman asimiyla yokluyor; gelistirme makinesinde
# hicbiri dinlemedigi icin tek render 16 saniyesini beklemekle geciriyordu
# (CPU suresi 0.015 sn). Urunun onbellegi var ama tam sayfa TTL'i 5 saniye,
# yani render bitmeden bayatliyordu. Bir kez isitip damgalari ileri aliriz;
# degerler gercek olcumdur, uydurma yok. Ayrintisi probe_isit.py'de.
if [ "$HAS_PHP" = "1" ] && ! ls "$TMPDIR"/az_probe_cache_*.json >/dev/null 2>&1; then
  printf '  %-20s %s' "(isitma)" "yoklama onbellegi dolduruluyor... "
  ( cd "$KOK" && php -r 'include "src/index.php";' ) >/dev/null 2>&1
  "$PY" probe_isit.py "$TMPDIR" | tail -1
fi

gecen=0; kalan=0; atlanan=0; bozuk=()

# Sure olcumu: EPOCHREALTIME mikrosaniye verir, ama ondalik ayraci YERELE bagli
# (tr_TR'de virgul). Ikisini de at, tamsayi mikrosaniye kalsin.
simdi_us(){ local e=${EPOCHREALTIME}; e=${e/,/}; e=${e/./}; printf '%s' "$e"; }
sure_yaz(){ # $1 = baslangic (mikrosaniye)
  local ms=$(( ($(simdi_us) - $1) / 1000 ))
  printf '%d.%01ds' $(( ms / 1000 )) $(( (ms % 1000) / 100 ))
}

kosu(){ # dosya
  local f="$1" ad="${1%.*}" cikti son durum t0
  t0=$(simdi_us)
  case " $f " in
    *" ${f} "*) ;;
  esac
  if [ "$HAS_PHP" = "0" ] && [[ "$PHP_GEREK" == *" $f "* ]]; then
    printf '  %-20s ATLANDI (php yok)\n' "$ad"; atlanan=$((atlanan+1)); return
  fi
  if [ "$HAS_NODE" = "0" ] && [[ "$NODE_GEREK" == *" $f "* ]]; then
    printf '  %-20s ATLANDI (node yok)\n' "$ad"; atlanan=$((atlanan+1)); return
  fi
  local wsl_ile=0
  if [[ "$LINUX_GEREK" == *" $f "* ]] && [ "$HAS_PROCPS" = "0" ]; then
    if [ -n "$WSL_KOK" ]; then
      wsl_ile=1
    else
      printf '  %-20s ATLANDI (Linux ps gerekiyor; WSL de yok)\n' "$ad"; atlanan=$((atlanan+1)); return
    fi
  fi
  if [ "$wsl_ile" = "1" ]; then
    cikti="$(wsl.exe $WSL_SEC -e bash -lc "cd '$WSL_KOK' && bash tests/$f" 2>&1)"
    durum=$?
    cikti="${cikti//$'\r'/}"
    son="$(printf '%s\n' "$cikti" | grep -E 'GECEN|KALAN' | tail -1)"
    if [ "$durum" -eq 0 ]; then
      gecen=$((gecen+1)); printf '  %-20s OK  %7s  %s   [WSL]\n' "$ad" "$(sure_yaz "$t0")" "$son"
    else
      kalan=$((kalan+1)); bozuk+=("$ad"); printf '  %-20s HATA %6s  %s   [WSL]\n' "$ad" "$(sure_yaz "$t0")" "$son"
      printf '%s\n' "$cikti" | tail -12 | sed 's/^/        /'
    fi
    return
  fi
  case "$f" in
    *.py) cikti="$("$PY" "$f" 2>&1)" ;;
    *.sh) cikti="$(bash "$f" 2>&1)" ;;
    *.js) if [ "$HAS_NODE" = "0" ]; then
            printf '  %-20s ATLANDI (node yok)\n' "$ad"; atlanan=$((atlanan+1)); return
          fi
          cikti="$(node "$f" 2>&1)" ;;
  esac
  durum=$?
  # Testler son satirda ozet basar: "GECEN: n KALAN: m" / "HATA: n" / "SIZINTI: n"
  son="$(printf '%s\n' "$cikti" | grep -E 'GECEN|KALAN|HATA|IHLAL|SIZINTI|AYRISMA|SORUN' | tail -1)"
  if [ "$durum" -eq 0 ]; then
    gecen=$((gecen+1)); printf '  %-20s OK  %7s  %s\n' "$ad" "$(sure_yaz "$t0")" "$son"
  else
    kalan=$((kalan+1)); bozuk+=("$ad"); printf '  %-20s HATA %6s  %s\n' "$ad" "$(sure_yaz "$t0")" "$son"
    printf '%s\n' "$cikti" | tail -12 | sed 's/^/        /'
  fi
}

echo "Server Status Monitor — testler ($KOK)"
echo
TOPLAM_T0=$(simdi_us)

for f in t_*.py t_*.sh t_*.js; do
  [ -e "$f" ] || continue
  # URETILEN kosum dosyasini test sanma: t_X.py calisirken t_X.sh / t_X.js
  # yaziyor (urun kodunu kaynaktan cikarip). Ayni govdeyi iki kez kosmayalim.
  case "$f" in
    *.sh|*.js) [ -e "${f%.*}.py" ] && continue ;;
  esac
  if [ $# -gt 0 ]; then
    es=0; for k in "$@"; do case "$f" in *"$k"*) es=1 ;; esac; done
    [ "$es" = "1" ] || continue
  fi
  kosu "$f"
done

echo
echo "GECEN: $gecen   HATA: $kalan   ATLANDI: $atlanan   SURE: $(sure_yaz "$TOPLAM_T0")"
[ "$kalan" -eq 0 ] || { echo "Bozuk: ${bozuk[*]}"; exit 1; }
