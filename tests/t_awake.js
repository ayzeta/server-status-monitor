// "Otomatik guncelleme uyanik-kal ayarini sifirliyor mu" — OLCUM.
// Blok KAYNAKTAN cikarilir; localStorage sayfa yuklemeleri arasinda KORUNUR
// (gercek tarayicidaki gibi), wakeLock davranisi senaryoya gore secilir.
// Guncelleme sonrasi sayfa kendini yeniliyor (tick: appVer != PAGE_VER), yani
// olculen sey tam olarak "yeni bir sayfa yuklemesi" .
const fs = require('fs');
const P = require('path').join(__dirname, '..', 'src', 'index.php');
const src = fs.readFileSync(P, 'utf8');

const bas = src.indexOf('  const awBtn=document.getElementById(\'awake-btn\');');
const son = src.indexOf('\n  }', src.indexOf("document.addEventListener('visibilitychange',acq)", bas)) + 4;
const blok = src.slice(bas, son);
if (bas < 0 || blok.length < 100) { console.log('blok bulunamadi'); process.exit(2); }

// Tarayici yerine gecenler ---------------------------------------------------
const depo = new Map();                       // localStorage: yuklemeler arasi KALICI
const localStorage = {
  getItem: k => (depo.has(k) ? depo.get(k) : null),
  setItem: (k, v) => depo.set(k, String(v)),
};

function sayfaYukle({ kilitVerilir = true, gorunur = true, KEEP_AWAKE = false }) {
  const dinleyici = {};
  const btn = {
    hidden: true, _sinif: new Set(), _attr: {},
    classList: { toggle: (c, v) => (v ? btn._sinif.add(c) : btn._sinif.delete(c)) },
    setAttribute: (k, v) => (btn._attr[k] = v),
    addEventListener: (e, f) => (dinleyici[e] = f),
  };
  const durum = { kilitSayisi: 0, serbest: 0 };
  const navigator = {
    wakeLock: {
      request: async () => {
        if (!kilitVerilir) { const e = new Error('NotAllowed'); e.name = 'NotAllowedError'; throw e; }
        durum.kilitSayisi++;
        return { release: async () => { durum.serbest++; }, addEventListener: () => {} };
      },
    },
  };
  const document = {
    getElementById: () => btn,
    visibilityState: gorunur ? 'visible' : 'hidden',
    addEventListener: () => {},
  };
  const f = new Function('document', 'navigator', 'localStorage', 'KEEP_AWAKE', 't',
    blok + '\nreturn {btn:document.getElementById(), tikla:()=>0};');
  f(document, navigator, localStorage, KEEP_AWAKE, s => s);
  return { btn, durum, tikla: () => dinleyici.click && dinleyici.click() };
}

let gecen = 0, kalan = 0;
function ck(ad, gelen, beklenen) {
  const g = JSON.stringify(gelen), b = JSON.stringify(beklenen);
  if (g === b) { gecen++; console.log('  ' + ad.padEnd(52) + ' -> ' + g); }
  else { kalan++; console.log('  BASARISIZ ' + ad + ': beklenen=' + b + ' gelen=' + g); }
}
const bekle = () => new Promise(r => setImmediate(r));

(async () => {
  // 1) Ilk yukleme: tercih yok, config varsayilani kapali
  let s = sayfaYukle({});
  await bekle();
  ck('ilk yukleme: dugme kapali', s.btn._sinif.has('on'), false);
  ck('ilk yukleme: kilit alinmaz', s.durum.kilitSayisi, 0);

  // 2) Kullanici dugmeye basiyor
  s.tikla();
  await bekle();
  ck('tiklayinca kayit yazilir', depo.get('az-awake'), '1');
  ck('tiklayinca kilit alinir', s.durum.kilitSayisi, 1);

  // 3) GUNCELLEME: sayfa kendini yeniliyor, localStorage AYNI
  s = sayfaYukle({});
  await bekle();
  ck('yenilemeden sonra kayit DURUYOR', depo.get('az-awake'), '1');
  ck('yenilemeden sonra dugme acik', s.btn._sinif.has('on'), true);
  ck('yenilemeden sonra kilit yeniden alinir', s.durum.kilitSayisi, 1);

  // 4) Yenileme ARKA PLANDA olursa (kullanici baska sekmede)
  s = sayfaYukle({ gorunur: false });
  await bekle();
  ck('arka planda: kayit yine durur', depo.get('az-awake'), '1');
  ck('arka planda: kilit ALINMAZ (gorunur degil)', s.durum.kilitSayisi, 0);
  ck('arka planda: dugme YANMAZ (kilit yok, yalan soylemez)', s.btn._sinif.has('on'), false);

  // 5) Tarayici kilidi REDDEDERSE
  s = sayfaYukle({ kilitVerilir: false });
  await bekle();
  ck('reddedilince: kayit yine durur', depo.get('az-awake'), '1');
  ck('reddedilince: kilit yok', s.durum.kilitSayisi, 0);
  ck('reddedilince: dugme YANMAZ', s.btn._sinif.has('on'), false);

  // 6) Tercih acik + kilit yokken tiklama: KAPATMAZ, yeniden dener
  s = sayfaYukle({ kilitVerilir: false });
  await bekle();
  s.tikla(); await bekle();
  ck('kilitsizken tiklama tercihi KAPATMAZ', depo.get('az-awake'), '1');

  // 7) Ayni durumda kilit verilebilir hale gelirse tiklama onu alir
  s = sayfaYukle({ gorunur: false });     // once kilitsiz basla
  await bekle();
  ck('arka planda kilit yok', s.durum.kilitSayisi, 0);
  s.tikla(); await bekle();
  ck('tiklama tercihi hala acik birakir', depo.get('az-awake'), '1');

  // 8) Gercekten kapatmak: kilit TUTULUYORKEN tiklama
  s = sayfaYukle({});
  await bekle();
  ck('kilit tutuluyor', s.durum.kilitSayisi, 1);
  s.tikla(); await bekle();
  ck('kilitliyken tiklama KAPATIR', depo.get('az-awake'), '0');
  ck('kapatinca kilit birakilir', s.durum.serbest, 1);
  ck('kapatinca dugme soner', s.btn._sinif.has('on'), false);

  console.log('\nGECEN: ' + gecen + '  KALAN: ' + kalan);
})();
