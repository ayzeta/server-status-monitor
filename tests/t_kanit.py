"""ROZET KANITA, OLAY KAYDI KAMPANYAYA — ikisinin ayrildigini olcer.

Kullanici kurali: "varsayimla gosteriyorsa hic gostermesin". Rozet yalnizca
surec o tikte goruldugunde cikmali; olay kaydinin kapanisi ise tek bir
"goremedim" tikinde yazilmamali (cok surecli iste cop cift uretirdi).

act_age KAYNAKTAN cikarilir, tik tik surulur.
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
BURASI = os.path.dirname(os.path.abspath(__file__))
src = io.open(KOK + "src/collector.sh", encoding='utf-8', errors='replace').read()

bas = src.index("act_age() {")
son = src.index(NL + "act_emit() {", bas)
blok = src[bas:son]

betik = NL.join([
    "PASS=0; FAIL=0",
    'ck(){ if [ "$2" = "$3" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1));'
    ' echo "  BASARISIZ $1: beklenen=[$3] gelen=[$2]"; fi; }',
    'ACT_STATE=./t_k_st; ACT_GRACE=120; ACT_RETAIN=3600; ACT_NOW=1700000000',
    blok,
    '# tik <etimes> -> "rozet|kampanya|bitis"',
    'tik(){ ACT_NEXT=""; act_age is "$1"',
    '  printf "%s" "$ACT_NEXT" > "$ACT_STATE"',
    '  echo "${ACT_AGE:--}|${ACT_LIVE:--}|${ACT_END:--}"; }',
    'sifirla(){ : > "$ACT_STATE"; ACT_NOW=1700000000; }',
    "",
    '# ── Surec goruluyor: rozet VAR ────────────────────────────',
    'sifirla',
    'ck "goruldu: rozet ve kampanya" "$(tik 45)" "45|1700000000|-"',
    "",
    '# ── Tek tik goremedik: ROZET SONER, kampanya durur ───────',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "goremedik: rozet YOK, kampanya acik" "$(tik "")" "-|1700000000|-"',
    "",
    '# ── Geri geldi: rozet yine kanitla, AYNI kampanya ────────',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "geri geldi: ayni kampanya" "$(tik 165)" "165|1700000000|-"',
    "",
    '# ── Art arda iki goremedik: kampanya kapanir ─────────────',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "1. yokluk: henuz bitmedi" "$(tik "")" "-|1700000000|-"',
    'ACT_NOW=$((ACT_NOW+70))',
    'ck "2. yokluk: BITTI yazilir" "$(tik "")" "-|-|1700000120"',
    "",
    '# ── Kor sonda (?): rozet YOK ama kampanya dusmez ─────────',
    'sifirla',
    'tik 30 >/dev/null',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "kor tik: rozet yok, kampanya acik" "$(tik "?")" "-|1700000000|-"',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "kor sonrasi goruldu" "$(tik 120)" "120|1700000000|-"',
    "",
    '# ── Hic kampanya yokken kor tik hicbir sey uretmez ───────',
    'sifirla',
    'ck "kampanyasiz kor tik" "$(tik "?")" "-|-|-"',
    "",
    'rm -f ./t_k_st',
    'echo; echo "GECEN: $PASS  KALAN: $FAIL"; [ $FAIL -eq 0 ]',
])
io.open(os.path.join(BURASI, "t_kanit.sh"), "w", encoding="utf-8", newline=NL).write(betik)
r = subprocess.run(["bash", "t_kanit.sh"], capture_output=True, text=True, cwd=BURASI)
print(r.stdout or r.stderr)
sys.exit(r.returncode)
