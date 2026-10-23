"""Guncelleme uygulandiktan sonra "guncelleme var" yazisi hemen dusuyor mu.

Gercek olay: kullanici guncelledi (sunucu v1.5.35), footer hala "guncelleme var (1)"
diyordu — sayi gunluk onbellekten okunuyordu. Sayi artik her turda YERELDEN sayilir.

Test GERCEK git deposu kurar: iki depo (uzak + yerel), yerel geride birakilir,
sonra pull edilir; sayinin ag erisimi olmadan 0'a dusmesi beklenir.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _os
# Depo koku: test dosyasinin yerinden bulunur (tests/ -> kok).
KOK = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))) + '/'
src = io.open(KOK + "src/collector.sh", encoding='utf-8', errors='replace').read()

# Kaynaktan sayma komutunu cikar — elle yazmayalim
m = re.search(r'UPD_BEHL=\$\(git -C "\$REPO_DIR" (rev-list --count "HEAD\.\.origin/\$UPD_BRL")',
              src)
if not m:
    sys.exit("yerel sayma komutu bulunamadi")
print("kaynaktaki sayma:", m.group(1))

tmp = tempfile.mkdtemp(prefix="beh")
uzak = os.path.join(tmp, "uzak")
yerel = os.path.join(tmp, "yerel")


def g(*a, cwd=None):
    r = subprocess.run(["git"] + list(a), cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip()


pass_ = fail = 0


def ck(ad, gelen, beklenen):
    global pass_, fail
    if str(gelen) == str(beklenen):
        pass_ += 1
        print("  %-44s -> %s" % (ad, gelen))
    else:
        fail += 1
        print("  BASARISIZ %s: beklenen=%s gelen=%s" % (ad, beklenen, gelen))


os.makedirs(uzak)
g("init", "-q", "-b", "main", cwd=uzak)
g("config", "user.email", "t@t"), g("config", "user.name", "t")
subprocess.run(["git", "config", "user.email", "t@t"], cwd=uzak)
subprocess.run(["git", "config", "user.name", "t"], cwd=uzak)
io.open(os.path.join(uzak, "a.txt"), "w").write("1")
g("add", "-A", cwd=uzak); g("commit", "-qm", "ilk", cwd=uzak)
g("clone", "-q", uzak, yerel)
subprocess.run(["git", "config", "user.email", "t@t"], cwd=yerel)
subprocess.run(["git", "config", "user.name", "t"], cwd=yerel)


def say():
    dal = g("rev-parse", "--abbrev-ref", "HEAD", cwd=yerel)
    return g("rev-list", "--count", "HEAD..origin/%s" % dal, cwd=yerel)


ck("klon tazeyken geride degil", say(), "0")

# Uzakta iki yeni tur
for i in (2, 3):
    io.open(os.path.join(uzak, "a.txt"), "w").write(str(i))
    g("add", "-A", cwd=uzak); g("commit", "-qm", "tur%d" % i, cwd=uzak)
ck("fetch YAPILMADAN sayi degismez", say(), "0")

g("fetch", "-q", "origin", "main", cwd=yerel)
ck("fetch sonrasi 2 tur geride", say(), "2")

# Guncelleme uygulandi (update.sh'in yaptigi: pull)
g("merge", "-q", "origin/main", cwd=yerel)
ck("guncelleme sonrasi ANINDA 0 (ag yok)", say(), "0")

shutil.rmtree(tmp, ignore_errors=True)
print()
print("GECEN: %d  KALAN: %d" % (pass_, fail))
sys.exit(1 if fail else 0)
