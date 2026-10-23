// Nokta rengi: PHP ile JS AYNI sinifi mi veriyor. Ikisi de KAYNAKTAN cikarilir.
// Risk: sunucu render'i gri, 30 sn'lik tick kirmizi cizerse satir goz onunde renk
// degistirir — kullanici bunu "durum degisti" sanir.
const fs = require('fs');
const P = require('path').join(__dirname, '..', 'src', 'index.php');
const src = fs.readFileSync(P, 'utf8');

// PHP dali
const pb = src.indexOf("'<span class=\"sub-dot ' . ($c['ok']");
const pe = src.indexOf('"></span>', pb);
const phpIfade = src.slice(pb, pe);
// PHP ucgen zincirini JS'e birebir cevir (yapi ayni, sozdizimi farkli)
const phpJs = phpIfade
  .replace("'<span class=\"sub-dot ' . ", '')
  .replace(/\$c\['ok'\]/g, 'c.ok')
  .replace(/!empty\(\$c\['unknown'\]\)/g, '!!c.unknown')
  // Dilim bir sonraki dize literalinin acilisinda bitiyor: sondaki " . '" atilir.
  .replace(/\s*\.\s*'?\s*$/, '');

// JS ikizi
const jb = src.indexOf("${ch.ok?'ok':(ch.unknown?'muted':'err')}");
if (jb < 0) { console.log('JS dali bulunamadi'); process.exit(2); }
const jsIfade = src.slice(jb + 2, src.indexOf('}', jb + 2));

const php = new Function('c', 'return ' + phpJs + ';');
const js = new Function('ch', 'return ' + jsIfade + ';');

const ORNEK = [
  { ad: 'dogrulanmis iyi', c: { ok: true } },
  { ad: 'dogrulanmis sorun', c: { ok: false } },
  { ad: 'dogrulanamadi', c: { ok: false, unknown: true } },
  { ad: 'unknown ama ok (olmamali, yine de tutarli olsun)', c: { ok: true, unknown: true } },
];
const BEKLENEN = ['ok', 'err', 'muted', 'ok'];

let fail = 0;
ORNEK.forEach((o, i) => {
  const a = php(o.c), b = js(o.c);
  if (a !== b) { fail++; console.log('  AYRISMA ' + o.ad + ': php=' + a + ' js=' + b); }
  else if (a !== BEKLENEN[i]) { fail++; console.log('  BEKLENTI ' + o.ad + ': beklenen=' + BEKLENEN[i] + ' gelen=' + a); }
  else console.log('  ' + o.ad.padEnd(46) + ' -> ' + a);
});
console.log('\nAYRISMA/HATA: ' + fail);
process.exit(fail ? 1 : 0);
