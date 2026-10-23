"""install.sh'in urettigi 'ssmon' komutunu KAYNAKTAN cikarip calistirir.

Yazip birakmak yetmez: uretilen betik bash'ten gectigi gibi alt komutlari da
dogru yere baglamali ve bilinmeyen komutta sifirdan farkli cikmali. Yollar
printf '%q' ile gomuluyor, bosluklu dizinde de bozulmamali.
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
src = io.open(KOK + "install.sh", encoding='utf-8', errors='replace').read()

bas = src.index('WRAPPER="/usr/local/bin/ssmon"')
son = src.index('chmod 0755 "$WRAPPER"', bas) + len('chmod 0755 "$WRAPPER"')
blok = src[bas:son]

TMP = os.path.join(BURASI, "t_ssmon")
shutil.rmtree(TMP, ignore_errors=True)
# BOSLUKLU dizin: printf %q gomme dogru calismazsa burada patlar
REPO = os.path.join(TMP, "depo ve yol")
DATA = os.path.join(TMP, "veri dizini")
os.makedirs(os.path.join(REPO, "src"))
os.makedirs(DATA)
io.open(os.path.join(REPO, "update.sh"), "w", newline=NL).write('echo CAGRILDI-update "$@"' + NL)
io.open(os.path.join(REPO, "install.sh"), "w", newline=NL).write('echo CAGRILDI-install' + NL)
io.open(os.path.join(REPO, "uninstall.sh"), "w", newline=NL).write("echo CAGRILDI-uninstall \"$@\"" + NL)
io.open(os.path.join(DATA, "collector.sh"), "w", newline=NL).write('echo CAGRILDI-collector' + NL)
io.open(os.path.join(REPO, "src", "index.php"), "w", newline=NL).write(
    "<?php" + NL + "const APP_VERSION = '9.9.9'; // yorum" + NL)

betik = NL.join([
    'SRC=%s' % "'" + REPO.replace("\\", "/") + "'",
    'DATA_DIR=%s' % "'" + DATA.replace("\\", "/") + "'",
    'WRAPPER=%s' % "'" + os.path.join(TMP, "ssmon").replace("\\", "/") + "'",
    blok.replace('WRAPPER="/usr/local/bin/ssmon"', ':'),
])
yol = os.path.join(BURASI, "t_ssmon_kur.sh")
io.open(yol, "w", encoding="utf-8", newline=NL).write(betik)
r = subprocess.run(["bash", yol], capture_output=True, text=True, cwd=BURASI)
if r.returncode:
    sys.exit("uretim basarisiz: " + (r.stderr or r.stdout))

SSMON = os.path.join(TMP, "ssmon")
gecen = kalan = 0


def ck(ad, gelen, beklenen):
    global gecen, kalan
    if gelen == beklenen:
        gecen += 1
        print("  %-40s -> %r" % (ad, gelen))
    else:
        kalan += 1
        print("  BASARISIZ %s: beklenen=%r gelen=%r" % (ad, beklenen, gelen))


def kos(*a):
    r = subprocess.run(["bash", SSMON] + list(a), capture_output=True, text=True)
    return (r.stdout + r.stderr).strip(), r.returncode


ck("sozdizimi gecerli",
   subprocess.run(["bash", "-n", SSMON], capture_output=True).returncode, 0)
ck("update dogru betige gider", kos("update")[0], "CAGRILDI-update")
ck("uninstall dogru betige gider ve argumani tasir", kos("uninstall", "--purge")[0], "CAGRILDI-uninstall --purge")
ck("reinstall dogru betige gider", kos("reinstall")[0], "CAGRILDI-install")
ck("collect toplayiciyi cagirir", kos("collect")[0], "CAGRILDI-collector")
ck("version kaynaktan okur", kos("version")[0], "9.9.9")
cikti, kod = kos("olmayan")
ck("bilinmeyen komut: kullanim yazar", cikti.startswith("Usage: ssmon"), True)
ck("bilinmeyen komut: cikis sifirdan farkli", kod != 0, True)
ck("argumansiz cagri da kullanim yazar", kos()[0].startswith("Usage: ssmon"), True)

shutil.rmtree(TMP, ignore_errors=True)
os.remove(yol)
print()
print("GECEN: %d  KALAN: %d" % (gecen, kalan))
sys.exit(1 if kalan else 0)
