// IO bekleme suclu satirini KAYNAKTAN cikarip sinar.
//
// Gercek olay: IO bekleme %18'ken satir "xxhesap 15 KB/s" diyordu. Hesap listesi
// LVE'den gelir ve yalniz cPanel hesaplarini gorur; yuk root tarafindaysa orada
// hic gorunmez. Artik ikisi birlikte yazilir, buyuk olan onde.
const fs = require('fs');
const P = require('path').join(__dirname, '..', 'src', 'index.php');
const src = fs.readFileSync(P, 'utf8');

const bas = src.indexOf("  let topIo='',topIoTxt='';");
const M = 'if(s){topIo=suffix(s);topIoTxt=s;}';
const son = src.indexOf(M, bas) + M.length;
let kod = src.slice(bas, son) + '\n}';          // acilan blok kapatilir

// Blok artik pbase/pscript kullaniyor (surec adi + betik yolu) — onlar da
// KAYNAKTAN alinir, elle kopyalanmaz.
const PS_SON = "    return t.slice(i+1).replace(/^\\/home\\/[^/]+\\//,'').replace(/^\\//,'');};";
const yb = src.indexOf('  const ptok=c=>');   // pscript ptok kullaniyor
const ye = src.indexOf(PS_SON, yb) + PS_SON.length;
if (yb < 0 || ye < PS_SON.length) { console.log('CIKARILAMADI: pbase/pscript'); process.exit(2); }
const yardimci = src.slice(yb, ye);

const fn = new Function('data', 'fmtKbps', 'suffix', 't',
  yardimci + '\n' + kod + '\nreturn topIo;');

const kb = v => (v >= 1024 ? (Math.round(v / 1024 * 10) / 10) + ' MB/s'
                           : Math.round(v) + ' KB/s');
const ek = s => ' — ' + s;
const t = s => s;            // ceviri yok: beklenenler etiketleri ingilizce okur

let gecen = 0, kalan = 0;
function ck(ad, gelen, beklenen) {
  if (gelen === beklenen) { gecen++; console.log('  ' + ad.padEnd(46) + ' -> ' + JSON.stringify(gelen)); }
  else { kalan++; console.log('  BASARISIZ ' + ad + ':\n    beklenen=' + JSON.stringify(beklenen) + '\n    gelen   =' + JSON.stringify(gelen)); }
}

// Gercek olay: hesap kucuk, surec buyuk -> surec onde, hesap da yazilir
ck('surec buyuk: once surec, sonra hesap',
   fn({ ioAcct: [['xxhesap', 15]], ioProc: [['mysql', 40960, '/usr/sbin/mariadbd']] }, kb, ek, t),
   ' — process mariadbd · mysql 40 MB/s · account xxhesap 15 KB/s');

// Hesap buyukse once hesap
ck('hesap buyuk: once hesap',
   fn({ ioAcct: [['agirhesap', 50000]], ioProc: [['root', 200, '/usr/bin/x']] }, kb, ek, t),
   ' — account agirhesap 48.8 MB/s · process x · root 200 KB/s');

// Yalniz biri varsa yalniz o
ck('surec yok: yalniz hesap',
   fn({ ioAcct: [['h', 300]], ioProc: [] }, kb, ek, t), ' — account h 300 KB/s');
ck('hesap yok: yalniz surec',
   fn({ ioAcct: [], ioProc: [['root', 700, '/sbin/jbd2']] }, kb, ek, t), ' — process jbd2 · root 700 KB/s');

// Hicbiri yoksa bos (cagiran taraf top-CPU suclusuna duser)
ck('ikisi de yok -> bos', fn({ ioAcct: [], ioProc: [] }, kb, ek, t), '');
ck('sifir degerler sayilmaz',
   fn({ ioAcct: [['h', 0]], ioProc: [['r', 0, '/x']] }, kb, ek, t), '');

// Komut yolu kisaltilir (tam yol satiri sisirirdi)
ck('komut yalniz son parca',
   fn({ ioAcct: [], ioProc: [['root', 1024, '/opt/cpanel/ea-php82/root/usr/bin/php']] }, kb, ek, t),
   ' — process php · root 1 MB/s');

// Komut ARGUMANLARIYLA geliyor: ad ilk belirtec. Uretimde boyle ('/usr/sbin/
// crond -n', '/usr/bin/imunify-resident --quiet'); kesilmezse satir
// "crond -n · root 163 KB/s" diye okunuyordu.
ck('komut argumanlari ada karismaz',
   fn({ ioAcct: [], ioProc: [['root', 163, '/usr/sbin/crond -n']] }, kb, ek, t),
   ' — process crond · root 163 KB/s');

// Esitlikte surec onde (genis kapsamli olan once okunsun)
ck('esitlikte surec onde',
   fn({ ioAcct: [['h', 500]], ioProc: [['r', 500, '/x/y']] }, kb, ek, t),
   ' — process y · r 500 KB/s · account h 500 KB/s');

// ── Fail ADI: JS kurali collector.sh'teki awk ile AYNI sonucu vermeli ────────
// Iki yol var (sayfa acilisi tarihceden/awk, canli tik JS) ve ikisi ayni olayi
// anlatiyor; biri "python3" oteki "im360.run" derse pano kendi kendisiyle
// celisir. Satirlar GERCEK ps ciktisindan: tests/ornek/ps_yorumlayici.txt.
const nBas = src.indexOf('  const pbase=t=>');
const nSon = src.indexOf('    return b;};', nBas) + '    return b;};'.length;
const pnameFn = new Function('c', src.slice(nBas, nSon) + '\nreturn pname(c);');
const ornek = fs.readFileSync(require('path').join(__dirname, 'ornek', 'ps_yorumlayici.txt'), 'utf8')
  .split('\n').filter(Boolean)
  .map(l => l.split(/\s+/).slice(7).join(' '));   // 8. alandan sonrasi = args

[['php -r ... -> betik adi', 0, 'wpt-wp-cli.php'],
 ['lsphp (argumansiz) aynen kalir', 1, 'lsphp'],
 ['lveps genel degil, dokunulmaz', 2, 'lveps'],
 ['mariadbd: yol kirpilir', 3, 'mariadbd'],
 ['python3 -m im360.run -> modul', 4, 'im360.run'],
 ['python3.6 <betik> -> betik adi', 5, 'agent360'],
 ['lsphp:/yol -> yol atilir', 6, 'lsphp'],
].forEach(([ad, i, bek]) => ck('JS ' + ad, pnameFn(ornek[i]), bek));

console.log('\nGECEN: ' + gecen + '  KALAN: ' + kalan);
process.exit(kalan ? 1 : 0);
