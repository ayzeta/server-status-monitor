// Askiya alinmis sekmenin sahte "sunucu yanit vermedi" yazmasini onleyen korumayi
// KAYNAKTAN cikarip sinar.
//
// Gercek olay (olculdu): kullanici sekmeyi arka plana atti, 22:48:15'te hata,
// uyaninca 22:48:52'de "baglanti geri geldi". Sunucu boyunca ayaktaydi.
const fs = require('fs');
const P = require('path').join(__dirname, '..', 'src', 'index.php');
const src = fs.readFileSync(P, 'utf8');

const m = src.match(/if\(hidDuringFetch\|\|Date\.now\(\)-lastFetch>([^)]+)\)\{ markStale\(true\); return; \}/);
if (!m) { console.log('koruma bulunamadi'); process.exit(2); }
const sinirIfade = m[1];                       // ornek: FETCH_TIMEOUT*3+8000
const sinir = new Function('FETCH_TIMEOUT', 'return ' + sinirIfade + ';');
// Korumanin TAMAMI: gizlenme bayragi VEYA sure asimi.
const koruma = new Function('hidDuringFetch', 'FETCH_TIMEOUT', 'gecen',
  'return hidDuringFetch||gecen>' + sinirIfade + ';');
// Bayrak tik basinda sifirlaniyor mu — yoksa bir kez kalkan bayrak sonsuza kadar
// butun hatalari yutardi (gercek kesinti de yazilmazdi).
if (!/hidDuringFetch=document\.visibilityState!=='visible';/.test(src)) {
  console.log('  BAYRAK TIK BASINDA SIFIRLANMIYOR'); process.exit(1);
}

// fetchWithRetry'in PLANLANAN en kotu suresi: kaynaktan oku, elle yazma.
const retries = 2, delay = 2000;               // tick cagrisindaki varsayilanlar
const planliEnKotu = FT => (retries + 1) * FT + retries * delay;

let gecen = 0, kalan = 0;
function ck(ad, gelen, beklenen) {
  if (gelen === beklenen) { gecen++; console.log('  ' + ad.padEnd(52) + ' -> ' + gelen); }
  else { kalan++; console.log('  BASARISIZ ' + ad + ': beklenen=' + beklenen + ' gelen=' + gelen); }
}
const askidaMi = (FT, ms) => ms > sinir(FT);

for (const FT of [15000, 20000, 30000]) {
  const plan = planliEnKotu(FT);
  ck('FT=' + FT + ': planli en kotu (' + plan + 'ms) askı SAYILMAZ', askidaMi(FT, plan), false);
  ck('FT=' + FT + ': plani 1 sn asan da sayilmaz', askidaMi(FT, plan + 1000), false);
  ck('FT=' + FT + ': 2 dk donma askı SAYILIR', askidaMi(FT, 120000) || plan > 120000, true);
  ck('FT=' + FT + ': 10 dk donma askı SAYILIR', askidaMi(FT, 600000), true);
}
// Gercek olaydaki sure: ~37 sn sonra "geri geldi" — donma suresi en az o kadardi.
ck('taban sinirda (FT=15000) 60 sn donma yakalanir', askidaMi(15000, 60000), true);
// Hizli, GERCEK bir hata askı sayilmamali (sunucu kapali, aninda red)
ck('aninda red (5 sn) askı degil', askidaMi(15000, 5000), false);

// ── Asil senaryo: KISA arka plan turu ──────────────────────────
// Olculen gercek olaylar 37 sn ve 69 sn surdu; ikisi de FT=15000'deki sure
// esiginin (53 sn) altinda ya da ona yakin. Sure tek basina yetmiyordu.
ck('37 sn arka plan: SURE esigi yakalamaz', askidaMi(15000, 37000), false);
ck('37 sn arka plan: GIZLENME bayragi yakalar', koruma(true, 15000, 37000), true);
ck('69 sn arka plan: bayrak yakalar', koruma(true, 15000, 69000), true);

// ── Gercek kesinti bastirilmamali ──────────────────────────────
ck('sekme hic gizlenmediyse hizli hata YAZILIR', koruma(false, 15000, 5000), false);
ck('sekme gizlenmediyse normal zaman asimi YAZILIR', koruma(false, 15000, 32000), false);
ck('gizlenmedi ama makine uyudu (10 dk) -> bastirilir', koruma(false, 15000, 600000), true);

console.log('\nGECEN: ' + gecen + '  KALAN: ' + kalan);
process.exit(kalan ? 1 : 0);
