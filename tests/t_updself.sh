#!/usr/bin/env bash
# update.sh KENDINI degistirirken geri kalani kosuyor mu? (2026-11-19)
#
# NEDEN: betik "git merge --ff-only" ile kendi dosyasini diskte yeniden yaziyor.
# Bash betigi bayt konumuna gore okudugu icin dosya kisalirsa kalan satirlar HIC
# kosmuyor ve cikis kodu 0 kaliyor (bash 5.1.8'de olculdu). O zaman merge'den
# sonraki "bash install.sh --yes" sessizce atlanir: git "guncelim" der, panonun
# dosyalari eski kalir, hata da verilmez.
#
# NASIL OLCULUYOR: URUNUN KENDI update.sh'i kosturuluyor. Disaridan bagimli
# oldugu uc sey PATH'te/dizinde taklit ediliyor -- "git" (fetch/merge),
# "id" (root kontrolu) ve "install.sh" (kurulum adimi). Sahte git, "merge"
# cagrildiginda update.sh'i KISA bir surumle degistiriyor: gercek merge'un
# yaptigi sey tam olarak bu. Sonra tek soru kaliyor: install.sh kostu mu?
#
# Vakum degil: ayni deney, korumasi SOKULMUS bir kopyayla da kosuluyor. Koruma
# calismiyorsa o kopya da gecerdi ve test hicbir sey olcmuyor olurdu.
set -u
KOK="$(cd "$(dirname "$0")/.." && pwd)"
gecen=0; kalan=0
ck(){ if [ "$2" = "$3" ]; then gecen=$((gecen+1)); printf '  %-46s -> tamam (%s)\n' "$1" "$2"
      else kalan=$((kalan+1)); printf '  BASARISIZ %-36s beklenen=%s gelen=%s\n' "$1" "$3" "$2"; fi; }

kur(){ # $1 = calisma dizini, $2 = kosulacak update.sh
  D="$1"
  rm -rf "$D"; mkdir -p "$D/bin" "$D/depo/.git"
  cp "$2" "$D/depo/update.sh"

  # install.sh: kostugunu KANIT dosyasiyla bildirir.
  printf '%s\n' '#!/usr/bin/env bash' 'echo kostu > "$(dirname "$0")/../kanit"' \
    > "$D/depo/install.sh"

  # Kisa surum: gercek merge'un yerine konan dosya. Asil update.sh'ten cok daha
  # kisa olmasi onemli -- olculen kusur tam da kisalma durumunda cikiyor.
  printf '%s\n' '#!/usr/bin/env bash' 'echo "kisa surum"' > "$D/kisa.sh"

  # Sahte git: update.sh'in sordugu her seye cevap verir, "merge" deyince
  # betigi KISA surumle degistirir.
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'case "$*" in'
    printf '%s\n' '  *"rev-parse --abbrev-ref"*) echo main ;;'
    printf '%s\n' '  *"rev-parse --short origin"*) echo bbbbbbb ;;'
    printf '%s\n' '  *"rev-parse --short"*) echo aaaaaaa ;;'
    printf '%s\n' '  *"merge-base"*) echo AAAA ;;'
    printf '%s\n' '  *"rev-parse origin"*) echo BBBB ;;'
    printf '%s\n' '  *"rev-parse @"*) echo AAAA ;;'
    printf '%s\n' '  *"rev-list --count"*) echo 1 ;;'
    printf '%s\n' '  *fetch*) : ;;'
    printf '%s\n' '  *log*) : ;;'
    printf '%s\n' "  *merge*) cp \"$D/kisa.sh\" \"$D/depo/update.sh\" ;;"
    printf '%s\n' '  *) : ;;'
    printf '%s\n' 'esac'
    printf '%s\n' 'exit 0'
  } > "$D/bin/git"

  # Sahte id: betik root ister; testi root olmadan kosabilmek icin.
  printf '%s\n' '#!/usr/bin/env bash' 'echo 0' > "$D/bin/id"
  chmod +x "$D/bin/git" "$D/bin/id" "$D/depo/install.sh" "$D/depo/update.sh"
}

kosu(){ # $1 = calisma dizini  -> "cikis_kodu kanit"
  ( cd "$1/depo" && PATH="$1/bin:$PATH" bash ./update.sh >/dev/null 2>&1 )
  printf '%s %s' "$?" "$([ -f "$1/kanit" ] && echo var || echo yok)"
}

T="${TMPDIR:-/tmp}/az_updself"

# ── 1) URUN: koruma yerinde ─────────────────────────────────────
kur "$T/urun" "$KOK/update.sh"
ck "merge dosyayi kisaltsa da kurulum kosuyor" "$(kosu "$T/urun")" "0 var"

# ── 2) KONTROL: koruma sokulmus kopya ───────────────────────────
# Kendini kopyalayan blok cikarilinca ayni deney BASARISIZ olmali. Olmazsa
# yukaridaki iddia bir sey olcmuyor demektir.
mkdir -p "$T"
awk '/^# .. ONCE KENDINI/{atla=1} /^cd "\$\{SSM_UPD_KOK/{atla=0; print "cd \"$(cd \"$(dirname \"$0\")\" && pwd)\""; next} !atla' \
  "$KOK/update.sh" > "$T/korumasiz.sh"
# Sokumun gercekten oldugunu dogrula (awk kaliba tutmadiysa test yanilir).
ck "kontrol kopyasinda koruma yok" \
   "$(grep -c 'SSM_UPD_KOPYA' "$T/korumasiz.sh")" "0"
kur "$T/kontrol" "$T/korumasiz.sh"
SONUC="$(kosu "$T/kontrol")"
printf '  bilgi: korumasiz kopyanin sonucu = %s\n' "$SONUC"
ck "korumasiz kopya kurulumu ATLIYOR (kusur gercek)" \
   "$([ "$SONUC" = "0 var" ] && echo hayir || echo evet)" "evet"

rm -rf "$T"
echo
echo "GECEN: $gecen  KALAN: $kalan"
[ "$kalan" -eq 0 ]
