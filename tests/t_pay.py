"""Pay penceresi (grace) davranisi — KAYNAKTAN cikarilip olculur.

Gercek olay (2026-10-21, sunucuda olculdu): csf-autogroup cron'u */30, 'ps' hicbir
surec gostermiyor, buna ragmen rozet 5DK'dan 9DK'ya cikiyordu. Sebep: act_age
sureci gormese bile kampanyayi 600 sn boyunca 'suruyor' sayip yasi buyutuyordu.

Burada iki sey sinanir:
  1) Varsayilan pay (uzun isler): surec kaybolsa da pencere icinde rozet durur.
  2) Pay 0 (csf-autogroup): surec kaybolunca rozet ANINDA duser, yas da kampanyadan
     degil surecin kendi etimes'inden gelir.
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
    'ACT_STATE=./t_pay_st; ACT_GRACE=600; ACT_RETAIN=3600; ACT_NOW=1700000000',
    blok,
    '# tik <etimes> <pay>  -> "yas|bitis"',
    'tik(){ ACT_NEXT=""; act_age is "$1" "" "" $2',
    '  printf "%s" "$ACT_NEXT" > "$ACT_STATE"',
    '  echo "${ACT_AGE:--}|${ACT_END:--}"; }',
    'sifirla(){ : > "$ACT_STATE"; ACT_NOW=1700000000; }',
    "",
    '# ── Varsayilan pay: uzun is, bir tik kacsa da dusmez ──────',
    'sifirla',
    'ck "gorulen uzun is" "$(tik 300 600)" "300|-"',
    'ACT_NOW=$((ACT_NOW+60))',
    # ESKI BEKLENTI: pay icinde rozet yas gostermeye devam ederdi. O bir VARSAYIMDI
    # (surec goruilmuyordu) ve kaldirildi: rozet artik yalnizca kanitla cikar,
    # kampanya ise olay kaydinin kapanisini beklesin diye acik kalir.
    'ck "tik kacti: rozet YOK ama kampanya acik" "$(tik "" 600)" "-|-"',
    'ACT_NOW=$((ACT_NOW+600))',
    'ck "pay doldu: bitti" "$(tik "" 600)" "-|1700000000"',
    "",
    '# ── Pay 0: surec yoksa ANINDA duser ───────────────────────',
    'sifirla',
    'ck "kisa tur gorulur, yas = etimes" "$(tik 12 0)" "12|-"',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "surec gitti: ANINDA bitti" "$(tik "" 0)" "-|1700000000"',
    "",
    '# ── Pay 0: takili kalan tur gercek yasiyla gorunur ────────',
    'sifirla',
    'ck "1. tik: 60 sn" "$(tik 60 0)" "60|-"',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "2. tik: 120 sn (kampanya degil, etimes)" "$(tik 120 0)" "120|-"',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "3. tik: 180 sn" "$(tik 180 0)" "180|-"',
    "",
    '# ── Pay 0 ile yas SISIRILMEZ: surec yokken sayac buyumez ──',
    'sifirla',
    'tik 12 0 >/dev/null',
    'ACT_NOW=$((ACT_NOW+60));  A1=$(tik "" 0)',
    'ACT_NOW=$((ACT_NOW+240)); A2=$(tik "" 0)',
    'ck "4 dk sonra hala yas YOK (eski kusur)" "$(echo "$A1|$A2" | cut -d"|" -f1,3)" "-|-"',
    "",
    'rm -f ./t_pay_st',
    'echo; echo "GECEN: $PASS  KALAN: $FAIL"; [ $FAIL -eq 0 ]',
])
io.open(os.path.join(BURASI, "t_pay.sh"), "w", encoding="utf-8", newline=NL).write(betik)
r = subprocess.run(["bash", "t_pay.sh"], capture_output=True, text=True, cwd=BURASI)
print(r.stdout or r.stderr)
sys.exit(r.returncode)
