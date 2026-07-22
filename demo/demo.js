/* ════════════════════════════════════════════════════════════════════════
   demo.js — server-status-monitor CANLI DEMO motoru  (yalnız GitHub Pages)
   ────────────────────────────────────────────────────────────────────────
   ÜRÜNDEN TAMAMEN AYRIK. src/index.php'de HİÇBİR demo kodu yoktur; bu dosya
   yalnızca build ile üretilen statik docs/ kopyasına eklenir ve kurulan
   sunuculara ASLA gitmez. Gerçek arayüzü index.php'nin global render(data)'sıyla
   besler; kendi içinde servis/süreç/metrik verisini üretir, eksik süreç
   iskeletini enjekte eder, canlı fetch build tarafından etkisizleştirilir.

   Dondurma (ekran görüntüsü/GIF için):  ?snap=calm|issues|recovery  &theme=dark|light
   ════════════════════════════════════════════════════════════════════════ */
(function () {
  var P = new URLSearchParams(location.search);
  var SNAP = P.get('snap');                 // null | calm | issues | recovery
  if (P.get('theme')) document.documentElement.setAttribute('data-theme', P.get('theme'));

  var CORES = 12, TICK_MS = 2600, STEP = 60;
  var ACC = ['bluewave','shopfast','pixelcart','acmeco','nordvps','ledger','brightmail',
             'zencache','oakhost','riverside','maplebox','summitio','harborlab','delta7',
             'novastore','quibble','fernpost','glacier','tandem','vector9'];
  function pick(i){ return ACC[i % ACC.length]; }
  function pad(n){ return (n<10?'0':'')+n; }

  // ── Sağlıklı servisler (her render'da gönderilir; index.php baseline'ı build
  //    makinesinde "Offline" olabilir, bunlar onu "Operational"a çevirir) ──────
  function ck(label, note, ver, upS, up){ var c={ok:true,label:label,note:note}; if(ver)c.ver=ver; if(upS){c.upS=upS;c.up=up||0;} return c; }
  var SERVICES = {
    web:  {status:'operational',ok:5,total:5,checks:[
      ck('LiteSpeed','running','6.3.6','10h',36000), ck('HTTPS (443)','responding · listening'),
      ck('HTTP (80)','responding · listening'), ck('WHM (2087)','running · listening','cPanel 11.136.0.29','35d',3024000),
      ck('cPanel (2083)','running · listening')]},
    mail: {status:'operational',ok:9,total:9,checks:[
      ck('SMTP (25)','running · listening','Exim 4.99.4','6d',518400), ck('SMTP Submit. (587)','running · listening'),
      ck('SMTPS (465)','running · listening'), ck('POP3 (110)','running · listening','Dovecot 2.4.4','6d',518400),
      ck('POP3S (995)','running · listening'), ck('IMAP (143)','running · listening'),
      ck('IMAPS (993)','running · listening'), ck('Webmail (2095)','running · listening'),
      ck('Webmail SSL (2096)','running · listening')]},
    dns:  {status:'operational',ok:2,total:2,checks:[
      ck('DNS TCP (53)','running · listening','BIND 9.11.36','6d',518400), ck('DNS UDP (53)','listening')]},
    sec:  {status:'operational',ok:5,total:5,checks:[
      ck('Imunify360','running','8.13.6','6d',518400), ck('LFD','running','v16.20','36m',2160),
      ck('CSF firewall','enabled','v16.20'), ck('ModSecurity','SecRuleEngine On','2.9.13'),
      ck('CageFS','enabled','7.6.38')]},
    db:   {status:'operational',ok:2,total:2,checks:[
      ck('MySQL (3306)','running · listening','10.11.13','6d',518400), ck('MySQL ping','alive')]},
    cache:{status:'operational',ok:2,total:2,checks:[
      ck('Redis (6379)','responding · listening','5.0.3','19d',1641600), ck('Memcached (11211)','responding · listening','1.5.22','6d',518400)]},
    ftp:  {status:'operational',ok:2,total:2,checks:[
      ck('FTP service','running · listening','1.0.52','3d',259200), ck('Kernel state','port bound')]}
  };

  // ── Eksik SÜREÇ iskeletini enjekte et (index.php süreç verisi yokken bu
  //    bölümü hiç basmaz; render()/renderProcs tbody'leri doldurabilsin diye) ──
  function ensureSkeleton(){
    if (document.getElementById('proc-row')) return;
    var log = document.querySelector('.log-card');
    if (!log) return;
    var logSec = log.previousElementSibling;         // "Event log" başlığı
    var parent = log.parentNode;
    function tblCard(title, extra, headCells, tbodyId){
      return '<div class="proc-card"><div class="proc-title">'+title+(extra||'')+'</div>'+
             '<table class="proc-table"><thead><tr>'+headCells+'</tr></thead><tbody id="'+tbodyId+'"></tbody></table></div>';
    }
    var U=t('User'), CMD=t('Command');
    var cpuC='<th>PID</th><th>'+U+'</th><th class="num">CPU%</th><th class="num">MEM%</th><th>'+t('Time')+'</th><th>'+CMD+'</th>';
    var ramC='<th>PID</th><th>'+U+'</th><th class="num">MEM%</th><th class="num">RSS</th><th>'+CMD+'</th>';
    var dskC='<th>'+t('Account')+'</th><th></th><th class="num">GB</th>';
    var phpC='<th>'+t('Account')+'</th><th></th><th class="num">'+t('Procs')+'</th>';
    var sqlC='<th>ID</th><th>'+U+'</th><th>'+t('DB')+'</th><th>'+t('Query')+'</th><th class="num">'+t('Time(s)')+'</th><th>'+t('State')+'</th>';

    var sec=document.createElement('div'); sec.className='sec'; sec.style.marginTop='12px';
    sec.innerHTML=t('Processes')+' <span class="proc-age" id="proc-age"></span> <span id="act-chips"></span>';

    var row=document.createElement('div'); row.className='proc-row'; row.id='proc-row';
    row.innerHTML = tblCard(t('Top processes · CPU'),'',cpuC,'pt-cpu')
      + tblCard(t('Top processes · RAM'),'',ramC,'pt-ram')
      + tblCard(t('Top disk · account'),' <span class="proc-age">&middot; '+t('GB used')+'</span>',dskC,'pt-disk')
      + tblCard(t('PHP · account'),' <span class="proc-age">&middot; '+t('active+idle')+'</span>',phpC,'pt-php');

    var sqlRow=document.createElement('div'); sqlRow.className='proc-row-sql';
    sqlRow.innerHTML='<div class="proc-card"><div class="proc-title">'+t('MySQL · active queries')+
      '<span class="proc-age" id="sql-thr"></span></div><table class="proc-table"><thead><tr>'+sqlC+
      '</tr></thead><tbody id="pt-sql"></tbody></table></div>';

    parent.insertBefore(sec, logSec);
    parent.insertBefore(row, logSec);
    parent.insertBefore(sqlRow, logSec);
  }

  // ── Sparkline geçmişini ön-doldur (index.php baseline'ı boş) ───────────────
  function seedHistory(kind){
    var keys=['l1','l5','l15','cpu','ram','disk','iow','wrk','rx','tx','mq'];
    keys.forEach(function(k){ if(hist[k]) hist[k].length=0; });
    histT.length=0;
    var base=new Date(clock.getTime()-30*STEP*1000);
    for (var i=0;i<30;i++){
      var f=i/29, w=Math.sin(i/3.5), w2=Math.sin(i/5+1);
      var ramp = kind==='ramp'? f : kind==='settle'? (1-f) : 0.15;   // 0..1 eğilim
      histT.push(pad(base.getHours())+':'+pad(base.getMinutes()));
      hist.l1.push(+(4.2+ramp*20+w*0.5).toFixed(2));
      hist.l5.push(+(5.0+ramp*17+w2*0.4).toFixed(2));
      hist.l15.push(+(5.2+ramp*12+w*0.3).toFixed(2));
      hist.cpu.push(Math.round(24+ramp*66+w*4));
      hist.ram.push(Math.round(62+ramp*22+w2*1.5));
      hist.disk.push(59);
      hist.iow.push(Math.max(0,Math.round(1+ramp*7)));
      hist.wrk.push(Math.round(8+ramp*50));
      hist.rx.push(Math.round(235+ramp*2400+w*80));
      hist.tx.push(Math.round(69+ramp*950+w2*40));
      hist.mq.push(Math.round(8+ramp*(kind==='ramp'?1100:0)));
      base=new Date(base.getTime()+STEP*1000);
    }
  }

  // ── Demo saati ─────────────────────────────────────────────────────────────
  var clock = new Date();
  function stamp(){ var d=clock; return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds()); }

  // ── Dünya durumu ───────────────────────────────────────────────────────────
  var S = { load1:4.2,load5:5.1,load15:5.3,cpu:24,ram:62,disk:59,iow:1,rxK:235,txK:69,rxSat:2,txSat:1,
    workers:8,idle:336,mailq:8,mysqlThr:1,inode:41,ioRKB:196,ioWKB:734,dbrt:1,webrt:3,
    acts:[null,null,null,null],imFiles:0,imAcct:'',diskGrow:'',raid:null,smart:null,mismatch:0 };

  var CALM={load1:4.2,load5:5.1,load15:5.3,cpu:24,ram:62,disk:59,iow:1,rxK:235,txK:69,rxSat:2,txSat:1,
    workers:8,idle:336,mailq:8,mysqlThr:1,inode:41,ioRKB:196,ioWKB:734,dbrt:1,webrt:3};
  function tgt(o){ var r={}; for(var k in CALM)r[k]=CALM[k]; for(var j in o)r[j]=o[j]; return r; }

  // Yavaşlatılmış: uzun ramp'ler + kritik fazlarda uzun tutuş
  var PHASES=[
    {n:5, t:tgt({}), on:function(){ S.acts=[null,null,null,null]; S.imAcct=''; S.imFiles=0; S.diskGrow=''; S.raid=null; S.smart=null; S.mismatch=0; }},
    {n:6, t:tgt({rxK:2650,txK:1080,rxSat:76,txSat:60,workers:18,idle:430,cpu:47,load1:7.6,load5:6.8,load15:6.1,ram:66,mailq:34})},
    {n:5, t:tgt({rxK:2500,txK:1000,rxSat:72,txSat:57,workers:20,idle:440,cpu:52,load1:9.2,load5:8.0,load15:6.8,ram:68,iow:6,ioRKB:22400,ioWKB:31800,dbrt:4,mailq:36}),
      on:function(){ S.acts[0]=40; S.diskGrow='+3 GB/24h'; }},
    {n:7, t:tgt({rxK:2900,txK:1150,rxSat:83,txSat:66,workers:56,idle:150,cpu:92,load1:26,load5:22,load15:17,ram:74,iow:9,ioRKB:18800,ioWKB:24200,dbrt:12})},
    {n:7, t:tgt({rxK:2700,txK:1050,rxSat:80,txSat:63,workers:60,idle:120,cpu:90,load1:24,load5:22,load15:18,ram:85,iow:8,dbrt:20}),
      on:function(){ S.acts[2]=30; S.acts[3]=45; S.imAcct=ACC[0]; S.imFiles=42000; }},
    {n:7, t:tgt({rxK:2600,txK:1020,rxSat:78,txSat:61,workers:58,idle:130,cpu:88,load1:24,load5:23,load15:19,ram:83,iow:7,mysqlThr:26,dbrt:185})},
    {n:7, t:tgt({rxK:2500,txK:1000,rxSat:76,txSat:60,workers:52,idle:160,cpu:84,load1:22,load5:21,load15:19,ram:81,iow:8,mysqlThr:24,dbrt:150,inode:82,mailq:1180}),
      on:function(){ S.raid='resync'; S.smart='SMART: /dev/sda 4 reallocated sectors'; }},
    {n:5, t:tgt({rxK:2500,txK:1000,rxSat:76,txSat:60,workers:52,idle:160,cpu:86,load1:23,load5:22,load15:20,ram:82,iow:8,mysqlThr:25,dbrt:160,inode:82,mailq:1180})},
    {n:9, t:tgt({cpu:26,load1:4.6,load5:5.2,load15:6.0,ram:61,iow:1,workers:10,idle:340,mysqlThr:2,inode:41,mailq:12,dbrt:2,rxK:280,txK:90,rxSat:6,txSat:3}),
      on:function(){ S.acts=[null,null,null,null]; S.imAcct=''; S.imFiles=0; S.diskGrow=''; S.raid=null; S.smart=null; S.mismatch=0; }},
    {n:4, t:tgt({})}
  ];
  var pi=0, pt=0;
  function ease(a,b){ return a+(b-a)*0.34; }
  function jit(v,a){ return v+(Math.random()*2-1)*a; }
  function stepPhase(){
    var ph=PHASES[pi];
    if (pt===0 && ph.on) ph.on();
    for (var k in ph.t) S[k]=ease(S[k], ph.t[k]);
    for (var i=0;i<4;i++) if (S.acts[i]!=null) S.acts[i]+=STEP;
    if (S.imAcct && S.acts[3]!=null) S.imFiles=Math.min(184000, S.imFiles+27000);
    if (++pt>=ph.n){ pt=0; pi=(pi+1)%PHASES.length; }
  }

  // ── Renk yardımcıları (eşikler index.php ile aynı) ─────────────────────────
  function cpuCol(v){ return v>=90?'var(--danger)':v>=80?'var(--warn)':'var(--c-cpu)'; }
  function ramCol(v){ return v>=85?'var(--danger)':v>=70?'var(--warn)':'var(--c-ram)'; }
  function iowCol(v){ return v>=15?'var(--danger)':v>=8?'var(--warn)':'var(--c-iow)'; }
  function netCol(s){ return s>=90?'var(--danger)':s>=70?'var(--warn)':'var(--accent)'; }
  function inoCol(v){ return v>=90?'var(--danger)':v>=80?'var(--warn)':'var(--hint)'; }
  function thrCol(v){ return v>=CORES*2?'var(--danger)':v>=CORES?'var(--warn)':'var(--hint)'; }
  function diskCol(){ if(S.smart||S.raid==='degraded'||S.inode>=90||S.disk>=90)return'var(--danger)';
    if(S.raid==='resync'||S.mismatch>0||S.inode>=80||S.disk>=75)return'var(--warn)'; return'var(--c-disk)'; }
  function lv(v,hi,cr){ return v>=cr?2:v>=hi?1:0; }
  function overall(v){
    var L=0, off=[];
    function add(l,label){ if(l>0){ off.push([l,label]); if(l>L)L=l; } }
    add(lv(v.load1/CORES,1.0,2.0),'load '+(v.load1/CORES).toFixed(1)+'×');
    add(lv(v.cpu,80,90),'CPU '+Math.round(v.cpu)+'%');
    add(lv(v.ram,70,85),'RAM '+Math.round(v.ram)+'%');
    add(lv(v.iowait,8,15),'IO '+Math.round(v.iowait)+'%');
    add(lv(Math.max(v.netRxSat,v.netTxSat),70,90),'net '+Math.round(Math.max(v.netRxSat,v.netTxSat))+'%');
    add(lv(v.lsphpTotal,CORES,CORES*2),v.lsphpTotal+' workers');
    add(lv(v.mysqlThr,CORES,CORES*2),'MySQL '+v.mysqlThr);
    add(lv(v.inodePct,80,90),'inode '+v.inodePct+'%');
    add(lv(v.mailQ,374,374*3),'mailq '+v.mailQ);
    if(S.raid==='degraded')add(2,v.raidTxt); else if(S.raid==='resync')add(1,v.raidTxt);
    if(S.smart)add(2,'SMART pre-fail');
    off.sort(function(a,b){return b[0]-a[0];});
    return { status:L===2?'Issues detected':L===1?'Degraded':'All systems operational',
             color:L===2?'var(--danger)':L===1?'var(--warn)':'var(--ok)',
             detail:off.slice(0,5).map(function(o){return o[1];}).join(' · ') };
  }
  function rate(kb){ kb=Math.round(kb); return kb>=1024?(kb/1024).toFixed(1)+' MB/s':kb+' KB/s'; }

  // ── Süreç tabloları ────────────────────────────────────────────────────────
  var snap=1;
  function procCpu(){
    var hot=S.cpu>75, rows=[];
    rows.push(['438726','mysql',(S.mysqlThr>=CORES?(60+Math.round(jit(8,4))):Math.round(jit(9,2))).toFixed(1),'11.8','6-15:'+pad(20+(pt%40))+':14','/usr/sbin/mariadbd']);
    var base=hot?26:6;
    for(var i=0;i<13;i++){
      var u=pick(i+1), c=Math.max(0.4,jit(base-i*(hot?1.6:0.35),hot?3:0.8)).toFixed(1);
      var cmd=(i%4===0)?'lsphp:/home/'+u+'/public_html/index.php':(i%4===1)?'lsphp:/home/'+u+'/public_html/wp-cron.php':'lsphp';
      if(i===5){ u='root'; cmd='/usr/local/cpanel/3rdparty/bin/php'; c=jit(3,1).toFixed(1); }
      rows.push([''+(1391000+i*37),u,c,'0.1','00:0'+(1+i%6),cmd]);
    }
    rows.sort(function(a,b){return parseFloat(b[2])-parseFloat(a[2]);});
    return rows;
  }
  function procRam(){
    var rows=[['438726','mysql','9.3','11.8','11.1 GB','/usr/sbin/mariadbd'],
      ['1188402','root','3.2','0.4','420 MB','/usr/local/cpanel/3rdparty/bin/php']];
    var mb=[372,268,244,232,198,186,182,178,172,168,161,154];
    for(var i=0;i<12;i++) rows.push([''+(1391000+i*37),pick(i+1),'1.0','0.2',mb[i]+' MB','lsphp']);
    return rows;
  }
  function procPhp(){
    var rows=[], tot=Math.round(S.workers), n=Math.min(16,Math.max(6,Math.round(tot/2)+4)), big=S.workers>CORES;
    for(var i=0;i<n;i++){ var w=big&&i<3?(6+(2-i)):Math.max(1,Math.round(jit(big?3:2,1))); rows.push([pick(i+1),w]); }
    rows.sort(function(a,b){return b[1]-a[1];});
    return rows;
  }
  function diskAcct(){ var gb=[29.8,11.8,10.6,7.8,7.5,7.4,7.2,6.3,6.2,5.7,5.5,5.0,4.6,4.5], r=[]; for(var i=0;i<gb.length;i++)r.push([pick(i),gb[i]]); return r; }
  var SQLQ=['SELECT * FROM wp_options WHERE autoload=\'yes\'','SELECT SLEEP(6)',
    'UPDATE wp_postmeta SET meta_value=? WHERE post_id=?','SELECT COUNT(*) FROM wp_posts WHERE post_status=\'publish\'',
    'DELETE FROM wp_options WHERE option_name LIKE \'_transient_%\'','SELECT * FROM orders WHERE status=\'processing\' ORDER BY created',
    'INSERT INTO wp_actionscheduler_logs ...','OPTIMIZE TABLE wp_postmeta'];
  var SQLST=['Sending data','Sorting result','Locked','Copying to tmp table','Sending data','updating'];
  function procSql(){
    if(S.mysqlThr<8) return [];
    var n=Math.min(12,Math.max(3,Math.round(S.mysqlThr)-3)), r=[];
    for(var i=0;i<n;i++) r.push([''+(48210+i*13),pick(i+2),pick(i+2)+'_wp'+(1+i%3),''+(5+((i*7+pt)%180)),SQLST[i%SQLST.length],SQLQ[i%SQLQ.length]]);
    r.sort(function(a,b){return parseInt(b[3])-parseInt(a[3]);});
    return r;
  }

  // ── render() payload'u ─────────────────────────────────────────────────────
  function genDemoData(){
    var d={
      hostname:'demo.ayzeta.net', threads:CORES, coreCount:CORES, time:stamp(),
      uptime:'35 Days '+pad(15)+':'+pad(22+pi)+':14',
      load1:+S.load1.toFixed(2), load5:+S.load5.toFixed(2), load15:+S.load15.toFixed(2),
      cpu:Math.round(jit(S.cpu,S.cpu>80?1.2:0.8)), ram:Math.round(S.ram), disk:Math.round(S.disk), iowait:Math.max(0,Math.round(S.iow)),
      memUsedGB:Math.round(S.ram/100*94), memTotalGB:94, shmemGB:34, shmemPct:36, shmemCol:'var(--hint)',
      swapUsedGB:0, swapTotalGB:16, swapPct:0,
      diskUsedGB:555, diskTotalGB:933, inodePct:Math.round(S.inode), diskGrow:S.diskGrow,
      raidState:S.raid, raidTxt:S.raid==='resync'?'RAID1 rebuilding 46%':(S.raid==='degraded'?'RAID1 degraded (1/2)':''),
      raidCol:S.raid==='degraded'?'var(--danger)':S.raid==='resync'?'var(--warn)':'var(--hint)',
      raidMismatch:S.mismatch, smartTxt:S.smart?'SMART pre-fail':'', smartMsg:S.smart,
      ioR:rate(S.ioRKB), ioW:rate(S.ioWKB), dstate:S.iow>5?Math.round(jit(2,1)):0, rstate:Math.max(1,Math.round(S.load1/2)),
      rxRate:rate(S.rxK), txRate:rate(S.txK), rxK:Math.round(S.rxK), txK:Math.round(S.txK),
      netRxSat:Math.round(S.rxSat), netTxSat:Math.round(S.txSat), netRxCol:netCol(S.rxSat), netTxCol:netCol(S.txSat),
      lsphpTotal:Math.round(S.workers), lsphpIdle:Math.round(S.idle),
      mailQ:Math.round(S.mailq), mqRaw:Math.round(S.mailq), acctForMailq:374, acctCount:374,
      webResponseTime:Math.round(S.webrt), mysqlResponseTime:Math.round(S.dbrt),
      sslDaysLeft:61, sslExpiry:'2026-09-21',
      mysqlThr:Math.round(S.mysqlThr), mysqlThrCol:thrCol(Math.round(S.mysqlThr)),
      procAge:32, snapMtime:(snap++),
      procCpu:procCpu(), procRam:procRam(), procPhp:procPhp(), procSql:procSql(), diskAcct:diskAcct(),
      acts:[ S.acts[0]!=null?Math.round(S.acts[0]):null, null, S.acts[2]!=null?Math.round(S.acts[2]):null, S.acts[3]!=null?Math.round(S.acts[3]):null ],
      actImunifyP:S.imAcct||null, actImunifyN:S.imFiles||null,
      web:SERVICES.web, mail:SERVICES.mail, dns:SERVICES.dns, sec:SERVICES.sec, db:SERVICES.db, cache:SERVICES.cache, ftp:SERVICES.ftp
    };
    d.cardCol={ cpu:cpuCol(d.cpu), ram:ramCol(d.ram), disk:diskCol(), iow:iowCol(d.iowait) };
    d.overall=overall(d);
    return d;
  }

  // ── DEMO rozeti ─────────────────────────────────────────────────────────────
  function badge(){
    var title=document.querySelector('.hdr-title'); if(!title||document.getElementById('demo-badge'))return;
    var b=document.createElement('span'); b.id='demo-badge'; b.textContent='DEMO';
    b.style.cssText='margin-left:8px;font-size:10px;font-weight:800;letter-spacing:.08em;padding:2px 6px;border-radius:5px;vertical-align:middle;background:var(--warn-bg,rgba(245,158,11,.18));color:var(--warn,#f59e0b);border:1px solid var(--warn,#f59e0b);';
    title.appendChild(b);
    title.style.whiteSpace='nowrap';   // başlık+DEMO rozeti tek satırda kalsın (header dolunca 2. satıra kaymasın)
    var sub=document.querySelector('.hdr-sub'); if(sub)sub.textContent=(LANG_UI==='tr'?'canlı demo · simüle veri':'live demo · simulated data');
  }

  // ── Dondurulmuş kareler (ekran görüntüsü/GIF) ──────────────────────────────
  function freeze(kind){
    if(kind==='issues'){
      S.cpu=91;S.load1=25.8;S.load5=21.4;S.load15=17.2;S.ram=84;S.iow=9;S.workers=60;S.idle=124;
      S.mysqlThr=26;S.dbrt=185;S.inode=82;S.mailq=1180;S.rxK=2880;S.txK=1140;S.rxSat=82;S.txSat=65;
      S.ioRKB=18800;S.ioWKB=24200;S.diskGrow='+3 GB/24h';S.raid='resync';S.smart='SMART: /dev/sda 4 reallocated sectors';
      S.acts=[520,null,300,360];S.imAcct=ACC[0];S.imFiles=163000;
      seedHistory('ramp');
      logs.length=0;
      [['err','MySQL threads_running very high: 26 (query pileup)','15:07:41'],
       ['warn','Inode usage high: 82%','15:07:12'],
       ['warn','RAID1 rebuilding 46% — array rebuilding','15:06:55'],
       ['err','SMART: /dev/sda 4 reallocated sectors','15:06:40'],
       ['err','CPU critical: 91%','15:06:20'],
       ['err','High load: 25.80 (1m)','15:06:02'],
       ['warn','RAM high: 84%','15:05:48'],
       ['ok','imunify scan started','15:05:30'],
       ['ok','backup started','15:04:10']].forEach(function(l){logs.push({type:l[0],msg:l[1],ts:l[2]});});
    } else if(kind==='recovery'){
      seedHistory('settle'); logs.length=0;
      [['ok','MySQL threads_running back to normal','15:14:31'],
       ['ok','CPU back to normal: 26%','15:14:10'],
       ['ok','Load back to normal: 4.60','15:13:58'],
       ['ok','RAM back to normal: 61%','15:13:40'],
       ['ok','Inode usage back to normal','15:13:22'],
       ['ok','RAID array healthy again','15:13:05'],
       ['ok','SMART pre-failure cleared','15:12:50'],
       ['ok','imunify scan finished','15:12:31'],
       ['ok','backup finished','15:12:10'],
       ['err','MySQL threads_running very high: 26 (query pileup)','15:07:41']].forEach(function(l){logs.push({type:l[0],msg:l[1],ts:l[2]});});
    } else { seedHistory('flat'); logs.length=0; }
    renderLog();
    render(genDemoData());
    redrawSparks();
  }

  // ── Başlat ──────────────────────────────────────────────────────────────────
  function loop(){ stepPhase(); clock=new Date(clock.getTime()+STEP*1000); try{ render(genDemoData()); }catch(e){ if(window.console)console.warn('demo',e);} }
  function start(){
    ensureSkeleton(); badge();
    // Statik demo: dil düğmesi cookie+reload YERİNE önceden üretilmiş EN/TR sayfaları
    // arasında gezinir (Pages'te PHP yok, reload aynı dili döndürürdü). Eski listener'ı
    // atmak için düğmeyi klonlayıp değiştir.
    var lb=document.getElementById('lang-btn');
    if(lb){ var nb=lb.cloneNode(true); lb.parentNode.replaceChild(nb,lb);
      nb.addEventListener('click', function(){ location.href=(LANG_UI==='tr')?'../':'tr/'; }); }
    // Build makinesinde .proc_snapshot yok → PHP baseline "snapshot missing" seed'ler.
    // Demo canlı olayları sıfırdan üretsin diye log'u temizle.
    logs.length=0; try{ sessionStorage.removeItem('az-logs'); }catch(e){} renderLog();
    if(SNAP){ seedHistory('flat'); freeze(SNAP); return; }   // dondurulmuş kare, döngü yok
    seedHistory('flat');
    loop();
    setInterval(loop, TICK_MS);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
