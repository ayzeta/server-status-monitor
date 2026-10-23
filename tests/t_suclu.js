// IO bekleme suclu satirini KAYNAKTAN cikarip sinar.
//
// Gercek olay: IO bekleme %18'ken satir "xxhesap 15 KB/s" diyordu. Hesap listesi
// LVE'den gelir ve yalniz cPanel hesaplarini gorur; yuk root tarafindaysa orada
// hic gorunmez. Artik ikisi birlikte yazilir, buyuk olan onde.
const fs = require('fs');
const P = require('path').join(__dirname, '..', 'src', 'index.php');
const src = fs.readFileSync(P, 'utf8');

const bas = src.indexOf("  let topIo='';");
const son = src.indexOf('if(s)topIo=suffix(s);', bas) + 'if(s)topIo=suffix(s);'.length;
let kod = src.slice(bas, son) + '\n}';          // acilan blok kapatilir

const fn = new Function('data', 'fmtKbps', 'suffix',
  kod.replace("let topIo='';", "let topIo='';") + '\nreturn topIo;');

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

console.log('\nGECEN: ' + gecen + '  KALAN: ' + kalan);
process.exit(kalan ? 1 : 0);
