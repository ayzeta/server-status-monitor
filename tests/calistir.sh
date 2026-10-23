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
PHP_GEREK=" t_growikiz.py t_ioikiz.py t_sslikiz.py t_bosdurum.py t_snapkoprusu.py "
NODE_GEREK=" t_growikiz.py t_ioikiz.py t_sslikiz.py "
# Gercek Linux "ps" isteyenler. Git Bash'te /proc taklidi VAR ama ps Windows'un
# ps'i: "--sort" yok. O yuzden olcut dosya degil, procps'in kendisi.
LINUX_GEREK=" t_pscanli.sh "
HAS_PROCPS=0
ps --version 2>&1 | grep -qi procps && HAS_PROCPS=1

gecen=0; kalan=0; atlanan=0; bozuk=()

kosu(){ # dosya
  local f="$1" ad="${1%.*}" cikti son durum
  case " $f " in
    *" ${f} "*) ;;
  esac
  if [ "$HAS_PHP" = "0" ] && [[ "$PHP_GEREK" == *" $f "* ]]; then
    printf '  %-20s ATLANDI (php yok)\n' "$ad"; atlanan=$((atlanan+1)); return
  fi
  if [ "$HAS_NODE" = "0" ] && [[ "$NODE_GEREK" == *" $f "* ]]; then
    printf '  %-20s ATLANDI (node yok)\n' "$ad"; atlanan=$((atlanan+1)); return
  fi
  if [[ "$LINUX_GEREK" == *" $f "* ]] && [ "$HAS_PROCPS" = "0" ]; then
    printf '  %-20s ATLANDI (Linux ps/procps gerekiyor)\n' "$ad"; atlanan=$((atlanan+1)); return
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
    gecen=$((gecen+1)); printf '  %-20s OK    %s\n' "$ad" "$son"
  else
    kalan=$((kalan+1)); bozuk+=("$ad"); printf '  %-20s HATA  %s\n' "$ad" "$son"
    printf '%s\n' "$cikti" | tail -12 | sed 's/^/        /'
  fi
}

echo "Server Status Monitor — testler ($KOK)"
echo

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
echo "GECEN: $gecen   HATA: $kalan   ATLANDI: $atlanan"
[ "$kalan" -eq 0 ] || { echo "Bozuk: ${bozuk[*]}"; exit 1; }
