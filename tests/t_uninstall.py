"""uninstall.sh'i SAHTE bir kurulum uzerinde calistirip ne silip ne biraktigini olcer.

En kritik nokta: .htaccess'te cPanel'in kendi PHP blogu SAG KALMALI. Dosyayi
butunuyle silmek hesabin PHP surumunu degistirir — eski bir kusurdu, tekrar
etmesin diye burada olculuyor.
"""
import io
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
BURASI = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)

TMP = os.path.join(BURASI, "t_uninst").replace("\\", "/")
shutil.rmtree(TMP, ignore_errors=True)
DEPO = TMP + "/depo"
DATA = TMP + "/veri"
HOME = TMP + "/home/ayzeta"
WEB = HOME + "/public_html/status"
for d in (DEPO, DATA, WEB, TMP + "/bin"):
    os.makedirs(d, exist_ok=True)

# Root denetimi testte devre disi: Git Bash'te 'id -u' sifir degil ve bu test
# kaldirma MANTIGINI olcuyor, yetki kapisini degil. Kapinin VARLIGI ayrica
# dogrulanir (asagida), yoksa sessizce kaybolabilirdi.
ham = io.open(KOK + "uninstall.sh", encoding="utf-8").read()
ROOT_SATIRI = '[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root'
if ROOT_SATIRI not in ham:
    sys.exit("uninstall.sh'te root denetimi YOK")
io.open(DEPO + "/uninstall.sh", "w", encoding="utf-8", newline=NL).write(
    NL.join(":" if ROOT_SATIRI in s else s for s in ham.split(NL)))
io.open(DEPO + "/.install.conf", "w", newline=NL).write(
    'WEB_USER="ayzeta"; WEB_SUBDIR="public_html/status"; DATA_DIR="%s"' % DATA + NL)

# Kurulumun biraktigi dosyalar
for f in ("collector.sh", "config.env", ".act_state", ".upd_cache",
          ".ioproc_state", ".csf_state", ".ver_cache"):
    io.open(os.path.join(DATA, f), "w", newline=NL).write("x" + NL)
io.open(os.path.join(DATA, "kullanicinin_kendi_dosyasi"), "w").write("dokunma" + NL)
for f in (".proc_snapshot", ".metrics_history", ".disk_history", ".diskacct_history"):
    io.open(os.path.join(HOME, f), "w").write("x" + NL)
io.open(os.path.join(HOME, "onemli_dosya"), "w").write("dokunma" + NL)
io.open(WEB + "/index.php", "w").write("<?php" + NL)
io.open(WEB + "/config.php", "w").write("<?php return [];" + NL)

HT = NL.join([
    "# cPanel-generated php ini directives, do not edit",
    "<IfModule php8_module>",
    "   php_value upload_max_filesize 64M",
    "</IfModule>",
    "# BEGIN server-status-monitor access control",
    "Order deny,allow",
    "Deny from all",
    "# END server-status-monitor access control",
    "# kullanicinin kendi kurali",
    "Options -Indexes",
    "",
])
io.open(WEB + "/.htaccess", "w", newline=NL).write(HT)

# crontab yerine sahte: PATH'in basina konur
io.open(TMP + "/bin/crontab", "w", newline=NL).write(NL.join([
    "#!/bin/sh",
    'if [ "$1" = "-l" ]; then cat "%s/crontab.txt" 2>/dev/null; exit 0; fi' % TMP,
    'cat > "%s/crontab.txt"' % TMP, ""]))
os.chmod(TMP + "/bin/crontab", 0o755)
io.open(TMP + "/crontab.txt", "w", newline=NL).write(NL.join([
    "0 3 * * * /usr/local/cpanel/scripts/upcp",
    "* * * * * %s/collector.sh >/dev/null 2>&1" % DATA, ""]))

env = dict(os.environ)
env["PATH"] = TMP + "/bin" + os.pathsep + env["PATH"]
env["HOME_DIR"] = HOME
r = subprocess.run(["bash", "uninstall.sh", "--yes"], cwd=DEPO,
                   capture_output=True, text=True, env=env)
print(r.stdout.strip()[-400:] if r.stdout else (r.stderr or "")[:400])
print()

gecen = kalan = 0


def ck(ad, kosul):
    global gecen, kalan
    if kosul:
        gecen += 1
        print("  %-52s -> tamam" % ad)
    else:
        kalan += 1
        print("  BASARISIZ %s" % ad)


def var(p):
    return os.path.exists(p)


ck("cikis kodu sifir", r.returncode == 0)
ck("collector silindi", not var(DATA + "/collector.sh"))
ck("durum dosyalari silindi", not var(DATA + "/.act_state") and not var(DATA + "/.ioproc_state"))
ck("KULLANICININ dosyasi DURUYOR", var(DATA + "/kullanicinin_kendi_dosyasi"))
ck("index.php silindi", not var(WEB + "/index.php"))
ck("config.php DURUYOR (--purge yok)", var(WEB + "/config.php"))
ck("besleme dosyalari silindi", not var(HOME + "/.proc_snapshot") and not var(HOME + "/.diskacct_history"))
ck("hesabin diger dosyasi DURUYOR", var(HOME + "/onemli_dosya"))

ht = io.open(WEB + "/.htaccess", encoding="utf-8").read()
ck(".htaccess DURUYOR", var(WEB + "/.htaccess"))
ck("cPanel PHP blogu KORUNDU", "php8_module" in ht and "upload_max_filesize" in ht)
ck("kullanicinin kurali KORUNDU", "Options -Indexes" in ht)
ck("bizim blok SILINDI", "server-status-monitor access control" not in ht and "Deny from all" not in ht)

cron = io.open(TMP + "/crontab.txt", encoding="utf-8").read()
ck("cron satirimiz silindi", "collector.sh" not in cron)
ck("baska cron satiri KORUNDU", "upcp" in cron)

# --purge: config ve kayit da gitsin
io.open(WEB + "/config.php", "w").write("<?php return [];" + NL)
r2 = subprocess.run(["bash", "uninstall.sh", "--purge", "--yes"], cwd=DEPO,
                    capture_output=True, text=True, env=env)
ck("--purge config.php'yi siler", not var(WEB + "/config.php"))
ck("--purge kayitli yanitlari siler", not var(DEPO + "/.install.conf"))

# Kayit yoksa durmali (yanlis dosya silmektense dur)
r3 = subprocess.run(["bash", "uninstall.sh", "--yes"], cwd=DEPO,
                    capture_output=True, text=True, env=env)
ck("kayit yoksa calismaz", r3.returncode != 0 and "no saved config" in (r3.stdout + r3.stderr))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
