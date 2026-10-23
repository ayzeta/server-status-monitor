"""CSF durum makinesini KAYNAKTAN cikarip sinar.

Sinanan: karar SIRASI (ilk tutan kazanir), yetki hatasi ile "zincir yok" ayrimi,
ve kotu haberin ART ARDA IKI olcum kurali (csf -r sirasinda zincir kisa sure yok).

Iki harness kusuru dusurulmustu, ikisi de testteydi:
 1) Dosya varligi/izni ($T_BIN -x, command -v csf) degiskene cevrildi: Git Bash'te
    'touch + chmod +x' sonrasi '-x' Linux'takiyle ayni davranmiyordu.
 2) Durum dosyasini silip hemen geri okumak Windows'ta yarisiyordu; her senaryo
    artik YENI bir DATA_DIR aliyor. Tazeleme ust kabukta ('yeni'), cunku $(...)
    alt kabuk — orada atanan dizin sonraki olcume tasinmaz.
iptables gercek bir sahte komut (PATH'te): cikis kodu ve stderr metni sinananin ta kendisi.
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

bas = src.index("  if [ -d /etc/csf ] || command -v csf")
son = src.index(NL + "  fi", src.index('echo "csf_testing $T"', bas)) + len(NL + "  fi")
blok = (src[bas:son]
        .replace('[ -d /etc/csf ] || command -v csf >/dev/null 2>&1', '[ "$T_PRESENT" = 1 ]')
        .replace('[ ! -x /usr/sbin/csf ] && ! command -v csf >/dev/null 2>&1',
                 '[ "$T_HAS_BIN" != 1 ]')
        .replace('[ -e /etc/csf/csf.disable ]', '[ "$T_DISABLE" = 1 ]')
        .replace("/etc/csf/csf.conf", '"$T_CONF"')
        # iptables da PATH'ten degil degiskenden cagrilir: python alt surec olarak
        # bash baslatinca $(pwd) Windows bicimli donuyor, PATH'e eklenen dizin
        # parcalaniyor ve 'command -v iptables' hep basarisiz oluyordu.
        .replace('command -v iptables-legacy >/dev/null 2>&1'
                 ' && iptables-legacy -S LOCALINPUT >/dev/null 2>&1',
                 '[ "$T_HAS_LEGACY" = 1 ] && $T_IPT -S LOCALINPUT >/dev/null 2>&1')
        .replace('! command -v iptables >/dev/null 2>&1', '[ "$T_HAS_IPT" != 1 ]')
        .replace('elif iptables -S LOCALINPUT >/dev/null 2>&1; then',
                 'elif $T_IPT -S LOCALINPUT >/dev/null 2>&1; then')
        .replace('CSF_ERR=$(iptables -S LOCALINPUT 2>&1 >/dev/null)',
                 'CSF_ERR=$($T_IPT -S LOCALINPUT 2>&1 >/dev/null)'))

for gerekli in ('$T_PRESENT', '$T_HAS_BIN', '$T_DISABLE', '$T_CONF',
                '$T_HAS_IPT', '$T_HAS_LEGACY', '$T_IPT'):
    if gerekli not in blok:
        sys.exit("degistirme tutmadi: %s" % gerekli)

betik = NL.join([
    "PASS=0; FAIL=0",
    'ck(){ if [ "$2" = "$3" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1));'
    ' echo "  BASARISIZ $1: beklenen=[$3] gelen=[$2]"; fi; }',
    'T_CONF=$(mktemp)',
    'T_IPT="bash ./fake_iptables.sh"; export IPT_MODE',
    '# Varsayilan saglikli dunya; her senaryo gerekeni degistirir.',
    'T_PRESENT=1; T_HAS_BIN=1; T_DISABLE=0; T_HAS_IPT=1; T_HAS_LEGACY=0; IPT_MODE=ok',
    'printf "%s\\n" \'TESTING = "0"\' > "$T_CONF"',
    "",
    'kos(){ ' + blok + NL + '}',
    'yeni(){ DATA_DIR=$(mktemp -d); }        # temiz gecmis: yeni kampanya',
    'olc(){ kos | awk \'/^csf /{print $2}\'; }',
    "",
    '# ── Saglikli durum ──────────────────────────────────────────',
    'yeni; ck "hepsi yolunda -> ok" "$(olc)" "ok"',
    "",
    '# ── Sira: ilk tutan kazanir ─────────────────────────────────',
    'T_HAS_BIN=0',
    'yeni; ck "ikili yok: ilk olcumde BEKLETILIR" "$(olc)" "unknown"',
    'ck "art arda ikinci olcumde missing" "$(olc)" "missing"',
    'T_HAS_BIN=1',
    "",
    'T_DISABLE=1',
    'yeni; ck "csf.disable -> off, ANINDA" "$(olc)" "off"',
    'IPT_MODE=norule',
    'yeni; ck "off, kural yoklugundan ONCE gelir" "$(olc)" "off"',
    'T_DISABLE=0; IPT_MODE=ok',
    "",
    'printf "%s\\n" \'TESTING = "1"\' > "$T_CONF"',
    'yeni; ck "TESTING=1 -> testing, ANINDA" "$(olc)" "testing"',
    'yeni; ck "testing, kurallar YUKLU olsa da kazanir" "$(olc)" "testing"',
    'IPT_MODE=norule',
    'yeni; ck "testing, kural yoklugundan da ONCE" "$(olc)" "testing"',
    'printf "%s\\n" \'TESTING = "0"\' > "$T_CONF"; IPT_MODE=ok',
    "",
    '# ── Kural kontrolu ve yetki ayrimi ──────────────────────────',
    'IPT_MODE=norule',
    'yeni; ck "zincir yok: ilk olcumde BEKLETILIR" "$(olc)" "unknown"',
    'ck "art arda ikinci olcumde norules" "$(olc)" "norules"',
    "",
    'IPT_MODE=perm',
    'yeni; ck "yetki hatasi -> unknown (norules DEGIL)" "$(olc)" "unknown"',
    'ck "yetki hatasi tekrarinda da unknown" "$(olc)" "unknown"',
    "",
    '# ── Gecici pencere: csf -r sirasinda zincir yok, sonra geri gelir ──',
    'IPT_MODE=ok',
    'yeni; ck "once saglikli" "$(olc)" "ok"',
    'IPT_MODE=norule',
    'ck "TEK turluk kayip SAHTE ALARM URETMEZ" "$(olc)" "ok"',
    'IPT_MODE=ok',
    'ck "zincir geri geldi, ok kalir" "$(olc)" "ok"',
    'IPT_MODE=norule',
    'ck "gercek kayip: birinci tur beklet" "$(olc)" "ok"',
    'ck "gercek kayip: ikinci tur yayinla" "$(olc)" "norules"',
    'IPT_MODE=ok',
    'ck "duzelince aninda ok" "$(olc)" "ok"',
    "",
    '# ── iptables hic yoksa: dogrulanamadi (norules DEGIL) ──────',
    'T_HAS_IPT=0; IPT_MODE=ok',
    'yeni; ck "iptables yok -> unknown" "$(olc)" "unknown"',
    'ck "tekrarinda da unknown (beklemez)" "$(olc)" "unknown"',
    'T_HAS_IPT=1',
    "",
    '# ── Legacy yedegi: nft zinciri yok ama legacy var ───────────',
    'T_HAS_LEGACY=1; IPT_MODE=norule',
    'yeni; ck "legacy denemesi de basarisizsa beklet" "$(olc)" "unknown"',
    'T_HAS_LEGACY=0',
    "",
    '# ── CSF hic yoksa satir HIC yazilmaz (pano komut ipucuna duser) ──',
    'T_PRESENT=0',
    'yeni; ck "CSF yok -> csf satiri yok" "$(olc)" ""',
    "",
    'rm -rf ./t_path "$T_CONF"',
    'echo; echo "GECEN: $PASS  KALAN: $FAIL"; [ $FAIL -eq 0 ]',
])
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "t_csf.sh"), "w", encoding="utf-8", newline=NL).write(betik)
r = subprocess.run(["bash", "t_csf.sh"], capture_output=True, text=True,
                   cwd=os.path.dirname(os.path.abspath(__file__)))
print(r.stdout or r.stderr)
sys.exit(r.returncode)
