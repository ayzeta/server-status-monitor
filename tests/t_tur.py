"""Is turunun bitise tasinmasini KAYNAKTAN cikarip sinar.

Kullanicinin gordugu kusur: "Ayzeta Backup basladi · geri yukleme · abdesthane"
ile baslayan is "Ayzeta Backup bitti · abdesthane" ile bitiyordu — tur dusuyordu.
Kapsam ('ps') icin kurulu mekanizmanin tur ('pk') ikizi burada olculuyor.
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
    'ACT_STATE=./t_st; ACT_GRACE=600; ACT_RETAIN=3600; ACT_NOW=1700000000',
    blok,
    '# Tik: yas, kapsam, tur ver -> yayin + durumu dosyaya tasi',
    'tik(){ ACT_NEXT=""; act_age is "$1" "$2" "$3"',
    '  printf "%s" "$ACT_NEXT" > "$ACT_STATE"',
    '  echo "${ACT_AGE:--}|${ACT_END:--}|${ACT_END_P:--}|${ACT_END_K:--}"; }',
    'sifirla(){ : > "$ACT_STATE"; ACT_NOW=1700000000; }',
    "",
    '# ── Tur kampanya boyunca ayni: bitise tasinir ──────────────',
    'sifirla',
    'ck "1. tik: suruyor" "$(tik 60 abdesthane geri_yukleme)" "60|-|-|-"',
    'ACT_NOW=$((ACT_NOW+60))',
    'ck "2. tik: hala suruyor" "$(tik 120 abdesthane geri_yukleme)" "120|-|-|-"',
    'ACT_NOW=$((ACT_NOW+700))   # pay penceresi asildi, kampanya kapanir',
    'ck "bitis: KAPSAM ve TUR birlikte" "$(tik "" "" "")"'
    ' "-|1700000060|abdesthane|geri_yukleme"',
    "",
    '# ── Tur degistiyse yazilmaz (yanlis tur yazmaktansa hic) ───',
    'sifirla',
    'tik 60 hesap1 geri_yukleme >/dev/null',
    'ACT_NOW=$((ACT_NOW+60))',
    'tik 120 hesap1 yedekleme >/dev/null',
    'ACT_NOW=$((ACT_NOW+700))',
    'ck "tur degisti -> bos, kapsam durur" "$(tik "" "" "")" "-|1700000060|hesap1|-"',
    "",
    '# ── Kapsam degisse de tur durur (ikisi bagimsiz) ───────────',
    'sifirla',
    'tik 60 hesap1 yedekleme >/dev/null',
    'ACT_NOW=$((ACT_NOW+60))',
    'tik 120 hesap2 yedekleme >/dev/null',
    'ACT_NOW=$((ACT_NOW+700))',
    'ck "kapsam * olur, tur korunur" "$(tik "" "" "")" "-|1700000060|*|yedekleme"',
    "",
    '# ── Yeni kampanya eskinin turunu DEVRALMAZ ─────────────────',
    'sifirla',
    'tik 60 hesap1 geri_yukleme >/dev/null',
    'ACT_NOW=$((ACT_NOW+700))',
    'tik "" "" "" >/dev/null                    # kampanya kapandi',
    'ACT_NOW=$((ACT_NOW+60))',
    'tik 30 hesap9 "" >/dev/null                # YENI kampanya, tur verilmedi',
    'ACT_NOW=$((ACT_NOW+700))',
    'ck "yeni kampanyada eski tur yok" "$(tik "" "" "")" "-|1700000760|hesap9|-"',
    "",
    '# ── Turu hic olmayan etkinlik bozulmaz ─────────────────────',
    'sifirla',
    'tik 60 hesap1 "" >/dev/null',
    'ACT_NOW=$((ACT_NOW+700))',
    # Burada TEK tik atildi, yani son dogrulanmis an baslangic ani; ustteki
    # senaryolarda iki tik oldugu icin +60. (Testin ilk surumu bunu kaciriyordu.)
    'ck "tursuz etkinlik: yalniz kapsam" "$(tik "" "" "")" "-|1700000000|hesap1|-"',
    "",
    'rm -f ./t_st',
    'echo; echo "GECEN: $PASS  KALAN: $FAIL"; [ $FAIL -eq 0 ]',
])
io.open(os.path.join(BURASI, "t_tur.sh"), "w", encoding="utf-8", newline=NL).write(betik)
r = subprocess.run(["bash", "t_tur.sh"], capture_output=True, text=True, cwd=BURASI)
print(r.stdout or r.stderr)
sys.exit(r.returncode)
