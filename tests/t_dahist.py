"""Hesap basina gunluk disk kaydini KAYNAKTAN cikarip sinar.

Olculen: satir bicimi, ayni gun ikinci kez yazilmamasi, kota kapaliyken HIC
yazilmamasi (sahte sifir uretmemek), saklama penceresi.
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
NL = chr(10)
src = io.open(KOK + "src/collector.sh", encoding='utf-8', errors='replace').read()

bas = src.index('    DAH="$HOME_DIR/.diskacct_history"')
son = src.index(NL + "    fi", bas) + len(NL + "    fi")
blok = (src[bas:son]
        .replace('chown "$WEB_USER:$WEB_USER" "$DAH"; chmod 640 "$DAH"', ':')
        # Gunu test veriyor; blogun kendi 'date +%F' atamasi onu ezerdi.
        .replace('DAHTODAY=$(date +%F)', ':'))

betik = NL.join([
    "PASS=0; FAIL=0",
    'ck(){ if [ "$2" = "$3" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1));'
    ' echo "  BASARISIZ $1: beklenen=[$3] gelen=[$2]"; fi; }',
    'HOME_DIR=.; DAC=./t_dac',
    '# Sahte repquota ciktisi: "KB hesap", buyukten kucuge',
    'veri(){ printf "%s\\n" "$@" > "$DAC.all"; }',
    'bos(){ : > "$DAC.all"; }',
    'yaz(){ DAHTODAY="$1"' + NL + blok + NL + '}',
    'oku(){ cat ./.diskacct_history 2>/dev/null; }',
    'sil(){ rm -f ./.diskacct_history; }',
    "",
    'sil; veri "23698637 pergo" "13631488 ladoor" "104857 minik"',
    'yaz 2026-10-01',
    'ck "satir bicimi: gun + hesap:gb" "$(oku)" "2026-10-01 pergo:22.601 ladoor:13.000 minik:0.100"',
    "",
    'ck "ayni gun ikinci kez yazilmaz" "$(yaz 2026-10-01; oku)"'
    ' "2026-10-01 pergo:22.601 ladoor:13.000 minik:0.100"',
    "",
    'veri "26843545 pergo" "13631488 ladoor" "104857 minik"',
    'yaz 2026-10-02',
    'ck "ertesi gun yeni satir" "$(oku | tail -1)" "2026-10-02 pergo:25.600 ladoor:13.000 minik:0.100"',
    'ck "eski satir duruyor" "$(oku | wc -l)" "2"',
    "",
    '# Kota kapali: repquota bos doner -> HIC yazilmamali',
    'bos; yaz 2026-10-03',
    'ck "kota yoksa satir eklenmez" "$(oku | wc -l)" "2"',
    'ck "son satir bozulmadi" "$(oku | tail -1 | cut -d" " -f1)" "2026-10-02"',
    "",
    '# Tek hesap, ondalik yuvarlama',
    'sil; veri "1572864 tek"',
    'yaz 2026-10-05',
    'ck "tek hesap, 1.5 GB" "$(oku)" "2026-10-05 tek:1.500"',
    "",
    '# Saklama: 40 satirdan fazlasi dusurulur',
    'sil',
    'for i in $(seq 1 45); do veri "1048576 h$i"; yaz "2026-01-$i"; done',
    'ck "en fazla 40 gun saklanir" "$(oku | wc -l)" "40"',
    'ck "en eski satir dusmus" "$(oku | head -1 | cut -d" " -f1)" "2026-01-6"',
    "",
    'rm -f ./t_dac.all ./.diskacct_history',
    'echo; echo "GECEN: $PASS  KALAN: $FAIL"; [ $FAIL -eq 0 ]',
])
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "t_dahist.sh"), "w", encoding="utf-8", newline=NL).write(betik)
r = subprocess.run(["bash", "t_dahist.sh"], capture_output=True, text=True,
                   cwd=os.path.dirname(os.path.abspath(__file__)))
print(r.stdout or r.stderr)
sys.exit(r.returncode)
