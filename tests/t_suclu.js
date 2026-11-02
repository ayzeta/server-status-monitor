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

const fn = new Function('data', 'fmtKbps', 'suffix',
  kod + '\nreturn topIo;');

const kb = v => (v >= 1024 ? (Math.round(v / 1024 * 10) / 10) + ' MB/s'
                           : Math.round(v) + ' KB/s');
const ek = s => ' — ' + s;

let gecen = 0, kalan = 0;
function ck(ad, gelen, beklenen) {
  if (gelen === beklenen) { gecen++; console.log('  ' + ad.padEnd(46) + ' -> ' + JSON.stringify(gelen)); }
  else { kalan++; console.log('  BASARISIZ ' + ad + ':\n    beklenen=' + JSON.stringify(beklenen) + '\n    gelen   =' + JSON.stringify(gelen)); }
}

// Gercek olay: hesap kucuk, surec buyuk -> surec onde, hesap da yazilir
ck('surec buyuk: once surec, sonra hesap',
   fn({ ioAcct: [['xxhesap', 15]], ioProc: [['mysql', 40960, '/usr/sbin/mariadbd']] }, kb, ek),
   ' — mariadbd 40 MB/s · xxhesap 15 KB/s');

// Hesap buyukse once hesap
ck('hesap buyuk: once hesap',
   fn({ ioAcct: [['agirhesap', 50000]], ioProc: [['root', 200, '/usr/bin/x']] }, kb, ek),
   ' — agirhesap 48.8 MB/s · x 200 KB/s');

// Yalniz biri varsa yalniz o
ck('surec yok: yalniz hesap',
   fn({ ioAcct: [['h', 300]], ioProc: [] }, kb, ek), ' — h 300 KB/s');
ck('hesap yok: yalniz surec',
   fn({ ioAcct: [], ioProc: [['root', 700, '/sbin/jbd2']] }, kb, ek), ' — jbd2 700 KB/s');

// Hicbiri yoksa bos (cagiran taraf top-CPU suclusuna duser)
ck('ikisi de yok -> bos', fn({ ioAcct: [], ioProc: [] }, kb, ek), '');
ck('sifir degerler sayilmaz',
   fn({ ioAcct: [['h', 0]], ioProc: [['r', 0, '/x']] }, kb, ek), '');

// Komut yolu kisaltilir (tam yol satiri sisirirdi)
ck('komut yalniz son parca',
   fn({ ioAcct: [], ioProc: [['root', 1024, '/opt/cpanel/ea-php82/root/usr/bin/php']] }, kb, ek),
   ' — php 1 MB/s');

// Esitlikte surec onde (genis kapsamli olan once okunsun)
ck('esitlikte surec onde',
   fn({ ioAcct: [['h', 500]], ioProc: [['r', 500, '/x/y']] }, kb, ek),
   ' — y 500 KB/s · h 500 KB/s');

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
