<?php
ini_set('serialize_precision', '-1'); // json_encode float'ları kısa bassın (mail satır limiti)

// ════════════════════════════════════════════════════════════════
// CONFIG — config.php varsa okunur; yoksa varsayılanlarla tek başına çalışır.
// (config.php.example'a bak.) Marka + web kullanıcısı buradan; veri dosyaları
// kullanıcının home'undan türetilir (root cron oraya yazıp chown eder).
// ════════════════════════════════════════════════════════════════
$cfg = @include __DIR__ . '/config.php';
if (!is_array($cfg)) $cfg = [];
$WEB_USER    = $cfg['web_user']      ?? (function_exists('posix_geteuid') ? (posix_getpwuid(posix_geteuid())['name'] ?? '') : ''); // config yoksa PHP'nin çalıştığı kullanıcı (CageFS'te hesap)
$HOME_DIR    = $cfg['home_dir']      ?? ('/home/' . $WEB_USER);
$SITE_TITLE  = $cfg['site_title']    ?? 'Server Status Monitor';
$SITE_SUB    = $cfg['site_subtitle'] ?? 'Real-time server health';
$LOGO_URL    = $cfg['logo_url']      ?? '';
$FAVICON_URL = $cfg['favicon_url']   ?? '';
$CREDIT_TEXT = $cfg['credit_text']   ?? 'Ayzeta';            // footer attribution (config'den değiştirilebilir)
$CREDIT_URL  = $cfg['credit_url']    ?? 'https://ayzeta.net';
$_tw = array_values(array_filter(preg_split('/\s+/', trim($SITE_TITLE)))); // logo yoksa baş harfler (substr: mbstring garanti değil)
$INITIALS = strtoupper(count($_tw) >= 2 ? substr($_tw[0], 0, 1) . substr($_tw[1], 0, 1) : substr(($_tw[0] ?? 'SM'), 0, 2));

// ── Process snapshot ──────────────────────────────────────────
// PHP CageFS içinde diğer kullanıcıların süreçlerini göremez (sanal /proc);
// tam liste root'un dakikalık cron'undan gelir ($HOME_DIR/.proc_snapshot,
// root yazıp web kullanıcısına chown eder). Dosya yoksa bölüm görünmez.
$procSnapFile = $HOME_DIR . '/.proc_snapshot';
$sqlMinSec = 5; // cron'daki 'time >= N' ile aynı olmalı; placeholder metni de bunu kullanır
$procCpu = []; $procRam = []; $procPhp = []; $procSql = []; $procSec = []; $rootSvc = []; $svcAge = []; $svcVer = []; $diskAcct = []; $smartBad = []; $netSpeed = []; $procAge = null;

$procMtime = null;
if (is_readable($procSnapFile)) {
    $procMtime = filemtime($procSnapFile);
    $procAge   = time() - $procMtime;
    $snapRaw  = (string)@file_get_contents($procSnapFile);
    $sections = preg_split('/^--- (.+?) ---$/m', $snapRaw, -1, PREG_SPLIT_DELIM_CAPTURE);
    for ($i = 1; $i < count($sections) - 1; $i += 2) {
        $title = trim($sections[$i]);
        $lines = array_values(array_filter(array_map('rtrim', explode("\n", $sections[$i + 1]))));
        if (stripos($title, 'CPU') !== false) {
            foreach ($lines as $n => $ln) {
                if ($n === 0) continue; // ps başlık satırı
                $p = preg_split('/\s+/', trim($ln), 6); // pid,user,pcpu,pmem,etime,args
                if (count($p) === 6) $procCpu[] = $p;
            }
        } elseif (stripos($title, 'RSS') !== false) {
            foreach ($lines as $n => $ln) {
                if ($n === 0) continue;
                $p = preg_split('/\s+/', trim($ln), 6); // pid,user,pcpu,pmem,rss,comm
                if (count($p) === 6) {
                    $kb   = (int)$p[4];
                    $p[4] = $kb >= 1048576 ? round($kb / 1048576, 1) . ' GB' : round($kb / 1024) . ' MB';
                    $procRam[] = $p;
                }
            }
        } elseif (stripos($title, 'lsphp') !== false) {
            foreach ($lines as $ln) {
                $p = preg_split('/\s+/', trim($ln)); // count,user,comm
                if (count($p) >= 2 && is_numeric($p[0])) $procPhp[] = [$p[1], (int)$p[0]];
            }
        } elseif (stripos($title, 'MySQL') !== false) {
            foreach ($lines as $ln) {
                $p = explode("\t", $ln, 6); // id,user,db,time,state,query (tab-ayrılmış)
                if (count($p) === 6 && is_numeric(trim($p[0]))) $procSql[] = array_map('trim', $p);
            }
        } elseif (stripos($title, 'Security') !== false) {
            foreach ($lines as $ln) {
                $p = preg_split('/\s+/', trim($ln), 2); // key value
                if (count($p) === 2) $procSec[$p[0]] = trim($p[1]);
            }
        } elseif (stripos($title, 'WHM services') !== false) {
            foreach ($lines as $ln) {
                $p = preg_split('/\s+/', trim($ln)); // svc name enabled installed running
                if (count($p) === 5 && $p[0] === 'svc') {
                    $rootSvc[$p[1]] = ['name' => $p[1], 'enabled' => (int)$p[2],
                                       'installed' => (int)$p[3], 'running' => (int)$p[4]];
                }
            }
        } elseif (stripos($title, 'Root checks') !== false) {
            foreach ($lines as $ln) {
                $p = preg_split('/\s+/', trim($ln), 2); // key value
                if (count($p) !== 2) continue;
                if ($p[0] === 'smart_bad') { $smartBad[] = trim($p[1]); } // birden çok disk olabilir
                elseif ($p[0] === 'netspeed') { // "netspeed eth0 1000" — arayüz başına Mbps
                    $ns = preg_split('/\s+/', trim($p[1]));
                    if (count($ns) === 2 && is_numeric($ns[1])) $netSpeed[$ns[0]] = (int)$ns[1];
                } else $procSec[$p[0]] = trim($p[1]);
            }
        } elseif (stripos($title, 'Service ages') !== false) {
            foreach ($lines as $ln) {
                $p = preg_split('/\s+/', trim($ln)); // svcage name seconds
                if (count($p) === 3 && $p[0] === 'svcage' && is_numeric($p[2])) $svcAge[$p[1]] = (int)$p[2];
            }
        } elseif (stripos($title, 'Versions') !== false) {
            foreach ($lines as $ln) {
                $p = preg_split('/\s+/', trim($ln), 3); // ver anahtar "Etiket sürüm"
                if (count($p) === 3 && $p[0] === 'ver') $svcVer[$p[1]] = $p[2];
            }
        } elseif (stripos($title, 'Top disk accounts') !== false) {
            foreach ($lines as $ln) {
                $p = preg_split('/\s+/', trim($ln)); // diskacct user gb
                if (count($p) === 3 && $p[0] === 'diskacct' && is_numeric($p[2])) $diskAcct[] = [$p[1], (float)$p[2]];
            }
        }
    }
}

// ════════════════════════════════════════════════════════════════
// WHM SERVİS VERİSİ — TEK kaynak: ROOT snapshot (cron'daki whmapi1 CLI).
// Eski token'lı HTTP API fallback'i KALDIRILDI (.whm_token kullanılmıyor,
// dosya varsa da okunmaz). Snapshot bayatlarsa svcCheck port yoklamasına
// düşer ve STALE alarmı (Event log + başlık etiketi) zaten kendini duyurur.
// ════════════════════════════════════════════════════════════════
$whmServices  = [];
$whmApiOk     = false;
$whmAcctCount = null;
$svcSrc       = 'none';
$rootFresh    = ($procAge !== null && $procAge <= 180);

if ($rootFresh && $rootSvc) {
    $whmServices = $rootSvc;
    $whmApiOk    = true;
    $svcSrc      = 'root';
}
if ($rootFresh && isset($procSec['acct']) && is_numeric($procSec['acct'])) {
    $whmAcctCount = (int)$procSec['acct'];
}

function whmSvcOk($name, $services) {
    if (!isset($services[$name])) return null;
    $s = $services[$name];
    if (!$s['enabled'] || !$s['installed']) return null;
    return isset($s['running']) ? (bool)$s['running'] : false;
}

// ── Load Average ──────────────────────────────────────────────
$loadRaw  = @file_get_contents('/proc/loadavg');
$loadData = explode(' ', trim($loadRaw));
$load1    = isset($loadData[0]) ? (float)$loadData[0] : 0;
$load5    = isset($loadData[1]) ? (float)$loadData[1] : 0;
$load15   = isset($loadData[2]) ? (float)$loadData[2] : 0;

// ── CPU Core Count ────────────────────────────────────────────
$coreCount = 1;
$cpuinfo   = @file_get_contents('/proc/cpuinfo');
if ($cpuinfo) {
    preg_match_all('/^processor/m', $cpuinfo, $m);
    if (count($m[0]) > 0) $coreCount = count($m[0]);
}

// ── CPU + Network (birleşik örnekleme) ────────────────────────
// Eski kodda CPU 120ms, ağ 250ms olmak üzere iki ayrı bekleme vardı.
// Şimdi ikisi aynı 250ms pencereyi paylaşıyor: istek ~120ms hızlandı,
// CPU ölçümü daha uzun pencerede biraz daha kararlı.
// Not: /proc/loadavg, /proc/stat, /proc/meminfo ve /proc/net/dev bu
// kurulumda SUNUCU GENELİ değerler verir (WHM/top ile çapraz doğrulandı).
// CageFS'in sanallaştırdığı şey /proc/<pid> süreç listesidir — bu yüzden
// süreç tabloları root cron'dan (.proc_snapshot) beslenir.
function readCpuLine() {
    $s = @file('/proc/stat');
    if (!$s) return null;
    $p = preg_split('/\s+/', trim($s[0]));
    return [
        'total'  => $p[1]+$p[2]+$p[3]+$p[4]+$p[5]+$p[6]+$p[7],
        'idle'   => $p[4],
        'iowait' => $p[5],
    ];
}
function getNetStats() {
    $lines = @file('/proc/net/dev');
    $rx = 0; $tx = 0; $if = []; // toplam (görüntü) + arayüz-başına (doygunluk)
    if (!$lines) return ['rx' => 0, 'tx' => 0, 'if' => []];
    foreach ($lines as $line) {
        $line = trim($line);
        if (strpos($line, ':') === false) continue;
        $parts = preg_split('/\s+/', str_replace(':', ' ', $line));
        if (in_array($parts[0], ['lo', 'sit0'])) continue;
        $r = isset($parts[1]) ? (int)$parts[1] : 0;
        $t = isset($parts[9]) ? (int)$parts[9] : 0;
        $rx += $r; $tx += $t;
        $if[$parts[0]] = ['rx' => $r, 'tx' => $t];
    }
    return ['rx' => $rx, 'tx' => $tx, 'if' => $if];
}

// Disk R/W hızı: /proc/diskstats sektör sayaçları (×512 bayt). Sadece tam
// diskler sayılır (sda, nvme0n1, vd/xvd) — partition'lar dahil edilirse
// aynı I/O iki kez sayılır. CPU/ağ ile aynı 250ms pencereyi paylaşır.
function readDiskIO() {
    $lines = @file('/proc/diskstats');
    if (!$lines) return null;
    $r = 0; $w = 0;
    foreach ($lines as $ln) {
        $p = preg_split('/\s+/', trim($ln));
        if (count($p) < 10) continue;
        if (!preg_match('/^(sd[a-z]+|nvme\d+n\d+|vd[a-z]+|xvd[a-z]+)$/', $p[2])) continue;
        $r += (int)$p[5]; $w += (int)$p[9]; // sectors read / written
    }
    return ['r' => $r, 'w' => $w];
}

$c1   = readCpuLine();
$net1 = getNetStats();
$d1   = readDiskIO();
usleep(250000);
$c2   = readCpuLine();
$net2 = getNetStats();
$d2   = readDiskIO();

$cpuUsage = 0; $ioWait = 0;
if ($c1 && $c2 && ($cpuTd = $c2['total'] - $c1['total']) > 0) {
    $cpuUsage = max(0, (int)round((1 - (($c2['idle']   - $c1['idle'])   / $cpuTd)) * 100));
    $ioWait   = max(0, (int)round(     (($c2['iowait'] - $c1['iowait']) / $cpuTd)  * 100));
}
$rxRate = max(0, (int)(($net2['rx'] - $net1['rx']) * 4));
$txRate = max(0, (int)(($net2['tx'] - $net1['tx']) * 4));
// ── Ağ hattı doygunluğu (%) ───────────────────────────────────
// Her arayüzün anlık hızını KENDİ link hızına oranlar, en kötüsünü (max) alır.
// TOPLAMA DEĞİL: atıl bir hat (eth2 gibi) kapasiteyi şişirmesin, dolu bir hat
// gizlenmesin. Gerçek link aggregation'da çekirdek zaten bond0'ı tek arayüz +
// üye toplamı hız olarak sunar → doğru ölçülür. Link hızı ($netSpeed) root
// cron'dan gelir (CageFS PHP'nin /sys/class/net'i okumasını engeller, disk I/O
// gibi); trafik canlı. Tam çift-yönlü: rx/tx ayrı → Network IN/OUT ayrı renklenir.
$netRxSat = null; $netTxSat = null;
if ($rootFresh && $netSpeed) {
    foreach (($net2['if'] ?? []) as $n => $v2) {
        if (empty($netSpeed[$n])) continue;          // hızı bilinmeyen/atıl port atlanır
        $cap = $netSpeed[$n] * 125000;               // Mbps → B/s (yön başına, çift-yönlü)
        if ($cap <= 0) continue;
        $v1  = $net1['if'][$n] ?? ['rx' => 0, 'tx' => 0];
        $netRxSat = max($netRxSat ?? 0, (int)round(max(0, ($v2['rx'] - $v1['rx']) * 4) / $cap * 100));
        $netTxSat = max($netTxSat ?? 0, (int)round(max(0, ($v2['tx'] - $v1['tx']) * 4) / $cap * 100));
    }
}
$netSat = ($netRxSat === null && $netTxSat === null) ? null : max((int)$netRxSat, (int)$netTxSat);
$ioRead = null; $ioWrite = null;
if ($d1 && $d2) {
    $ioRead  = max(0, (int)(($d2['r'] - $d1['r']) * 512 * 4)); // B/s
    $ioWrite = max(0, (int)(($d2['w'] - $d1['w']) * 512 * 4));
}
// CageFS /proc/diskstats'ı sanallaştırıp GİZLİYOR (canlı testte doğrulandı:
// loadavg/meminfo görünür, diskstats görünmez) — kendi örneklememiz boşsa
// root cron'un 1 sn'lik ölçümüne (KB/s) düşülür.
if ($ioRead === null && $rootFresh && isset($procSec['diskio_r']) && is_numeric($procSec['diskio_r'])) {
    $ioRead  = max(0, (int)$procSec['diskio_r'] * 1024);
    $ioWrite = max(0, (int)($procSec['diskio_w'] ?? 0) * 1024);
}

function fmtBytes($b) {
    if ($b >= 1048576) return round($b/1048576, 1) . ' MB/s';
    if ($b >= 1024)    return round($b/1024, 1)    . ' KB/s';
    return $b . ' B/s';
}

// ── Memory ────────────────────────────────────────────────────
$meminfo      = @file('/proc/meminfo');
$memTotal     = 0; $memAvailable = 0; $swapTotal = 0; $swapFree = 0; $memShmem = 0;
if ($meminfo) {
    foreach ($meminfo as $line) {
        if (strpos($line, 'MemTotal:')     === 0) $memTotal     = (int)filter_var($line, FILTER_SANITIZE_NUMBER_INT);
        if (strpos($line, 'MemAvailable:') === 0) $memAvailable = (int)filter_var($line, FILTER_SANITIZE_NUMBER_INT);
        if (strpos($line, 'SwapTotal:')    === 0) $swapTotal    = (int)filter_var($line, FILTER_SANITIZE_NUMBER_INT);
        if (strpos($line, 'SwapFree:')     === 0) $swapFree     = (int)filter_var($line, FILTER_SANITIZE_NUMBER_INT);
        if (strpos($line, 'Shmem:')        === 0) $memShmem     = (int)filter_var($line, FILTER_SANITIZE_NUMBER_INT);
    }
}
$memUsed         = $memTotal - $memAvailable;
$memUsagePercent = $memTotal > 0 ? round(($memUsed / $memTotal) * 100) : 0;
$memTotalGB      = $memTotal > 0 ? round($memTotal / 1024 / 1024, 1) : 0;
$memUsedGB       = round($memUsed / 1024 / 1024, 1);
// Swap: RAM %48 iken bile swap şişiyorsa load'un klasik gizli sebebi. Swap yoksa (total 0) gösterilmez.
$swapTotalGB     = $swapTotal > 0 ? round($swapTotal / 1024 / 1024, 1) : 0;
$swapUsedGB      = $swapTotal > 0 ? round(($swapTotal - $swapFree) / 1024 / 1024, 1) : 0;
$swapUsedMB      = $swapTotal > 0 ? (int)round(($swapTotal - $swapFree) / 1024) : 0;
// Shmem (tmpfs, /dev/shm, opcache paylaşımlı belleği): genelde geri kazanılamaz,
// MemAvailable eksik sayar → % "sağlıklı yoğun" ile "opcache kaçağı"nı ayırmaz.
// Kırılımı göstermek % rakamını yorumlanabilir kılar (76 GB shmem krizi dersi).
$shmemGB         = round($memShmem / 1024 / 1024, 1);
// Eşikler ORANSAL (her sunucuya uygun): shmem toplam RAM'in %'si, swap kullanımı
// toplam swap'ın %'si. Düz GB/MB değeri farklı boyutlu sunucularda anlamsızdı.
$shmemPct        = $memTotal  > 0 ? round($memShmem / $memTotal * 100)          : 0;
$swapPct         = $swapTotal > 0 ? round(($swapTotal - $swapFree) / $swapTotal * 100) : 0;
$shmemCol        = $shmemPct >= 55 ? 'var(--danger)' : ($shmemPct >= 40 ? 'var(--warn)' : 'var(--hint)');

// ── Disk ──────────────────────────────────────────────────────
$diskTotal        = @disk_total_space('/');
$diskFree         = @disk_free_space('/');
$diskUsed         = $diskTotal - $diskFree;
$diskUsagePercent = $diskTotal > 0 ? round(($diskUsed / $diskTotal) * 100) : 0;
$diskTotalGB      = $diskTotal > 0 ? round($diskTotal / 1024 / 1024 / 1024) : 0;
$diskUsedGB       = round($diskUsed / 1024 / 1024 / 1024);
// Disk büyüme trendi (cron'un günlük .disk_history dosyasından): net GB/gün →
// hafta ve %80'e kalan süre projeksiyonu. TRAILING 30 GÜN penceresi: tek
// seferlik temizlik (cache silme) tüm geçmişi bozmasın diye — eski nokta 30
// günde pencereden düşer, projeksiyon taze veriyle toparlar. Net eğim
// temizlikleri hesaba katar: disk net büyümüyorsa (temizlikler dengeliyorsa)
// %80'e gitmiyor demektir, projeksiyon gösterilmez.
$diskGrow = '';
$dhFile = $HOME_DIR . '/.disk_history';
if ($diskTotalGB > 0 && is_readable($dhFile)) {
    $pts = [];
    foreach (@file($dhFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [] as $ln) {
        $p = preg_split('/\s+/', trim($ln));
        if (count($p) === 2 && ($ts = strtotime($p[0])) && is_numeric($p[1])) $pts[] = [$ts, (int)$p[1]];
    }
    if (count($pts) >= 2) {
        $tLast = $pts[count($pts) - 1][0];
        $cutoff = $tLast - 30 * 86400;                  // son 30 gün
        $win = array_values(array_filter($pts, fn($p) => $p[0] >= $cutoff));
        if (count($win) >= 2) {
            [$t0, $u0] = $win[0];
            [$t1, $u1] = $win[count($win) - 1];
            $days = ($t1 - $t0) / 86400;
            if ($days >= 2 && $u1 > $u0) {              // sadece NET büyümede projeksiyon
                $perWeek = ($u1 - $u0) / $days * 7;
                $diskGrow = '+' . round($perWeek, 1) . ' GB/wk';
                $target80 = $diskTotalGB * 0.8;
                if ($u1 < $target80) {
                    $weeksTo80 = ($target80 - $u1) / $perWeek;
                    $diskGrow .= ' · 80% in ' . ($weeksTo80 < 1 ? '<1wk' : ($weeksTo80 >= 8 ? round($weeksTo80 / 4.3) . 'mo' : round($weeksTo80) . 'wk'));
                }
            }
        }
    }
}

// ── Uptime ────────────────────────────────────────────────────
$uptime_text = @file_get_contents('/proc/uptime');
$uptime      = $uptime_text ? (int)explode(' ', $uptime_text)[0] : 0;
$days        = floor($uptime / 86400);
$hours       = str_pad(floor(($uptime % 86400) / 3600), 2, '0', STR_PAD_LEFT);
$mins        = str_pad(floor(($uptime % 3600) / 60),    2, '0', STR_PAD_LEFT);
$secs        = str_pad($uptime % 60,                     2, '0', STR_PAD_LEFT);
$uptimeFormatted = "{$days} Days {$hours}:{$mins}:{$secs}";

// ── Listening Ports ───────────────────────────────────────────
function getListeningPorts() {
    $ports = [];
    foreach (['/proc/net/tcp', '/proc/net/tcp6'] as $f) {
        $lines = @file($f);
        if (!$lines) continue;
        foreach ($lines as $i => $line) {
            if ($i === 0) continue;
            $parts = preg_split('/\s+/', trim($line));
            if (!isset($parts[3]) || $parts[3] !== '0A') continue;
            $addr = explode(':', $parts[1]);
            if (isset($addr[1])) $ports[] = hexdec($addr[1]);
        }
    }
    return array_unique($ports);
}
function getUdpPorts() {
    $ports = [];
    foreach (['/proc/net/udp', '/proc/net/udp6'] as $f) {
        $lines = @file($f);
        if (!$lines) continue;
        foreach ($lines as $i => $line) {
            if ($i === 0) continue;
            $parts = preg_split('/\s+/', trim($line));
            if (!isset($parts[1])) continue;
            $addr = explode(':', $parts[1]);
            if (isset($addr[1])) $ports[] = hexdec($addr[1]);
        }
    }
    return array_unique($ports);
}
$listeningPorts = getListeningPorts();
$udpPorts       = getUdpPorts();
function isListening($port, $ports) { return in_array($port, $ports); }

// ── Response Time ─────────────────────────────────────────────
function measureWebResponseTime() {
    $ctx = stream_context_create(['http' => ['timeout' => 3, 'follow_location' => false, 'ignore_errors' => true]]);
    $t = microtime(true);
    @file_get_contents('http://127.0.0.1/', false, $ctx);
    return max(1, round((microtime(true) - $t) * 1000));
}
function measureTcpResponseTime($host, $port, $readBytes = 0) {
    $t = microtime(true);
    $fp = @fsockopen($host, $port, $e, $s, 2);
    if (!$fp) return null;
    if ($readBytes > 0) { stream_set_timeout($fp, 2); @fread($fp, $readBytes); }
    $ms = round((microtime(true) - $t) * 1000);
    fclose($fp);
    return max(1, $ms);
}
$webResponseTime   = measureWebResponseTime();
$mysqlResponseTime = measureTcpResponseTime('127.0.0.1', 3306, 4);
function rtCol($ms) {
    if ($ms === null) return 'var(--accent)';
    if ($ms >= 100)   return 'var(--danger)';
    if ($ms >= 30)    return 'var(--warn)';
    return 'var(--accent)';
}

// ── SSL ───────────────────────────────────────────────────────
$sslDaysLeft = null; $sslExpiry = null;
$sslCache    = sys_get_temp_dir() . '/az_ssl_cache.json';
if (file_exists($sslCache) && (time() - filemtime($sslCache)) < 21600) {
    $cached      = json_decode(@file_get_contents($sslCache), true);
    $sslDaysLeft = $cached['days']   ?? null;
    $sslExpiry   = $cached['expiry'] ?? null;
} else {
    $ctx = stream_context_create(['ssl' => ['capture_peer_cert' => true, 'verify_peer' => false, 'verify_peer_name' => false]]);
    $fp  = @stream_socket_client('ssl://' . gethostname() . ':2087', $e, $s, 5, STREAM_CLIENT_CONNECT, $ctx);
    if ($fp) {
        $cert = stream_context_get_params($fp)['options']['ssl']['peer_certificate'];
        $info = openssl_x509_parse($cert); fclose($fp);
        if (isset($info['validTo_time_t'])) {
            $sslExpiry   = date('Y-m-d', $info['validTo_time_t']);
            $sslDaysLeft = (int)(($info['validTo_time_t'] - time()) / 86400);
            @file_put_contents($sslCache, json_encode(['days' => $sslDaysLeft, 'expiry' => $sslExpiry]));
        }
    }
}

// ── Helpers ───────────────────────────────────────────────────
function portOpen($host, $p, $timeout = 1) {
    $fp = @fsockopen($host, $p, $e, $s, $timeout);
    if ($fp) { fclose($fp); return true; }
    return false;
}
function anyExists($paths) {
    foreach ((array)$paths as $p) { if (@file_exists($p)) return true; }
    return false;
}

// Root feed önce, fallback port kontrolü
function svcCheck($label, $whmName, $port, $lp, $whmSvcs, $whmOk) {
    if ($whmOk && $whmName) {
        $status = whmSvcOk($whmName, $whmSvcs);
        if ($status !== null) {
            $lst  = $port ? isListening($port, $lp) : null;
            $note = $status ? 'running' : 'stopped';
            if ($port && $status) $note .= $lst ? ' · listening' : ' · not listening';
            return ['label' => $label, 'ok' => $status, 'type' => 'check', 'note' => $note, 'source' => 'root'];
        }
    }
    if ($port) {
        $ok  = portOpen('127.0.0.1', $port);
        $lst = isListening($port, $lp);
        $n   = $ok ? 'responding' . ($lst ? ' · listening' : '') : 'no response';
        return ['label' => $label, 'ok' => $ok, 'type' => 'check', 'note' => $n, 'source' => 'port'];
    }
    return ['label' => $label, 'ok' => false, 'type' => 'check', 'note' => 'unknown', 'source' => 'none'];
}
function chkPort($label, $port, $lp) {
    $ok  = portOpen('127.0.0.1', $port);
    $lst = isListening($port, $lp);
    return ['label' => $label, 'ok' => $ok, 'type' => 'check', 'source' => 'port',
            'note'  => $ok ? 'responding' . ($lst ? ' · listening' : '') : 'no response'];
}

// ════════════════════════════════════════════════════════════════
// WEB
// LiteSpeed: binary → sadece tür tespiti (LiteSpeed mi Apache mi)
// Çalışıp çalışmadığı → WHM httpd servisi
// ════════════════════════════════════════════════════════════════
$isLiteSpeed = anyExists(['/usr/local/lsws/bin/lshttpd']);
if ($rootFresh && isset($procSec['websrv'])) $isLiteSpeed = ($procSec['websrv'] === 'litespeed');
$webServerLabel = $isLiteSpeed ? 'LiteSpeed' : 'Apache';

// httpd servisinin durumu API'den
$httpdStatus = whmSvcOk('httpd', $whmServices);
$http443     = portOpen('127.0.0.1', 443);
$http80      = portOpen('127.0.0.1', 80);

// API yoksa port kontrolüne düş
if ($httpdStatus === null) {
    $httpdStatus = $http80 || $http443;
}

$webChecks = [
    ['label' => $webServerLabel, 'ok' => $httpdStatus, 'type' => 'check', 'source' => $whmApiOk ? $svcSrc : 'port',
     'note'  => $httpdStatus ? 'running' : 'stopped'],
    ['label' => 'HTTPS (443)', 'ok' => $http443, 'type' => 'check', 'source' => 'port',
     'note'  => $http443 ? 'responding' . (isListening(443, $listeningPorts) ? ' · listening' : '') : 'no response'],
    ['label' => 'HTTP (80)', 'ok' => $http80, 'type' => 'check', 'source' => 'port',
     'note'  => $http80 ? 'responding' . (isListening(80, $listeningPorts) ? ' · listening' : '') : 'no response'],
    svcCheck('WHM (2087)',    'cpsrvd', 2087, $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('cPanel (2083)', 'cpsrvd', 2083, $listeningPorts, $whmServices, $whmApiOk),
];
$webOk     = array_sum(array_column($webChecks, 'ok'));
$webTotal  = count($webChecks);
$webStatus = $webOk === $webTotal ? 'operational' : ($webOk > 0 ? 'degraded' : 'offline');

// ════════════════════════════════════════════════════════════════
// MAIL
// ════════════════════════════════════════════════════════════════
$mailChecks = [
    svcCheck('SMTP (25)',          'exim',   25,  $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('SMTP Submit. (587)', 'exim',  587,  $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('SMTPS (465)',        'exim',  465,  $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('POP3 (110)',         'pop',   110,  $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('POP3S (995)',        'pop',   995,  $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('IMAP (143)',         'imap',  143,  $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('IMAPS (993)',        'imap',  993,  $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('Webmail (2095)',     'cpsrvd', 2095, $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('Webmail SSL (2096)', 'cpsrvd', 2096, $listeningPorts, $whmServices, $whmApiOk),
];
// Mail queue ve toplam lsphp: System Info şeridinde kendi kartları (root snapshot'tan)
$mailQ = ($rootFresh && isset($procSec['mailq']) && is_numeric($procSec['mailq']) && (int)$procSec['mailq'] >= 0)
       ? (int)$procSec['mailq'] : null;
$lsphpTotal = ($rootFresh && isset($procSec['lsphp_total']) && is_numeric($procSec['lsphp_total']))
       ? (int)$procSec['lsphp_total'] : null;
$lsphpIdle = ($rootFresh && isset($procSec['lsphp_idle']) && is_numeric($procSec['lsphp_idle']))
       ? (int)$procSec['lsphp_idle'] : null;
// D-state: diskte bloklanan süreç sayısı — load'a girer ama CPU'da görünmez
$dState = ($rootFresh && isset($procSec['dstate']) && is_numeric($procSec['dstate']))
       ? (int)$procSec['dstate'] : null;
// R-state: koşan süreç sayısı. Load anatomisi: load ≈ R + D. CPU meta'da
// "run N / blk M" olarak; load ile toplam arasındaki fark LVE frenlemesidir
// (CloudLinux'ta throttle edilen görevler load'a girer ama R/D'de görünmez).
$rState = ($rootFresh && isset($procSec['rstate']) && is_numeric($procSec['rstate']))
       ? (int)$procSec['rstate'] : null;
// Inode kullanımı (%): disk alanı boş olsa da inode tükenince sunucu çöker.
// Milyonlarca küçük dosya (cache vb) tüketir — LiteSpeed cache olayının erken
// sinyali. Eşik %90 kritik / %80 uyarı. PHP inode okuyamaz, root df -i verir.
$inodePct = ($rootFresh && isset($procSec['inode_pct']) && is_numeric($procSec['inode_pct']))
       ? (int)$procSec['inode_pct'] : null;
$inodeCol = $inodePct === null ? 'var(--hint)'
          : ($inodePct >= 90 ? 'var(--danger)' : ($inodePct >= 80 ? 'var(--warn)' : 'var(--hint)'));
// RAID durumu (cron /proc/mdstat'tan): degraded = disk sessizce ölmüş (RAID5'te
// ikincisi ölene kadar fark edilmez — asıl izlenmesi gereken bu), resync =
// rebuild/eşitleme sürüyor. Dizi yoksa (RAID değil) $raidState null.
$raidState = null; $raidTxt = ''; $raidCol = 'var(--hint)';
if ($rootFresh && isset($procSec['raid'])) {
    $rp = preg_split('/\s+/', trim($procSec['raid']), 2);
    $raidState = $rp[0]; $rdet = $rp[1] ?? '';
    if ($raidState === 'degraded')    { $raidCol = 'var(--danger)'; $raidTxt = 'RAID degraded ' . $rdet; }
    elseif ($raidState === 'resync')  { $raidCol = 'var(--warn)';   $raidTxt = 'RAID rebuild ' . $rdet; }
    else                              { $raidCol = 'var(--hint)';   $raidTxt = 'RAID ' . $rdet; }
}
// RAID mismatch — son scrub'da uyuşmayan blok sayısı (>0 = veri tutarsız).
$raidMismatch = ($rootFresh && isset($procSec['raid_mismatch']) && is_numeric($procSec['raid_mismatch']))
       ? (int)$procSec['raid_mismatch'] : 0;
// SMART ön-arıza — alarm-only: sadece sorunlu disk görünür (smartd sağlıklıyı
// mailliyor). Her satır "sdb 24 realloc" → "SMART sdb: 24 realloc" (kırmızı).
$smartTxt = ''; $smartMsg = '';
if ($rootFresh && $smartBad) {
    $sp = [];
    foreach ($smartBad as $sb) {
        $q = preg_split('/\s+/', $sb, 2);
        $sp[] = 'SMART ' . htmlspecialchars($q[0]) . ': ' . htmlspecialchars($q[1] ?? '?');
    }
    $smartTxt = implode(' &middot; ', $sp);              // meta (HTML)
    $smartMsg = 'Disk pre-failure — ' . implode(', ', $smartBad) . '; plan replacement'; // log (düz)
}
// O an sorgu işleyen MySQL thread'i (5sn+ sorgu tablosunun görmediği "kısa ama çok" senaryosu)
$mysqlThr = ($rootFresh && isset($procSec['mysql_thr']) && is_numeric($procSec['mysql_thr']))
       ? (int)$procSec['mysql_thr'] : null;
// ps etime → saniye: [[gün-]saat:]dk:sn
function etimeSec($t) {
    if (!preg_match('/^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/', trim((string)$t), $m)) return null;
    return (int)$m[1] * 86400 + (int)$m[2] * 3600 + (int)$m[3] * 60 + (int)$m[4];
}
// Aktivite çipleri: yoğun arka plan işleri — yük spike'larının olağan şüphelileri.
// Süre birincil olarak cron'un act_* anahtarından gelir (TÜM süreç listesinde
// en eski eşleşen; gerçek pencere süresi). Cron eski sürümse Top-15 CPU
// taramasına düşülür — o değer "o anki görevin yaşı"dır, alt sınırdır
// (pkgacct her hesap için yeniden doğar). Desenler JS'tekiyle senkron.
// wpt/imunify'da minCpu eşiği: kalıcı daemon'ları (sw-engine-fpm havuzu,
// rustbolit --resident) elemek için — eşiksiz desen çipi sonsuza dek yakıyordu.
// Kompakt sayı: 8→"8", 15051→"15k", 1500000→"1.5M". Imunify kapsamı için.
function fmtCount($n) {
    if ($n >= 1000000) return round($n / 1000000, 1) . 'M';
    if ($n >= 1000)    return round($n / 1000) . 'k';
    return (string)(int)$n;
}
// 5. alan: kapsam (dosya sayısı) anahtarı — sadece imunify'da. Çipe "· N files"
// eklenir; küçük N = artımlı/değişen-dosya taraması, büyük N = haftalık tam sweep.
$actDefs = [
    ['backup running',  'act_backup',  '/pkgacct|cpbackup/i',                            0,  null],
    ['system update',   'act_update',  '/upcp|updatenow|dnf (upgrade|update)|yum (upgrade|update)/i', 0, null],
    ['wp-toolkit task', 'act_wpt',     '/wordpress-toolkit|wp-toolkit/i',               15, null],
    ['imunify scan',    'act_imunify', '/im360\.run|aibolit|rustbolit/i',               15, 'act_imunify_n'],
];
$actChips = []; $acts = []; $actImunifyN = null;
foreach ($actDefs as [$aLbl, $aKey, $aRe, $aMinCpu, $aScope]) {
    $mx = ($rootFresh && isset($procSec[$aKey]) && is_numeric($procSec[$aKey])) ? (int)$procSec[$aKey] : null;
    if ($mx === null) {
        foreach ($procCpu as $p) {
            if ((float)$p[2] < $aMinCpu) continue;
            if (!preg_match($aRe, $p[1] . ' ' . $p[5])) continue;
            $s = etimeSec($p[4]);
            if ($s !== null && ($mx === null || $s > $mx)) $mx = $s;
        }
    }
    // Imunify: artımlı taramalar SÜREKLI koşar (her değişen dosya) → çip hep
    // "1m" gösterir ve Event log'a geçiş düşmez (hiç sönmez). Bu gürültüyü
    // gizle; çipi SADECE gerçek hesap taramasında göster (path=/home/hesap →
    // act_imunify_p hesap adı; artımlı → "incremental"). Böylece çip anlamlı
    // olur ve haftalık sweep başlayınca Event log'a "started/finished" düşer.
    $imIncr = ($aKey === 'act_imunify' && ($procSec['act_imunify_p'] ?? '') === 'incremental');
    $acts[] = $imIncr ? null : $mx;
    if ($mx !== null && !$imIncr) {
        $chip = $aLbl . ' · ' . fmtAgeShort($mx);
        if ($aKey === 'act_imunify') {
            if (($procSec['act_imunify_p'] ?? '') !== '' && $procSec['act_imunify_p'] !== '-')
                $chip .= ' · ' . htmlspecialchars($procSec['act_imunify_p']); // hesap adı
            if (isset($procSec['act_imunify_n']) && is_numeric($procSec['act_imunify_n']) && (int)$procSec['act_imunify_n'] > 0) {
                $actImunifyN = (int)$procSec['act_imunify_n'];
                $chip .= ' · ' . fmtCount($actImunifyN) . ' files';
            }
        }
        $actChips[] = $chip;
    }
}
// Eşik→renk (metrik kimlik rengi sağlıklıda; sarı/kırmızı override)
// Mail queue eşiği HESAP BAŞINA (taşınabilir): 1/hesap sarı, 3/hesap kırmızı
function mqCol($q, $acct) {
    if ($q === null) return 'var(--muted)';
    $base = ($acct && $acct > 0) ? $acct : 50; // hesap sayısı yoksa makul taban
    return $q >= $base * 3 ? 'var(--danger)' : ($q >= $base * 1 ? 'var(--warn)' : 'var(--accent)');
}
// ÇALIŞAN worker eşiği = ÇEKİRDEK SAYISI standardı: eşzamanlı aktif iş
// sayısı çekirdek sayısını aşınca işler kuyruklanır (load average mantığı).
// Sarı = tüm çekirdekler dolu (n >= cores), Kırmızı = kuyruk 2× (n >= 2*cores).
function lsphpCol($n, $cores) {
    if ($n === null) return 'var(--muted)';
    $c = ($cores && $cores > 0) ? $cores : 1;
    return $n >= $c * 2 ? 'var(--danger)' : ($n >= $c ? 'var(--warn)' : 'var(--accent)');
}
$mailOk     = array_sum(array_column($mailChecks, 'ok'));
$mailTotal  = count($mailChecks);
$mailStatus = $mailOk === $mailTotal ? 'operational' : ($mailOk > 0 ? 'degraded' : 'offline');

// ════════════════════════════════════════════════════════════════
// DNS
// ════════════════════════════════════════════════════════════════
$dnsChecks = [
    svcCheck('DNS TCP (53)', 'named', 53, $listeningPorts, $whmServices, $whmApiOk),
    ['label' => 'DNS UDP (53)', 'ok' => isListening(53, $udpPorts), 'type' => 'check', 'source' => 'proc',
     'note'  => isListening(53, $udpPorts) ? 'listening' : 'not detected'],
];
$dnsOk     = array_sum(array_column($dnsChecks, 'ok'));
$dnsTotal  = count($dnsChecks);
$dnsStatus = $dnsOk === $dnsTotal ? 'operational' : ($dnsOk > 0 ? 'degraded' : 'offline');

// ════════════════════════════════════════════════════════════════
// SECURITY
// ════════════════════════════════════════════════════════════════
// CSF/ModSec/CageFS: root snapshot'ta veri varsa gerçek kontrol,
// yoksa eski davranış (komut kopyalama satırı) korunur.
$csfTesting = ($procSec['csf_testing'] ?? '0') === '1';
$secRoot = [];
$secRoot[] = isset($procSec['csf'])
    ? ['label' => 'CSF firewall', 'ok' => ($procSec['csf'] === 'enabled' && !$csfTesting), 'type' => 'check',
       'source' => 'root', 'note' => $procSec['csf'] . ($csfTesting ? ' · TESTING mode' : '')]
    : ['label' => 'CSF firewall', 'type' => 'cmd', 'cmd' => 'systemctl status csf'];
$msVal = isset($procSec['modsec']) ? trim($procSec['modsec'], " \t\"'") : null; // cPanel değeri tırnaklı yazabiliyor
$secRoot[] = $msVal !== null
    ? ['label' => 'ModSecurity', 'ok' => strcasecmp($msVal, 'on') === 0, 'type' => 'check',
       'source' => 'root', 'note' => 'SecRuleEngine ' . $msVal]
    : ['label' => 'ModSecurity', 'type' => 'cmd', 'cmd' => 'systemctl status httpd'];
$secRoot[] = isset($procSec['cagefs'])
    ? ['label' => 'CageFS', 'ok' => stripos($procSec['cagefs'], 'enabled') !== false, 'type' => 'check',
       'source' => 'root', 'note' => strtolower($procSec['cagefs'])] // cagefsctl "Enabled" der; csf satırıyla ("enabled") tutarlı olsun
    : ['label' => 'CageFS', 'type' => 'cmd', 'cmd' => 'cagefsctl --cagefs-status'];

$secChecks = array_merge([
    svcCheck('Imunify360',   'imunify360', null, $listeningPorts, $whmServices, $whmApiOk),
    svcCheck('LFD',          'lfd',        null, $listeningPorts, $whmServices, $whmApiOk),
], $secRoot);
$secVerifiable = array_filter($secChecks, fn($c) => isset($c['ok']));
$secOk    = array_sum(array_column(array_values($secVerifiable), 'ok'));
$secTotal = count($secVerifiable);
$secStatus = $secTotal > 0
    ? ($secOk === $secTotal ? 'operational' : ($secOk > 0 ? 'degraded' : 'offline'))
    : 'operational';

// ════════════════════════════════════════════════════════════════
// DATABASE
// ════════════════════════════════════════════════════════════════
$mysqlCheck  = svcCheck('MySQL (3306)', 'mysql', 3306, $listeningPorts, $whmServices, $whmApiOk);
if ($rootFresh && isset($procSec['mysql_ping'])) {
    // Root'un gerçek mysqladmin ping'i — socket dosyası çökmüş mysqld'den
    // geride kalabildiği için varlık kontrolünden daha güvenilir
    $mysqlPing = $procSec['mysql_ping'] === '1';
    $dbChecks  = [
        $mysqlCheck,
        ['label' => 'MySQL ping', 'ok' => $mysqlPing, 'type' => 'check', 'source' => 'root',
         'note'  => $mysqlPing ? 'alive' : 'no response'],
    ];
    // ping yetkilidir: cevap yoksa süreç ayakta bile olsa (hung) degraded
    $dbStatus = $mysqlPing ? 'operational' : ($mysqlCheck['ok'] ? 'degraded' : 'offline');
} else {
    $mysqlSocket = anyExists(['/var/lib/mysql/mysql.sock', '/tmp/mysql.sock', '/var/run/mysqld/mysqld.sock']);
    $dbChecks    = [
        $mysqlCheck,
        ['label' => 'MySQL socket', 'ok' => $mysqlSocket, 'type' => 'check', 'source' => 'file',
         'note'  => $mysqlSocket ? 'found' : 'not found'],
    ];
    $dbStatus = ($mysqlCheck['ok'] || $mysqlSocket) ? 'operational' : 'offline';
}
$dbOk     = array_sum(array_column($dbChecks, 'ok'));
$dbTotal  = count($dbChecks);

// ════════════════════════════════════════════════════════════════
// CACHE
// ════════════════════════════════════════════════════════════════
$cacheChecks = [
    chkPort('Redis (6379)',       6379,  $listeningPorts),
    chkPort('Memcached (11211)', 11211,  $listeningPorts),
];
$cacheOk     = array_sum(array_column($cacheChecks, 'ok'));
$cacheTotal  = count($cacheChecks);
$cacheStatus = $cacheOk === $cacheTotal ? 'operational' : ($cacheOk > 0 ? 'degraded' : 'offline');

// ════════════════════════════════════════════════════════════════
// FTP
// ════════════════════════════════════════════════════════════════
$ftpCheck  = svcCheck('FTP service', 'ftpd', 21, $listeningPorts, $whmServices, $whmApiOk);
$ftpListen = isListening(21, $listeningPorts);
$ftpChecks = [
    $ftpCheck,
    ['label' => 'Kernel state', 'ok' => $ftpListen, 'type' => 'check', 'source' => 'proc',
     'note'  => $ftpListen ? 'port bound' : 'not bound'],
];
$ftpOk     = array_sum(array_column($ftpChecks, 'ok'));
$ftpTotal  = count($ftpChecks);
$ftpStatus = $ftpOk === $ftpTotal ? 'operational' : ($ftpOk > 0 ? 'degraded' : 'offline');

// ── Servis yaşları (root snapshot: svcage) ────────────────────
// Ana daemon ne zamandır ayakta? Uzun uptime'lı sunucuda kısa etime =
// beklenmedik restart sinyali. <1 saat → satır notu sarı "restarted X ago",
// değilse "· up 29d 4h". Sadece birincil satırlar etiketlenir (exim×3 gibi
// aynı daemon'ın her port satırına yazmak gürültü olur).
function fmtAge($s) {
    if ($s >= 86400) return floor($s / 86400) . 'd ' . floor(($s % 86400) / 3600) . 'h';
    if ($s >= 3600)  return floor($s / 3600) . 'h ' . floor(($s % 3600) / 60) . 'm';
    return max(1, floor($s / 60)) . 'm';
}
// Sağ sütun için kompakt tek birim ("29d", "5h", "42m") — sabit dar sütuna
// sığsın diye; tam hali (fmtAge) hover tooltip'inde.
function fmtAgeShort($s) {
    if ($s >= 86400) return floor($s / 86400) . 'd';
    if ($s >= 3600)  return floor($s / 3600) . 'h';
    return max(1, floor($s / 60)) . 'm';
}
function tagAge(&$chk, $aliases) {
    global $svcAge, $rootFresh;
    if (!$rootFresh) return;
    $s = null;
    foreach ((array)$aliases as $a) if (isset($svcAge[$a])) $s = max($s ?? 0, $svcAge[$a]);
    if ($s === null) return;
    // Yaş, satırın EN SAĞINDA sabit genişlikte kompakt sütunda ("29d") —
    // sabit genişlik sayesinde kart boyunca dikey hizalanır ve taranabilir.
    // Alarm rengi yok: gece otomatik güncellemeleri düzenli restart üretir,
    // kısa değer ("39m") yakın restart'ı zaten kendiliğinden belli eder.
    $chk['up']  = fmtAge($s);      // tooltip: "29d 5h"
    $chk['upS'] = fmtAgeShort($s); // sütun:   "29d"
}
tagAge($webChecks[0],  ['litespeed', 'lshttpd', 'httpd']);
tagAge($webChecks[3],  ['cpsrvd', 'cpsrvd-dormant']);                 // WHM (2087)
tagAge($mailChecks[0], ['exim']);                                     // SMTP (25)
tagAge($mailChecks[3], ['dovecot']);                                  // POP3 (110) — POP/IMAP daemon'ı
tagAge($dnsChecks[0],  ['named', 'pdns_server']);
tagAge($secChecks[0],  ['imunify360-agen', 'imunify-residen']);       // Imunify360
tagAge($secChecks[1],  ['lfd']);
tagAge($dbChecks[0],   ['mariadbd', 'mysqld']);                       // MySQL (3306)
tagAge($ftpChecks[0],  ['pure-ftpd', 'proftpd']);
tagAge($cacheChecks[0], ['redis-server']);
tagAge($cacheChecks[1], ['memcached']);
// Sürümler kimlik satırının ALT SATIRINDA yaşla birlikte gösterilir
// ("6.3.5 · up 55m"). $full=false: etiket zaten ürün adıysa sadece numara;
// true: "Exim 4.99.4" gibi tam ad (etiket port adıysa ürünü de söyler).
function tagVer(&$chk, $key, $full = true) {
    global $svcVer;
    if (!isset($svcVer[$key])) return;
    $chk['ver']  = $full ? $svcVer[$key] : preg_replace('/^\S+\s*/', '', $svcVer[$key]);
    $chk['verT'] = $svcVer[$key]; // hover: her zaman tam ad
}
tagVer($webChecks[0],   'web', false);      // LiteSpeed → "6.3.5"
tagVer($webChecks[3],   'cpanel');          // WHM (2087) → "cPanel 11.136.0.29"
tagVer($mailChecks[0],  'exim');            // SMTP (25) → "Exim 4.99.4"
tagVer($mailChecks[3],  'dovecot');         // POP3 (110) → "Dovecot 2.4.4"
tagVer($dnsChecks[0],   'named');           // DNS TCP → "BIND 9.11.36"
tagVer($secChecks[0],   'imunify', false);  // Imunify360 → "8.13.6"
tagVer($secChecks[1],   'lfd', false);      // LFD → "v16.20" (csf paketiyle aynı sürüm)
tagVer($secChecks[2],   'csf', false);      // CSF firewall → "v16.20"
tagVer($secChecks[3],   'modsec', false);   // ModSecurity → "2.9.7" (EA4 rpm)
tagVer($secChecks[4],   'cagefs', false);   // CageFS → "7.5.13"
tagVer($ftpChecks[0],   'ftp', false);      // FTP → "1.0.52" (dar 4'lü kart; tam ad "Pure-FTPd 1.0.52" hover'da)
tagVer($dbChecks[0],    'db', false);       // MySQL → "10.11.18" (dar 4'lü kart; tam ad "MariaDB 10.11.18" hover'da)
tagVer($cacheChecks[0], 'redis', false);
tagVer($cacheChecks[1], 'memcached', false);

// ── Birleşik sağlık modeli ────────────────────────────────────
// Tepe durumu SADECE servis kartlarına değil TÜM metrik/kontrollere
// bakar: her kontrol bir seviye (ok/warn/err) + kısa etiket üretir,
// tepe EN KÖTÜ seviyeyi yansıtır ve sorunları yanına listeler. Metrik
// kartları da kendi seviyelerine (alt-sinyaller dahil) göre renklenir —
// sorun varken kart yeşil kalmaz. Tümü sunucu-render (CSF mail eki dahil).
// Eşikler mevcut kart/meta/event-log eşikleriyle birebir aynı (tek kaynak).
function hLvlHi($v, $hi, $cr) { return $v >= $cr ? 'err' : ($v >= $hi ? 'warn' : 'ok'); }
function hWorst(...$ls)       { $o = ['ok'=>0,'warn'=>1,'err'=>2]; $m='ok'; foreach ($ls as $l) if (($o[$l] ?? 0) > $o[$m]) $m=$l; return $m; }
function hCol($lvl, $ok)      { return $lvl==='err' ? 'var(--danger)' : ($lvl==='warn' ? 'var(--warn)' : $ok); }
function cardBorderCss($col)  { return ($col==='var(--danger)' || $col==='var(--warn)') ? ';border-color:'.$col : ''; }

$mqBase    = ($whmAcctCount && $whmAcctCount > 0) ? $whmAcctCount : 50;
$loadRatio = $load1 / max($coreCount, 1);
$health = [ // her giriş: [seviye, tepe-detayında görünecek kısa etiket]
    'load'     => [$loadRatio>=2.0?'err':($loadRatio>=1.0?'warn':'ok'),                          'Load '.number_format($load1,2)],
    'cpu'      => [hLvlHi($cpuUsage,80,90),                                                       'CPU '.$cpuUsage.'%'],
    'ram'      => [hLvlHi($memUsagePercent,70,85),                                                'RAM '.$memUsagePercent.'%'],
    'disk'     => [hLvlHi($diskUsagePercent,75,90),                                               'Disk '.$diskUsagePercent.'%'],
    'iow'      => [hLvlHi($ioWait,8,15),                                                          'IO wait '.$ioWait.'%'],
    'net'      => [$netSat===null?'ok':hLvlHi($netSat,70,90),                                     'Network '.$netSat.'%'],
    'inode'    => [$inodePct===null?'ok':hLvlHi($inodePct,80,90),                                 'inode '.$inodePct.'%'],
    'swap'     => [hLvlHi($swapPct,10,50),                                                        'swap '.$swapPct.'%'],
    'shmem'    => [hLvlHi($shmemPct,40,55),                                                       'shmem '.$shmemPct.'%'],
    'raid'     => [$raidState==='degraded'?'err':($raidState==='resync'?'warn':'ok'),             $raidTxt!==''?$raidTxt:'RAID issue'],
    'mismatch' => [$raidMismatch>0?'warn':'ok',                                                   $raidMismatch.' RAID mismatch'],
    'smart'    => [$smartMsg!==''?'err':'ok',                                                     'SMART fault'],
    'ssl'      => [$sslDaysLeft===null?'ok':($sslDaysLeft<=7?'err':($sslDaysLeft<=30?'warn':'ok')), 'SSL '.$sslDaysLeft.'d'],
    'webrt'    => [$webResponseTime===null?'ok':hLvlHi($webResponseTime,30,100),                  'Web '.$webResponseTime.'ms'],
    'dbrt'     => [$mysqlResponseTime===null?'ok':hLvlHi($mysqlResponseTime,30,100),              'MySQL '.$mysqlResponseTime.'ms'],
    'mysqlthr' => [$mysqlThr===null?'ok':hLvlHi($mysqlThr,$coreCount,$coreCount*2),               'MySQL '.$mysqlThr.' running'],
    'mailq'    => [$mailQ===null?'ok':($mailQ>=$mqBase*3?'err':($mailQ>=$mqBase?'warn':'ok')),    'Mail queue '.$mailQ],
    'wrk'      => [$lsphpTotal===null?'ok':($lsphpTotal>=$coreCount*2?'err':($lsphpTotal>=$coreCount?'warn':'ok')), $lsphpTotal.' PHP workers'],
    'snap'     => [($procAge===null||$procAge>180)?'warn':'ok',                                   'Snapshot stale'],
];
foreach (['Web'=>$webStatus,'Mail'=>$mailStatus,'DNS'=>$dnsStatus,'Security'=>$secStatus,'Database'=>$dbStatus,'Cache'=>$cacheStatus,'FTP'=>$ftpStatus] as $n=>$st) {
    $health['svc_'.strtolower($n)] = [$st==='offline'?'err':($st==='degraded'?'warn':'ok'), $n.' '.$st];
}
$errItems = []; $warnItems = [];
foreach ($health as $h) {
    if     ($h[0]==='err')  $errItems[]  = $h[1];
    elseif ($h[0]==='warn') $warnItems[] = $h[1];
}
if     ($errItems)  { $overallStatus = 'Issues detected';        $overallColorCss = 'var(--danger)'; $overallShort = 'Issues'; }
elseif ($warnItems) { $overallStatus = 'Degraded';               $overallColorCss = 'var(--warn)';   $overallShort = 'Degraded'; }
else                { $overallStatus = 'All systems operational'; $overallColorCss = 'var(--ok)';     $overallShort = 'OK'; }
$allIssues     = array_merge($errItems, $warnItems); // err'ler önce (kırmızı öncelikli)
$overallDetail = '';
if ($allIssues) {
    $overallDetail = implode(' · ', array_slice($allIssues, 0, 5));
    if (count($allIssues) > 5) $overallDetail .= ' · +'.(count($allIssues)-5);
}
// Metrik kartı renkleri — kendi metriği + ilgili alt-sinyallerin en kötüsü.
$netRxCol    = scolCss((int)$netRxSat, 70, 90, 'var(--accent)'); // Network IN/OUT değer+spark rengi
$netTxCol    = scolCss((int)$netTxSat, 70, 90, 'var(--accent)');
$mysqlThrCol = $mysqlThr === null ? 'var(--hint)' : scolCss($mysqlThr, $coreCount, $coreCount*2, 'var(--hint)'); // Threads_running
$cpuCardCol  = hCol($health['cpu'][0], 'var(--c-cpu)');
$ramCardCol  = hCol(hWorst($health['ram'][0],  $health['swap'][0],  $health['shmem'][0]), 'var(--c-ram)');
$diskCardCol = hCol(hWorst($health['disk'][0], $health['inode'][0], $health['raid'][0], $health['mismatch'][0], $health['smart'][0]), 'var(--c-disk)');
$iowCardCol  = hCol($health['iow'][0], 'var(--c-iow)');

$sslColorCss = 'var(--accent)';
if ($sslDaysLeft !== null) {
    if ($sslDaysLeft <= 7)      $sslColorCss = 'var(--danger)';
    elseif ($sslDaysLeft <= 30) $sslColorCss = 'var(--warn)';
}


// ── Sparkline geçmişi (cron'dan) ──────────────────────────────
// Cron her dakika load/cpu/ram/disk/iowait değerlerini
// /home/ayzeta/.metrics_history dosyasına yazar (son 30 dk).
// Sayfa bu geçmişle grafikleri açılışta doldurur; mail ekinde de
// spike'a giden trend görünür.
$histSeed = ['t'=>[], 'l1'=>[], 'l5'=>[], 'l15'=>[], 'cpu'=>[], 'ram'=>[], 'disk'=>[], 'iow'=>[], 'wrk'=>[], 'rx'=>[], 'tx'=>[], 'mq'=>[], 'top'=>[]];
$histFile = $HOME_DIR . '/.metrics_history';
if (is_readable($histFile)) {
    foreach (@file($histFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [] as $ln) {
        $p = preg_split('/\s+/', trim($ln));
        if (count($p) >= 8) {
            $histSeed['t'][]    = $p[0];
            $histSeed['l1'][]   = (float)$p[1];
            $histSeed['l5'][]   = (float)$p[2];
            $histSeed['l15'][]  = (float)$p[3];
            $histSeed['cpu'][]  = (int)$p[4];
            $histSeed['ram'][]  = (int)$p[5];
            $histSeed['disk'][] = (int)$p[6];
            $histSeed['iow'][]  = (int)$p[7];
            $histSeed['wrk'][]  = isset($p[8]) ? (int)$p[8] : 0; // eski satırlarda yok
            $histSeed['rx'][]   = isset($p[9]) ? (int)$p[9] : 0;
            $histSeed['tx'][]   = isset($p[10]) ? (int)$p[10] : 0;
            $histSeed['mq'][]   = isset($p[11]) ? (int)$p[11] : 0;
            $histSeed['top'][]  = (isset($p[12]) && $p[12] !== '-') ? $p[12] : ''; // "comm:cpu" — eski satırlarda yok
        }
    }
    // Pencere NOKTA SAYISIYLA değil ZAMANLA tanımlı: son 30 dakika.
    // Böylece yenileme ile canlı görünüm aynı pencereyi gösterir ve
    // "30 dk" gerçekten 30 dk olur. Gece yarısı sarması modulo ile çözülür.
    $nowS = (int)date('H') * 3600 + (int)date('i') * 60 + (int)date('s');
    $cnt  = count($histSeed['t']);
    $keep = $cnt;
    for ($i = 0; $i < $cnt; $i++) {
        $tp   = explode(':', $histSeed['t'][$i]);
        $ageS = ($nowS - ((int)$tp[0] * 3600 + (int)$tp[1] * 60) + 86400) % 86400;
        if ($ageS <= 1830) { $keep = $i; break; }   // 30 dk + 30 sn tolerans
    }
    if ($keep > 0) foreach ($histSeed as $k => $v) $histSeed[$k] = array_values(array_slice($v, $keep));
}

// ── Event log tohumu ──────────────────────────────────────────
// Geçmişe canlıdakiyle aynı eşikleri uygular; seviye geçişlerinde
// kayıt üretir. 1 dakikalık gerçek spike'lar ANINDA loglanır;
// eşik kenarı çırpınmasını süre filtresi değil HİSTEREZİS engeller:
// seviyeye giriş normal eşikten, çıkış %10 altından.
function lvlHyst($v, $cr, $hi, $cur) {
    if ($v >= $cr) return 'err';
    if ($cur === 'err' && $v >= $cr * 0.9) return 'err';
    if ($v >= $hi) return 'warn';
    if (($cur === 'err' || $cur === 'warn') && $v >= $hi * 0.9) return 'warn';
    return 'ok';
}
$seedLogs = [];
$seedLvl  = ['load' => 'ok', 'cpu' => 'ok', 'ram' => 'ok', 'iow' => 'ok'];
if (!empty($histSeed['t'])) {
    $lvl = ['load' => 'ok', 'cpu' => 'ok', 'ram' => 'ok', 'iow' => 'ok'];
    $n = count($histSeed['t']);
    for ($i = 0; $i < $n; $i++) {
        $ts = $histSeed['t'][$i];
        $l1v = $histSeed['l1'][$i];
        // Şüpheli iliştirme: aynı history satırındaki top process ("comm:cpu").
        // Metrikle aynı cron koşusunda yazıldığı için zaman uyumu birebir —
        // yük uyarısı kendini açıklar ("— top: pigz 72%"). RAM'e uygulanmaz
        // (top-CPU süreci RAM spike'ının faili olmayabilir, yanıltır).
        $sfx = '';
        if (($histSeed['top'][$i] ?? '') !== '' && strpos($histSeed['top'][$i], ':') !== false) {
            [$tn, $tc] = explode(':', $histSeed['top'][$i], 2);
            $tn  = preg_replace('/[^A-Za-z0-9_.\-]/', '', $tn);
            if ($tn !== '') $sfx = ' — top: ' . str_replace('_', ' ', $tn) . ' ' . (int)$tc . '%';
        }
        $chk = [
            'load' => [$l1v / max($coreCount, 1), 2.0, 1.0,
                       'High load: ' . number_format($l1v, 2) . ' (1m)' . $sfx,
                       'Load elevated: ' . number_format($l1v, 2) . ' (1m)' . $sfx,
                       'Load back to normal: ' . number_format($l1v, 2)],
            'cpu'  => [$histSeed['cpu'][$i], 90, 80,
                       'CPU critical: ' . $histSeed['cpu'][$i] . '%' . $sfx,
                       'CPU high: ' . $histSeed['cpu'][$i] . '%' . $sfx,
                       'CPU back to normal: ' . $histSeed['cpu'][$i] . '%'],
            'ram'  => [$histSeed['ram'][$i], 85, 70,
                       'RAM critical: ' . $histSeed['ram'][$i] . '%',
                       'RAM high: ' . $histSeed['ram'][$i] . '%',
                       'RAM back to normal: ' . $histSeed['ram'][$i] . '%'],
            'iow'  => [$histSeed['iow'][$i], 15, 8,
                       'IO Wait critical: ' . $histSeed['iow'][$i] . '%' . $sfx,
                       'IO Wait high: ' . $histSeed['iow'][$i] . '%' . $sfx,
                       'IO Wait back to normal: ' . $histSeed['iow'][$i] . '%'],
        ];
        foreach ($chk as $k => [$v, $cr, $hi, $mErr, $mWarn, $mOk]) {
            $new = lvlHyst($v, $cr, $hi, $lvl[$k]);
            if ($new === $lvl[$k]) continue;
            if ($new === 'err')          $seedLogs[] = ['type' => 'err',  'msg' => $mErr,  'ts' => $ts];
            elseif ($new === 'warn')     $seedLogs[] = ['type' => 'warn', 'msg' => $mWarn, 'ts' => $ts];
            elseif ($lvl[$k] !== 'ok')   $seedLogs[] = ['type' => 'ok',   'msg' => $mOk,   'ts' => $ts];
            $lvl[$k] = $new;
        }
    }
    $seedLogs = array_slice($seedLogs, -30);
    $seedLvl  = $lvl;
}

// Snapshot tazeliği — sistemin kendi kendini izlemesi: cron ölürse
// bu da Event log'a düşer (mail ekinde de görünür), köşedeki STALE
// etiketiyle sınırlı kalmaz.
$seedLvl['snap'] = 'ok';
if ($procAge === null || $procAge > 180) {
    $seedLvl['snap'] = 'err';
    $seedLogs[] = ['type' => 'err',
        'msg'  => $procAge === null
                ? 'Root snapshot missing — cron down?'
                : 'Root snapshot stale (' . $procAge . 's) — cron down?',
        'ts'   => date('H:i')];
}

// Swap kullanımı — RAM baskısının en erken habercisi. Eşik ORANSAL (swap'ın
// %'si): >=%50 kritik, >=%10 uyarı. Düz MB farklı swap boyutlarında yanıltırdı.
$seedLvl['swap'] = 'ok';
if ($swapPct >= 50) {
    $seedLvl['swap'] = 'err';
    $seedLogs[] = ['type' => 'err', 'msg' => 'Swap heavily in use: ' . $swapUsedGB . ' GB (' . $swapPct . '%)', 'ts' => date('H:i')];
} elseif ($swapPct >= 10) {
    $seedLvl['swap'] = 'warn';
    $seedLogs[] = ['type' => 'warn', 'msg' => 'Swap in use: ' . $swapUsedGB . ' GB (' . $swapPct . '%)', 'ts' => date('H:i')];
}
// Shmem — opcache/tmpfs kaçağının erken sinyali. Eşik RAM'in %'si (taşınabilir).
$seedLvl['shmem'] = 'ok';
if ($shmemPct >= 55) {
    $seedLvl['shmem'] = 'err';
    $seedLogs[] = ['type' => 'err', 'msg' => 'Shared memory very high: ' . $shmemGB . ' GB (' . $shmemPct . '% of RAM)', 'ts' => date('H:i')];
} elseif ($shmemPct >= 40) {
    $seedLvl['shmem'] = 'warn';
    $seedLogs[] = ['type' => 'warn', 'msg' => 'Shared memory elevated: ' . $shmemGB . ' GB (' . $shmemPct . '% of RAM)', 'ts' => date('H:i')];
}
// Inode — disk alanı boşken bile tükenirse sunucu çöker. Eşik %90/%80.
$seedLvl['inode'] = 'ok';
if ($inodePct !== null && $inodePct >= 90) {
    $seedLvl['inode'] = 'err';
    $seedLogs[] = ['type' => 'err', 'msg' => 'Inodes critically high: ' . $inodePct . '% (disk may fail despite free space)', 'ts' => date('H:i')];
} elseif ($inodePct !== null && $inodePct >= 80) {
    $seedLvl['inode'] = 'warn';
    $seedLogs[] = ['type' => 'warn', 'msg' => 'Inode usage high: ' . $inodePct . '%', 'ts' => date('H:i')];
}
// RAID — degraded = disk sessizce düşmüş (acil, ikincisi ölmeden değiştir).
$seedLvl['raid'] = 'ok';
if ($raidState === 'degraded') {
    $seedLvl['raid'] = 'err';
    $seedLogs[] = ['type' => 'err', 'msg' => $raidTxt . ' — a disk is down; replace before a second fails', 'ts' => date('H:i')];
} elseif ($raidState === 'resync') {
    $seedLvl['raid'] = 'warn';
    $seedLogs[] = ['type' => 'warn', 'msg' => $raidTxt . ' — array rebuilding', 'ts' => date('H:i')];
}
// RAID mismatch — son scrub'da uyuşmayan blok (>0 = veri tutarsızlık uyarısı).
$seedLvl['mismatch'] = 'ok';
if ($raidMismatch > 0) {
    $seedLvl['mismatch'] = 'warn';
    $seedLogs[] = ['type' => 'warn', 'msg' => 'RAID mismatch count: ' . $raidMismatch . ' — data inconsistency found in last scrub', 'ts' => date('H:i')];
}
// SMART — ön-arıza (alarm-only, sadece sorunlu diskte).
$seedLvl['smart'] = 'ok';
if ($smartMsg !== '') {
    $seedLvl['smart'] = 'err';
    $seedLogs[] = ['type' => 'err', 'msg' => $smartMsg, 'ts' => date('H:i')];
}
// Ağ hattı doygunluğu — hattın kendi hızının %'si (warn %70 / err %90).
$seedLvl['net'] = 'ok';
if ($netSat !== null && $netSat >= 90) {
    $seedLvl['net'] = 'err';
    $seedLogs[] = ['type' => 'err', 'msg' => 'Network link saturated: ' . $netSat . '% of line rate', 'ts' => date('H:i')];
} elseif ($netSat !== null && $netSat >= 70) {
    $seedLvl['net'] = 'warn';
    $seedLogs[] = ['type' => 'warn', 'msg' => 'Network link busy: ' . $netSat . '% of line rate', 'ts' => date('H:i')];
}
// Threads_running — DB'de aynı anda koşan sorgu (çekirdeğe oranlı: warn ≥ N / err ≥ 2N).
$seedLvl['mysqlthr'] = 'ok';
if ($mysqlThr !== null && $mysqlThr >= $coreCount * 2) {
    $seedLvl['mysqlthr'] = 'err';
    $seedLogs[] = ['type' => 'err', 'msg' => 'MySQL threads_running very high: ' . $mysqlThr . ' (query pileup)', 'ts' => date('H:i')];
} elseif ($mysqlThr !== null && $mysqlThr >= $coreCount) {
    $seedLvl['mysqlthr'] = 'warn';
    $seedLogs[] = ['type' => 'warn', 'msg' => 'MySQL threads_running elevated: ' . $mysqlThr, 'ts' => date('H:i')];
}

// ════════════════════════════════════════════════════════════════
// ROUTING
// Parametresiz → dashboard HTML
// ?raw=1       → WHMCS XML
// ?json=1      → JSON (JS auto-refresh)
// ════════════════════════════════════════════════════════════════
if (isset($_GET['raw'])) {
    header('Content-Type: text/plain; charset=utf-8');
    echo "<load>{$load15}</load>\n";
    echo "<uptime>{$uptimeFormatted}</uptime>\n";
    exit;
}

if (isset($_GET['json'])) {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode([
        'hostname'          => gethostname(), 'threads' => $coreCount,
        'time'              => date('Y-m-d H:i:s'),
        'overall'           => ['status' => $overallStatus, 'color' => $overallColorCss, 'detail' => $overallDetail],
        'cardCol'           => ['cpu' => $cpuCardCol, 'ram' => $ramCardCol, 'disk' => $diskCardCol, 'iow' => $iowCardCol],
        'load1'             => $load1, 'load5' => $load5, 'load15' => $load15,
        'cpu'               => $cpuUsage, 'ram' => $memUsagePercent,
        'disk'              => $diskUsagePercent, 'iowait' => $ioWait,
        'uptime'            => $uptimeFormatted,
        'memUsedGB'         => $memUsedGB,  'memTotalGB'  => $memTotalGB,
        'swapUsedGB'        => $swapUsedGB, 'swapTotalGB' => $swapTotalGB, 'swapPct' => $swapPct,
        'shmemGB'           => $shmemGB, 'shmemPct' => $shmemPct, 'shmemCol' => $shmemCol,
        'diskUsedGB'        => $diskUsedGB, 'diskTotalGB' => $diskTotalGB, 'diskGrow' => $diskGrow,
        'inodePct'          => $inodePct, 'inodeCol' => $inodeCol,
        'raidTxt'           => $raidTxt ?: null, 'raidCol' => $raidCol, 'raidState' => $raidState, 'raidMismatch' => $raidMismatch, 'smartTxt' => $smartTxt ?: null, 'smartMsg' => $smartMsg ?: null,
        'ioR'               => $ioRead !== null ? fmtBytes($ioRead) : null,
        'ioW'               => $ioWrite !== null ? fmtBytes($ioWrite) : null,
        'dstate'            => $dState, 'rstate' => $rState, 'mysqlThr' => $mysqlThr, 'mysqlThrCol' => $mysqlThrCol, 'vers' => $svcVer ?: null, 'acts' => $acts, 'actImunifyN' => $actImunifyN, 'actImunifyP' => ($procSec['act_imunify_p'] ?? null),
        'rxRate'            => fmtBytes($rxRate), 'txRate' => fmtBytes($txRate), 'rxK' => (int)round(($rxRate ?? 0)/1024), 'txK' => (int)round(($txRate ?? 0)/1024), 'mqRaw' => ($mailQ ?? 0), 'lsphpIdle' => $lsphpIdle,
        'netRxSat'          => $netRxSat, 'netTxSat' => $netTxSat, 'netRxCol' => $netRxCol, 'netTxCol' => $netTxCol,
        'webResponseTime'   => $webResponseTime,
        'mysqlResponseTime' => $mysqlResponseTime,
        'sslExpiry'         => $sslExpiry,  'sslDaysLeft' => $sslDaysLeft,
        'whmApiOk'          => $whmApiOk,
        'acctCount'         => $whmAcctCount, 'mailQ' => $mailQ, 'lsphpTotal' => $lsphpTotal, 'coreCount' => $coreCount, 'acctForMailq' => (($whmAcctCount && $whmAcctCount > 0) ? $whmAcctCount : 50),
        'procCpu'           => $procCpu, 'procRam' => $procRam,
        'procPhp'           => $procPhp, 'procSql' => $procSql, 'procAge' => $procAge, 'snapMtime' => $procMtime, 'diskAcct' => $diskAcct,
        'web'   => ['status' => $webStatus,   'checks' => $webChecks,   'ok' => $webOk,   'total' => $webTotal],
        'mail'  => ['status' => $mailStatus,  'checks' => $mailChecks,  'ok' => $mailOk,  'total' => $mailTotal],
        'dns'   => ['status' => $dnsStatus,   'checks' => $dnsChecks,   'ok' => $dnsOk,   'total' => $dnsTotal],
        'sec'   => ['status' => $secStatus,   'checks' => $secChecks,   'ok' => $secOk,   'total' => $secTotal],
        'db'    => ['status' => $dbStatus,    'checks' => $dbChecks,    'ok' => $dbOk,    'total' => $dbTotal],
        'cache' => ['status' => $cacheStatus, 'checks' => $cacheChecks, 'ok' => $cacheOk, 'total' => $cacheTotal],
        'ftp'   => ['status' => $ftpStatus,   'checks' => $ftpChecks,   'ok' => $ftpOk,   'total' => $ftpTotal],
    ]);
    exit;
}

// Parametresiz veya ?dashboard → HTML
header('Content-Type: text/html; charset=utf-8');

function renderChecks($checks) {
    $out = '';
    foreach ($checks as $c) {
        $type = isset($c['type']) ? $c['type'] : 'check';
        if ($type === 'cmd') {
            $cmd = htmlspecialchars($c['cmd']);
            $out .= '<div class="sub-check">'
                  . '<span class="sub-dot muted"></span>'
                  . '<span class="sub-lbl">' . htmlspecialchars($c['label']) . '</span>'
                  . '<button class="copy-btn" data-cmd="' . $cmd . '" title="Copy">'
                  . '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                  . '</button>'
                  . '<code class="sub-cmd-inline">' . $cmd . '</code>'
                  . '</div>' . "\n";
        } else {
            $note = isset($c['note']) ? htmlspecialchars($c['note']) : ($c['ok'] ? 'ok' : 'fail');
            // Yaş sütunu: HER satırda sabit genişlikte span (yaşı olmayanlarda boş) —
            // böylece notlar ortak hizada biter, yaşlar sağ kenarda dikey taranır.
            $age = '<span class="sub-age"' . (isset($c['up']) ? ' title="up ' . htmlspecialchars($c['up']) . '"' : '') . '>'
                 . (isset($c['upS']) ? htmlspecialchars($c['upS']) : '') . '</span>';
            // TEK SATIR: rozetler kalkıp yaş sağdaki dar sabit kolona geçince
            // sürüm etiketin yanına sığar oldu (9px, silik). Dar pencerede
            // yalnızca sürüm üç noktayla kırpılır (tamamı hover'da) —
            // etiket ve durum notu asla bozulmaz.
            $ver = isset($c['ver'])
                 ? '<span class="sub-ver" title="' . htmlspecialchars($c['verT'] ?? $c['ver']) . '">' . htmlspecialchars($c['ver']) . '</span>'
                 : '';
            $out .= '<div class="sub-check">'
                  . '<span class="sub-dot ' . ($c['ok'] ? 'ok' : 'err') . '"></span>'
                  . '<span class="sub-lbl">' . htmlspecialchars($c['label']) . $ver . '</span>'
                  . '<span class="sub-note' . (!empty($c['warn']) ? ' note-warn' : '') . '">' . $note . '</span>'
                  . $age
                  . '</div>' . "\n";
        }
    }
    return $out;
}
function bclass($s) { return $s === 'operational' ? 'badge-ok' : ($s === 'degraded' ? 'badge-warn' : 'badge-err'); }
function blabel($s) { return $s === 'operational' ? 'Operational' : ($s === 'degraded' ? 'Degraded' : 'Offline'); }

// ── Sunucu tarafı sparkline (SVG) ─────────────────────────────
// Mail eklerinde JS ölü olabilir (taşıma katmanı 998+ baytlık satırları
// kırar, kısıtlı ortamlar script'i engelleyebilir). Grafikler bu yüzden
// PHP'de SVG olarak da çizilir; canlıda JS ilk karesini çizince SVG'yi söker.
function lcolCss($v, $t, $ok = 'var(--accent)') { $r = $v / max($t, 1); return $r >= 2.0 ? 'var(--danger)' : ($r >= 1.0 ? 'var(--warn)' : $ok); } // 1.0×=doygun / 2.0×=aşırı yük
function scolCss($v, $hi, $cr, $ok = 'var(--accent)') { return $v >= $cr ? 'var(--danger)' : ($v >= $hi ? 'var(--warn)' : $ok); }

function svgSpark($data, $W, $H, $col, $ssrId) {
    $data = array_values($data);
    $n = count($data);
    if ($n < 2) return '<span class="spark-ssr" id="' . $ssrId . '"></span>';
    $mn = min($data); $mx = max($data); $rng = ($mx - $mn) ?: 1;
    $pts = [];
    for ($i = 0; $i < $n; $i++) {
        $pts[] = [$i * ($W / ($n - 1)), $H - 2 - (($data[$i] - $mn) / $rng) * ($H - 4)];
    }
    $d = sprintf('M%.1f %.1f', $pts[0][0], $pts[0][1]);
    for ($i = 1; $i < $n; $i++) {
        $m  = ($pts[$i-1][0] + $pts[$i][0]) / 2;
        // her segmenti yeni satıra: path verisi newline'a bağışık, mail satır limiti aşılamaz
        $d .= sprintf("\nC%.1f %.1f %.1f %.1f %.1f %.1f", $m, $pts[$i-1][1], $m, $pts[$i][1], $pts[$i][0], $pts[$i][1]);
    }
    $last = end($pts);
    $svg  = '<svg class="spark-ssr" id="' . $ssrId . '" width="' . $W . '" height="' . $H . '" viewBox="0 0 ' . $W . ' ' . $H . '">'
          . "\n" . '<path d="' . $d . '" fill="none" stroke="' . $col . '" stroke-width="1.5"/>'
          . "\n" . '<circle cx="' . sprintf('%.1f', $last[0]) . '" cy="' . sprintf('%.1f', $last[1]) . '" r="2.5" fill="' . $col . '"/>';
    $mi = 0;
    for ($i = 1; $i < $n; $i++) if ($data[$i] > $data[$mi]) $mi = $i;
    if ($mx > $mn && $mi !== $n - 1) {
        $svg .= "\n" . '<circle cx="' . sprintf('%.1f', $pts[$mi][0]) . '" cy="' . sprintf('%.1f', $pts[$mi][1])
              . '" r="3" fill="' . $col . '" stroke="var(--card)" stroke-width="1.5"/>';
    }
    return $svg . "\n</svg>";
}

// SSR veri setleri: tohum + anlık değer (JS'in ilk push'uyla birebir)
$ssr = [];
foreach (['l1' => $load1, 'l5' => $load5, 'l15' => $load15,
          'cpu' => $cpuUsage, 'ram' => $memUsagePercent,
          'disk' => $diskUsagePercent, 'iow' => $ioWait,
          'wrk' => ($lsphpTotal ?? 0),
          'rx' => (int)round(($rxRate ?? 0) / 1024), 'tx' => (int)round(($txRate ?? 0) / 1024),
          'mq' => ($mailQ ?? 0)] as $k => $cur) {
    $ssr[$k] = $histSeed[$k];
    $ssr[$k][] = $cur;
}

// ── Process tabloları ─────────────────────────────────────────
function pcpuClass($v) { $v = (float)$v; return $v >= 50 ? 'hot' : ($v >= 20 ? 'warm' : ''); }
function pmemClass($v) { $v = (float)$v; return $v >= 15 ? 'hot' : ($v >= 5 ? 'warm' : ''); }

function renderProcTables($procCpu, $procRam, $procPhp, $diskAcct = []) {
    $h = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');

    $out = '<div class="proc-card"><div class="proc-title">Top processes · CPU</div>'
         . '<table class="proc-table"><thead><tr><th>PID</th><th>User</th><th class="num" title="Percent of a single core &mdash; multi-threaded processes can exceed 100">CPU%</th><th class="num">MEM%</th><th>Time</th><th>Command</th></tr></thead><tbody id="pt-cpu">' . "\n";
    foreach ($procCpu as $p) {
        $out .= '<tr><td>' . $h($p[0]) . '</td><td class="proc-user">' . $h($p[1]) . '</td>'
              . '<td class="num ' . pcpuClass($p[2]) . '">' . $h($p[2]) . '</td>'
              . '<td class="num ' . pmemClass($p[3]) . '">' . $h($p[3]) . '</td><td>' . $h($p[4]) . '</td>'
              . '<td class="td-fill"><span class="proc-cmd" title="' . $h($p[5]) . '">' . $h($p[5]) . '</span></td></tr>' . "\n";
    }
    $out .= '</tbody></table></div>';

    $out .= '<div class="proc-card"><div class="proc-title">Top processes &middot; RAM</div>'
          . '<table class="proc-table"><thead><tr><th>PID</th><th>User</th><th class="num">MEM%</th><th class="num">RSS</th><th>Command</th></tr></thead><tbody id="pt-ram">' . "\n";
    foreach ($procRam as $p) {
        $mc = pmemClass($p[3]);
        $out .= '<tr><td>' . $h($p[0]) . '</td><td class="proc-user">' . $h($p[1]) . '</td>'
              . '<td class="num ' . $mc . '">' . $h($p[3]) . '</td><td class="num ' . $mc . '">' . $h($p[4]) . '</td>'
              . '<td class="td-fill"><span class="proc-cmd proc-cmd-sm" title="' . $h($p[5]) . '">' . $h($p[5]) . '</span></td></tr>' . "\n";
    }
    $out .= '</tbody></table></div>';

    // 3. sütun: en dolu hesaplar (disk) — dikey tablo, diğerleriyle aynı stil.
    $out .= renderDiskCard($diskAcct, $h);

    $out .= '<div class="proc-card"><div class="proc-title">PHP &middot; account <span class="proc-age">&middot; active+idle</span></div>'
          . '<table class="proc-table"><thead><tr><th>Account</th><th></th><th class="num" title="All lsphp processes for the account, idle pool included &mdash; the PHP Workers card counts only active (R/D) ones">Procs</th></tr></thead><tbody id="pt-php">' . "\n";
    $phpMax = 1;
    foreach ($procPhp as $p) { if ($p[1] > $phpMax) $phpMax = $p[1]; }
    foreach ($procPhp as $p) {
        $cls = $p[1] >= 10 ? 'hot' : ($p[1] >= 5 ? 'warm' : '');
        $w   = round($p[1] / $phpMax * 100);
        $out .= '<tr><td class="proc-user">' . $h($p[0]) . '</td>'
              . '<td class="php-bar-cell"><span class="php-bar" style="width:' . $w . '%"></span></td>'
              . '<td class="num ' . $cls . '">' . (int)$p[1] . '</td></tr>' . "\n";
    }
    $out .= '</tbody></table></div>';

    return $out;
}

// En dolu hesaplar — dikey tablo (lsphp/account stiliyle aynı), Processes
// satırında 3. sütun. Hesap-obezlerini erken yakalar (saatlik, quota'dan).
// Hesap disk rengi — ORANSAL (toplam diskin %'si, taşınabilir): >%3 kırmızı,
// >%1 turuncu. 933 GB diskte ≈ 28 GB / 9 GB — "10 sarı, 30 kırmızı" sezgisine
// denk. "Bu hesap tüm sunucu diskinin ciddi kısmını yiyor" sinyali.
function diskAcctCls($gb, $totalGB) {
    if ($totalGB <= 0) return '';
    $pct = $gb / $totalGB * 100;
    return $pct >= 3 ? 'hot' : ($pct >= 1 ? 'warm' : '');
}
function renderDiskCard($diskAcct, $h) {
    global $diskTotalGB;
    $out = '<div class="proc-card"><div class="proc-title">Top disk &middot; account'
         . '<span class="proc-age" title="cPanel account disk usage from quota (hourly). Color: red >3%, orange >1.5% of total disk">&middot; GB used</span></div>'
         . '<table class="proc-table"><thead><tr><th>Account</th><th></th><th class="num">GB</th></tr></thead><tbody id="pt-disk">' . "\n";
    if (!$diskAcct) {
        $out .= '<tr><td colspan="3" style="color:var(--hint)">quota data pending</td></tr>';
    }
    $mx = 0.1;
    foreach ($diskAcct as $p) if ($p[1] > $mx) $mx = $p[1];
    foreach ($diskAcct as $p) {
        $w  = round($p[1] / $mx * 100);
        $gb = rtrim(rtrim(number_format($p[1], 1), '0'), '.');
        $out .= '<tr><td class="proc-user">' . $h($p[0]) . '</td>'
              . '<td class="php-bar-cell"><span class="php-bar" style="width:' . $w . '%"></span></td>'
              . '<td class="num ' . diskAcctCls($p[1], $diskTotalGB) . '">' . $gb . '</td></tr>' . "\n";
    }
    return $out . '</tbody></table></div>';
}

function sqlTimeClass($t) { $t = (int)$t; return $t >= 60 ? 'hot' : ($t >= 10 ? 'warm' : ''); }

function renderSqlTable($procSql, $sqlMinSec = 5, $mysqlThr = null, $mysqlThrCol = 'var(--hint)') {
    $h = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
    // Threads_running: 5sn+ tablosunun görmediği "kısa ama çok sorgu" yükünün anlık
    // göstergesi. Çekirdeğe oranlı renk (warn ≥ çekirdek / err ≥ 2×) — DB'de sorgu birikmesi.
    $out = '<div class="proc-card"><div class="proc-title">MySQL &middot; active queries'
         . '<span class="proc-age" id="sql-thr" title="Threads executing a query at snapshot time, incl. sub-' . (int)$sqlMinSec . 's ones the list below does not show (the snapshot&#39;s own status query counts as 1)">'
         . ($mysqlThr !== null ? ' &middot; Threads_running: <span id="sql-thr-n" style="color:' . $mysqlThrCol . '">' . (int)$mysqlThr . '</span>' : '') . '</span></div>'
         . '<table class="proc-table"><thead><tr><th>ID</th><th>User</th><th>DB</th><th class="num">Time(s)</th><th>State</th><th>Query</th></tr></thead><tbody id="pt-sql">' . "\n";
    if (!$procSql) {
        $out .= '<tr><td colspan="6" class="sql-empty" style="color:var(--hint)">No queries running longer than ' . $sqlMinSec . 's at snapshot time</td></tr>';
    }
    foreach ($procSql as $p) {
        $out .= '<tr><td>' . $h($p[0]) . '</td><td class="proc-user">' . $h($p[1]) . '</td>'
              . '<td>' . $h($p[2]) . '</td><td class="num ' . sqlTimeClass($p[3]) . '">' . $h($p[3]) . '</td>'
              . '<td>' . $h($p[4]) . '</td><td class="td-fill"><span class="proc-cmd proc-cmd-sql" title="' . $h($p[5]) . '">' . $h($p[5]) . '</span></td></tr>' . "\n";
    }
    $out .= '</tbody></table></div>';
    return $out;
}
?>
<!DOCTYPE html>
<!-- lang="en": sayfa metni İngilizce; tr kalırsa text-transform:uppercase "İNFO/TİME" üretir --><html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title><?=htmlspecialchars($SITE_TITLE, ENT_QUOTES, 'UTF-8')?></title>
<meta name="robots" content="noindex,nofollow,noarchive">
<?php if ($FAVICON_URL): ?><link rel="icon" type="image/png" href="<?=htmlspecialchars($FAVICON_URL, ENT_QUOTES, 'UTF-8')?>"><?php endif; ?>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.19.0/dist/tabler-icons.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root,[data-theme="light"]{
  --brand:       #1b3f8b;
  --accent:      #2563eb;
  --accent-bg:   #e8f0fb;
  --warn:        #f59e0b;
  --warn-bg:     #fef3cd;
  --warn-txt:    #7c5000;
  --danger:      #ef4444;
  --danger-bg:   #fde8e8;
  --danger-txt:  #9b1c1c;
  --ok:          #22c55e;
  --ok-bg:       #dcfce7;
  --ok-txt:      #15632a;
  --bg:          #eef2f8;
  --card:        #ffffff;
  --card2:       #f8fafc;
  --border:      rgba(0,0,0,.07);
  --text:        #0d1520;
  --muted:       #64748b;
  --hint:        #94a3b8;
  --bar-track:   #edf2f9;
  --log-item-bg: #f8fafc;
  --cmd-bg:      #f1f5f9;
  --logo-filter: none;
  --hdr-sub:     rgba(255,255,255,.5);
  --hdr-meta-lbl:rgba(255,255,255,.45);
  --c-cpu:  #0891b2;
  --c-ram:  #7c3aed;
  --c-disk: #0d9488;
  --c-iow:  #0284c7;
}
[data-theme="dark"]{
  --brand:       #1e1b4b;
  --accent:      #818cf8;
  --accent-bg:   rgba(129,140,248,.18);
  --warn:        #fbbf24;
  --warn-bg:     rgba(251,191,36,.12);
  --warn-txt:    #fbbf24;
  --danger:      #f87171;
  --danger-bg:   rgba(248,113,113,.12);
  --danger-txt:  #f87171;
  --ok:          #34d399;
  --ok-bg:       rgba(52,211,153,.12);
  --ok-txt:      #34d399;
  --bg:          #0f0e1a;
  --card:        #1a1830;
  --card2:       #211f38;
  --border:      rgba(255,255,255,.07);
  --text:        #e2e8f0;
  --muted:       #94a3b8;
  --hint:        #64748b;
  --bar-track:   rgba(255,255,255,.08);
  --log-item-bg: rgba(255,255,255,.04);
  --cmd-bg:      rgba(255,255,255,.06);
  --logo-filter: brightness(0) invert(1);
  --hdr-sub:     rgba(255,255,255,.4);
  --hdr-meta-lbl:rgba(255,255,255,.4);
  --c-cpu:  #22d3ee;
  --c-ram:  #a78bfa;
  --c-disk: #2dd4bf;
  --c-iow:  #38bdf8;
}
body{background:var(--bg);font-family:'Inter',system-ui,sans-serif;font-size:13px;color:var(--text);-webkit-font-smoothing:antialiased;padding:16px;transition:background .3s,color .3s;}
.wrap{max-width:1280px;margin:auto;}

.hdr{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;background:var(--brand);border-radius:14px;padding:16px 22px;margin-bottom:10px;transition:background .3s;}
.hdr-brand{display:flex;align-items:center;gap:12px;}
.hdr-logo{width:40px;height:40px;border-radius:10px;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;overflow:hidden;}
.hdr-logo img{width:28px;filter:var(--logo-filter);}
.hdr-title{color:#fff;font-size:16px;font-weight:700;letter-spacing:-.03em;line-height:1.1;}
.hdr-sub{color:var(--hdr-sub);font-size:11px;margin-top:2px;}
.hdr-meta{display:flex;gap:20px;flex-wrap:wrap;align-items:center;}
.meta-item{text-align:right;}
.meta-lbl{font-size:10px;color:var(--hdr-meta-lbl);text-transform:uppercase;letter-spacing:.05em;}
.meta-val{font-size:13px;font-weight:600;color:#fff;margin-top:2px;}
.hdr-status{display:flex;align-items:center;gap:7px;background:rgba(255,255,255,.1);border-radius:8px;padding:6px 12px;}
.hdr-status-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;animation:pulse 2s infinite;}
.hdr-status-txt{font-size:11px;font-weight:600;color:#fff;}
.hdr-status-short{font-size:11px;font-weight:600;color:#fff;display:none;} /* sadece mobilde */
.hdr-status-detail{font-size:11px;color:rgba(255,255,255,.72);border-left:1px solid rgba(255,255,255,.28);padding-left:8px;margin-left:2px;max-width:52vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.hdr-status-full{display:contents;} /* masaüstü: sarmalayıcı görünmez, txt+detay eskisi gibi satır içi. Mobilde dokun-aç panel olur. */
/* Aktivite çipleri (backup/wp-toolkit/imunify + süre) — silik gri yazıyla gözden kaçıyordu.
   Konteyner sarmalı flex: çipler arasında boşluk karakteri yok (join''), flex-wrap
   olmadan mobilde satır kırılamayıp ekran dışına taşıyordu. */
#act-chips{display:inline-flex;flex-wrap:wrap;gap:4px;vertical-align:middle;max-width:100%;margin-left:6px;}
.bk-chip{font-size:9px;font-weight:700;background:var(--accent-bg);color:var(--accent);padding:2px 6px;border-radius:4px;letter-spacing:.04em;white-space:nowrap;}
.theme-btn{width:32px;height:32px;border-radius:8px;background:rgba(255,255,255,.12);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;color:#fff;font-size:16px;flex-shrink:0;transition:background .2s;}
.theme-btn:hover{background:rgba(255,255,255,.2);}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--ok);margin-right:5px;vertical-align:middle;animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.4;transform:scale(1.6);}}
.sec{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--hint);margin:12px 0 7px 2px;}
.sec-range{font-weight:400;text-transform:none;letter-spacing:0;color:var(--hint);}

.loads-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:8px;}
.load-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:11px 14px;position:relative;overflow:hidden;display:flex;align-items:center;gap:12px;transition:background .3s,border-color .3s;}
.load-card::after{content:"";position:absolute;bottom:0;left:0;right:0;height:2.5px;background:var(--c,var(--accent));}
.load-left{flex:1;min-width:0;}
.load-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--hint);margin-bottom:4px;white-space:nowrap;}
.load-sub-inline{font-weight:400;text-transform:none;letter-spacing:0;opacity:.7;}
.load-val{font-size:22px;font-weight:700;letter-spacing:-.04em;line-height:1;color:var(--c,var(--accent));transition:color .3s;}
.load-pct{font-size:10px;color:var(--hint);margin-top:3px;}
.load-spark{width:80px;height:32px;flex-shrink:0;}

.resources-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;}
.res-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:13px 14px;position:relative;overflow:hidden;transition:background .3s,border-color .3s;}
.res-card::after{content:"";position:absolute;bottom:0;left:0;right:0;height:2.5px;background:var(--c,var(--accent));}
.res-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;}
.res-left{display:flex;align-items:center;gap:7px;}
.res-icon{font-size:15px;color:var(--hint);}
.res-name{font-size:11px;font-weight:600;color:var(--muted);}
.res-val{font-size:22px;font-weight:700;letter-spacing:-.04em;color:var(--c,var(--accent));transition:color .3s;}
.res-middle{display:flex;align-items:center;gap:10px;margin-bottom:6px;}
.res-bar-wrap{flex:1;}
.res-bar-track{height:5px;background:var(--bar-track);border-radius:999px;overflow:hidden;}
.res-bar-fill{height:100%;border-radius:999px;background:var(--c,var(--accent));width:0%;transition:width .6s ease,background .3s;}
.res-spark{width:70px;height:24px;flex-shrink:0;}
.res-meta{font-size:10px;color:var(--hint);}

.info-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;}
.info-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:10px;transition:background .3s,border-color .3s;}
.info-icon{width:32px;height:32px;border-radius:9px;background:var(--accent-bg);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;}
.info-spark{width:64px;height:30px;margin-left:auto;align-self:center;flex-shrink:0;position:relative;}
.info-spark-canvas{position:absolute;inset:0;width:100%;height:100%;}
.info-body{flex:1;min-width:0;}
.info-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--hint);}
.info-val{font-size:15px;font-weight:700;letter-spacing:-.03em;color:var(--accent);margin-top:2px;transition:color .3s;}
.info-sub{font-size:10px;color:var(--hint);margin-top:1px;}

.svcs-row1{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:8px;}
.svcs-row2{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;}
.svc-card{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;transition:background .3s,border-color .3s;}
.svc-top{display:flex;align-items:center;gap:10px;padding:12px 14px 10px;}
.svc-icon{width:34px;height:34px;border-radius:9px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:17px;transition:background .3s,color .3s;}
.svc-info{flex:1;min-width:0;}
.svc-name{font-size:12px;font-weight:600;}
.svc-count{font-size:10px;color:var(--muted);margin-top:1px;}
.badge{font-size:10px;font-weight:600;padding:3px 9px;border-radius:999px;white-space:nowrap;}
.badge-ok  {background:var(--ok-bg);    color:var(--ok-txt);}
.badge-warn{background:var(--warn-bg);  color:var(--warn-txt);}
.badge-err {background:var(--danger-bg);color:var(--danger-txt);}
.svc-checks{border-top:1px solid var(--border);padding:8px 14px 10px;display:flex;flex-direction:column;gap:5px;flex:1;}
.sub-check{display:flex;align-items:center;gap:7px;min-height:20px;}
.sub-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;}
.sub-dot.ok   {background:var(--ok);}
.sub-dot.err  {background:var(--danger);}
.sub-dot.muted{background:var(--hint);}
.sub-lbl{font-size:11px;color:var(--muted);flex:1;display:flex;align-items:center;gap:4px;min-width:0;white-space:nowrap;overflow:hidden;} /* etiket asla sarmasın; sıkışınca önce sürüm kırpılır */
.sub-note{font-size:10px;color:var(--hint);white-space:nowrap;}
.sub-note.note-warn{color:var(--warn);font-weight:600;} /* yakın zamanda restart olmuş servis */
/* Yaş sütunu: her satırda sabit genişlik → sağ kenarda dikey hizalı, taranabilir */
.sub-age{width:24px;flex-shrink:0;text-align:right;font-size:9.5px;color:var(--hint);white-space:nowrap;}
/* Sürüm — etiketin yanında silik; dar pencerede yalnız o kırpılır (tamamı hover'da) */
.sub-ver{font-size:9px;font-weight:400;color:var(--hint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;flex:0 1 auto;}
.copy-btn{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:5px;border:1px solid var(--border);background:transparent;cursor:pointer;color:var(--hint);flex-shrink:0;transition:background .15s,color .15s,border-color .15s;}
.copy-btn:hover{background:var(--accent-bg);color:var(--accent);border-color:var(--accent);}
.copy-btn.copied{background:var(--ok-bg);color:var(--ok);border-color:var(--ok);}
.sub-cmd-inline{font-size:10px;color:var(--muted);background:var(--cmd-bg);padding:2px 6px;border-radius:5px;font-family:'SFMono-Regular',Consolas,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px;}

.proc-row{display:grid;grid-template-columns:2.2fr 1.5fr 1fr 1fr;gap:8px;}
.proc-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px;overflow:hidden;transition:background .3s,border-color .3s;}
.proc-title{font-size:12px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;}
.proc-age{font-size:10px;color:var(--hint);font-weight:400;text-transform:none;letter-spacing:0;}
.proc-age.stale{color:var(--warn);font-weight:600;}
.proc-table{width:100%;border-collapse:collapse;font-size:11px;}
.proc-table th{text-align:left;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--hint);padding:2px 6px 5px 0;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;}
/* Tıklanır sıralama göstergesi (canlı sayfa; mail ekinde JS ölü, cron sıralaması kalır) */
.proc-table th.sorted-desc:after{content:" \2193";color:var(--accent);}
.proc-table th.sorted-asc:after{content:" \2191";color:var(--accent);}
.proc-table th[title]{cursor:help;text-decoration:underline dotted;text-underline-offset:2px;}
.proc-table td{padding:3.5px 6px 3.5px 0;color:var(--muted);border-bottom:1px solid var(--border);white-space:nowrap;}
.proc-table tr:last-child td{border-bottom:none;}
.proc-table .num{text-align:right;font-variant-numeric:tabular-nums;}
.proc-table .hot{color:var(--danger);font-weight:600;}
.proc-table .warm{color:var(--warn);font-weight:600;}
.proc-cmd{font-family:'SFMono-Regular',Consolas,monospace;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;cursor:pointer;}
.proc-table td.td-fill{width:100%;max-width:0;}
.proc-cmd.expanded{white-space:normal;word-break:normal;overflow-wrap:anywhere;overflow:visible;max-width:none;}
.proc-user{font-weight:600;color:var(--text);}
.proc-table tbody tr:hover td{background:var(--card2);}
.php-bar-cell{width:56px;}
.php-bar{display:inline-block;height:5px;border-radius:999px;background:var(--accent);opacity:.55;min-width:3px;vertical-align:middle;}
.proc-row-sql{display:grid;grid-template-columns:1fr;gap:8px;margin-top:8px;}

.log-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px;transition:background .3s,border-color .3s;}
.log-hdr{display:flex;align-items:center;gap:8px;margin-bottom:10px;}
.log-hdr-title{font-size:12px;font-weight:600;flex:1;}
.log-clear{font-size:10px;color:var(--muted);cursor:pointer;padding:3px 9px;border:1px solid var(--border);border-radius:6px;background:transparent;transition:background .15s;}
.log-clear:hover{background:var(--card2);}
.log-list{display:flex;flex-direction:column;gap:4px;max-height:140px;overflow-y:auto;}
.log-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:7px;background:var(--log-item-bg);}
.log-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;}
.log-dot.ok  {background:var(--ok);}
.log-dot.warn{background:var(--warn);}
.log-dot.err {background:var(--danger);}
.log-txt{font-size:11px;color:var(--muted);flex:1;}
.log-ts{font-size:10px;color:var(--hint);white-space:nowrap;}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(10px);background:#0d1520;color:#fff;font-size:11px;font-weight:500;padding:8px 14px;border-radius:8px;opacity:0;transition:opacity .2s,transform .2s;pointer-events:none;z-index:999;}
[data-theme="dark"] .toast{background:var(--card2);color:var(--text);}
.spark-wrap{position:relative;flex-shrink:0;display:block;}
.spark-wrap .load-spark,.spark-wrap .res-spark{position:absolute;inset:0;width:100%;height:100%;}
.spark-ssr{position:absolute;inset:0;width:100%;height:100%;}
.spark-tip{position:fixed;z-index:998;background:#0d1520;color:#fff;font-size:10px;font-weight:600;padding:4px 8px;border-radius:6px;pointer-events:none;opacity:0;transition:opacity .12s;white-space:nowrap;text-align:center;}
.spark-tip .tip-v{display:block;font-size:11px;font-weight:700;}
.spark-tip .tip-t{display:block;font-size:9px;font-weight:500;opacity:.65;margin-top:1px;}
.static-mode .dot,.static-mode .hdr-status-dot{animation:none;}
[data-theme="dark"] .spark-tip{background:var(--card2);color:var(--text);border:1px solid var(--border);}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0);}
.footer{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:10px;color:var(--hint);flex-wrap:wrap;gap:6px;padding:0 2px;}
.footer-credit{flex:1;text-align:center;}
.footer-credit a{color:var(--hint);text-decoration:none;opacity:.85;transition:opacity .2s;}
.footer-credit a:hover{opacity:1;text-decoration:underline;}

@media(max-width:1100px){
  .loads-row{grid-template-columns:repeat(3,1fr);}
  .resources-row{grid-template-columns:repeat(2,1fr);}
  .info-row{grid-template-columns:repeat(3,1fr);}
  .svcs-row1,.svcs-row2{grid-template-columns:repeat(2,1fr);}
  .proc-row{grid-template-columns:1fr 1fr;}
}
@media(max-width:680px){
  .loads-row{grid-template-columns:repeat(3,1fr);}
  /* Load kartı dikey dizilir: etiket/değer/%, grafik kartın 3. satırında tam genişlik */
  .load-card{flex-direction:column;align-items:stretch;gap:6px;padding:10px 10px 8px;}
  .load-left{width:100%;}
  .load-lbl{white-space:normal;}
  .load-val{font-size:19px;}
  .load-card .spark-wrap{width:100%!important;height:26px!important;}
  /* minmax(0,1fr): kart min-content'i (64px sparkline + en uzun kelime)
     kolonu genişletip yatay taşma yaratmasın, kart daralabilsin */
  .resources-row,.info-row{grid-template-columns:repeat(2,minmax(0,1fr));}
  /* İkon dekoratif, mobilde gizlenir; sparkline veri taşıdığı için kalır */
  .info-icon{display:none;}
  /* Sürüm masaüstü/mail teşhis detayı — dar ekranda kırpık sürüm gürültü olur */
  .sub-ver{display:none;}
  .svcs-row1,.svcs-row2{grid-template-columns:1fr;}
  .proc-row{grid-template-columns:1fr;}
  /* Mobilde meta satırı sığmıyor: hostname/threads/uptime/updated gizlenir AMA
     en kritik bilgi — genel durum — kalır. Alt satıra taşmasın diye başlık tek
     satıra kilitlenir (uzunsa "…"), brand daralır, kompakt durum rozeti (renkli
     nokta + OK/Degraded/Issues) tema düğmesinin yanında SAĞ ÜST köşede sabit. */
  .hdr{padding:12px 14px;gap:8px;flex-wrap:nowrap;}
  .hdr-brand{flex:1 1 auto;min-width:0;}
  .hdr-brand>div{min-width:0;}
  .hdr-sub{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .hdr-meta{display:flex;gap:0;flex:0 0 auto;align-items:center;}
  .hdr-meta .meta-item{display:none;}
  .hdr-status{height:32px;padding:0 12px;position:relative;} /* tema düğmesiyle (32px) eşit yükseklik */
  .hdr-status-short{display:inline;}
  .hdr-status-full{display:none;} /* mobilde sade: sadece nokta + kelime; detay dokununca açılır */
  /* Detay varsa dokunulabilir olduğunu belli eden küçük ok işareti */
  .hdr-status.has-detail{cursor:pointer;}
  .hdr-status.has-detail .hdr-status-short::after{content:' \25BE';font-size:9px;opacity:.75;}
  .hdr-status.has-detail.st-open .hdr-status-short::after{content:' \25B4';}
  /* Açık: sağ üstten aşağı açılan panel — tam durum + sorun listesi (sarılır) */
  .hdr-status.st-open .hdr-status-full{
    display:flex;flex-direction:column;gap:5px;align-items:flex-start;
    position:absolute;top:calc(100% + 7px);right:0;z-index:60;
    background:var(--brand);border:1px solid rgba(255,255,255,.16);border-radius:9px;
    padding:10px 12px;min-width:180px;max-width:82vw;box-shadow:0 10px 28px rgba(0,0,0,.4);
  }
  .hdr-status.st-open .hdr-status-txt{display:block;font-size:12px;font-weight:700;color:#fff;}
  .hdr-status.st-open .hdr-status-detail{display:block!important;border-left:none;padding-left:0;margin-left:0;max-width:none;white-space:normal;overflow:visible;line-height:1.5;color:rgba(255,255,255,.82);}
  .hdr-title{font-size:14px;white-space:nowrap;}
  .load-pct{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  /* Mobilde tablo EKRANA SIĞAR (kaydırma yok): düşük değerli kolonlar
     gizlenir, komut sütunu daralır; dokununca satır dikey açılır. */
  .proc-table{font-size:10px;}
  .proc-table td,.proc-table th{padding-right:4px;}
  /* Mobilde PID/ID gizlenir (telefonda işlevsiz); yüzdeler ve renk sinyalleri görünür kalır */
  .proc-row .proc-card:nth-child(1) th:nth-child(1),
  .proc-row .proc-card:nth-child(1) td:nth-child(1),
  .proc-row .proc-card:nth-child(2) th:nth-child(1),
  .proc-row .proc-card:nth-child(2) td:nth-child(1),
  .proc-row-sql th:nth-child(1),.proc-row-sql td:nth-child(1),
  .proc-row-sql th:nth-child(3),.proc-row-sql td:nth-child(3),
  .proc-row-sql th:nth-child(5),.proc-row-sql td:nth-child(5){display:none;}
  .proc-row-sql td.sql-empty{display:table-cell!important;}
}
@media(max-width:379px){
  /* Çok dar ekran: başlık satırı yatay taşma yapmasın. Fontlar küçülür
     (320px'te başlık+rozet hâlâ tek satır); daha da darsa nowrap kalkar,
     rozet alt satıra sarar — sayfa kaydırmaz. */
  .hdr-brand{gap:8px;}
  .hdr-title{font-size:12.5px;white-space:normal;}
  .hdr-sub{font-size:10px;}
  .info-spark{width:52px;}
}
</style>
</head>
<body>
<div class="wrap">

<div class="hdr">
  <div class="hdr-brand">
    <div class="hdr-logo">
<?php if ($LOGO_URL): ?>
      <img src="<?=htmlspecialchars($LOGO_URL, ENT_QUOTES, 'UTF-8')?>"
           onerror="this.style.display='none';this.parentNode.innerHTML='<span style=color:#fff;font-size:13px;font-weight:700><?=$INITIALS?></span>'"
           alt="<?=htmlspecialchars($SITE_TITLE, ENT_QUOTES, 'UTF-8')?>">
<?php else: ?>
      <span style="color:#fff;font-size:13px;font-weight:700"><?=$INITIALS?></span>
<?php endif; ?>
    </div>
    <div>
      <div class="hdr-title"><?=htmlspecialchars($SITE_TITLE, ENT_QUOTES, 'UTF-8')?>
      </div>
      <div class="hdr-sub"><?=htmlspecialchars($SITE_SUB, ENT_QUOTES, 'UTF-8')?></div>
    </div>
    <button class="theme-btn" id="theme-btn" title="Toggle dark mode" style="margin-left:8px;">
      <i class="ti ti-moon" id="theme-icon"></i>
    </button>
  </div>
  <div class="hdr-meta">
    <div class="hdr-status<?=$overallDetail!==''?' has-detail':''?>" id="hdr-status">
      <div class="hdr-status-dot" id="hdr-dot" style="background:<?=$overallColorCss?>"></div>
      <span class="hdr-status-short" id="hdr-short"><?=$overallShort?></span>
      <div class="hdr-status-full">
        <span class="hdr-status-txt" id="hdr-txt"><?=$overallStatus?></span>
        <span class="hdr-status-detail" id="hdr-detail"<?=$overallDetail===''?' style="display:none"':''?>><?=htmlspecialchars($overallDetail, ENT_QUOTES, 'UTF-8')?></span>
      </div>
    </div>
    <div class="meta-item"><div class="meta-lbl">Hostname</div>
      <div class="meta-val" id="hostname"><?=htmlspecialchars(gethostname(),ENT_QUOTES,'UTF-8')?></div></div>
    <div class="meta-item"><div class="meta-lbl">Threads</div>
      <div class="meta-val" id="threads"><?=$coreCount?></div></div>
    <div class="meta-item"><div class="meta-lbl">Uptime</div>
      <div class="meta-val" id="uptime"><?=$uptimeFormatted?></div></div>
    <div class="meta-item"><div class="meta-lbl" id="updated-lbl">Updated</div>
      <div class="meta-val"><span class="dot"></span><span id="time-val"><?=date('H:i:s')?></span></div></div>
  </div>
</div>

<div class="sec">System metrics <span class="sec-range" id="metrics-range"><?php if (!empty($histSeed['t'])): ?>&middot; <?=htmlspecialchars($histSeed['t'][0])?> &ndash; <?=date('H:i')?><?php endif; ?></span></div>
<div class="loads-row">
  <div class="load-card" id="lc-l1" style="--c:<?=$lc1=lcolCss($load1, $coreCount)?><?=cardBorderCss($lc1)?>">
    <div class="load-left">
      <div class="load-lbl">Load avg <span class="load-sub-inline">1 min</span></div>
      <div class="load-val" id="v-l1"><?=number_format($load1,2)?></div>
      <div class="load-pct" id="p-l1"><?=round($load1/$coreCount*100)?>% of <?=$coreCount?> cores</div>
    </div>
    <span class="spark-wrap" style="width:80px;height:32px"><?=svgSpark($ssr['l1'], 80, 32, lcolCss($load1, $coreCount), 'ssr-l1')?><canvas class="load-spark" id="sp-l1"></canvas></span>
  </div>
  <div class="load-card" id="lc-l5" style="--c:<?=$lc5=lcolCss($load5, $coreCount)?><?=cardBorderCss($lc5)?>">
    <div class="load-left">
      <div class="load-lbl">Load avg <span class="load-sub-inline">5 min</span></div>
      <div class="load-val" id="v-l5"><?=number_format($load5,2)?></div>
      <div class="load-pct" id="p-l5"><?=round($load5/$coreCount*100)?>% of <?=$coreCount?> cores</div>
    </div>
    <span class="spark-wrap" style="width:80px;height:32px"><?=svgSpark($ssr['l5'], 80, 32, lcolCss($load5, $coreCount), 'ssr-l5')?><canvas class="load-spark" id="sp-l5"></canvas></span>
  </div>
  <div class="load-card" id="lc-l15" style="--c:<?=$lc15=lcolCss($load15, $coreCount)?><?=cardBorderCss($lc15)?>">
    <div class="load-left">
      <div class="load-lbl">Load avg <span class="load-sub-inline">15 min</span></div>
      <div class="load-val" id="v-l15"><?=number_format($load15,2)?></div>
      <div class="load-pct" id="p-l15"><?=round($load15/$coreCount*100)?>% of <?=$coreCount?> cores</div>
    </div>
    <span class="spark-wrap" style="width:80px;height:32px"><?=svgSpark($ssr['l15'], 80, 32, lcolCss($load15, $coreCount), 'ssr-l15')?><canvas class="load-spark" id="sp-l15"></canvas></span>
  </div>
</div>
<div class="resources-row">
  <div class="res-card" id="rc-cpu" style="--c:<?=$cpuCardCol?><?=cardBorderCss($cpuCardCol)?>">
    <div class="res-top">
      <div class="res-left"><i class="ti ti-cpu res-icon"></i><span class="res-name">CPU</span></div>
      <span class="res-val" id="rv-cpu"><?=$cpuUsage?>%</span>
    </div>
    <div class="res-middle">
      <div class="res-bar-wrap"><div class="res-bar-track"><div class="res-bar-fill" id="rb-cpu" style="width:<?=$cpuUsage?>%"></div></div></div>
      <span class="spark-wrap" style="width:70px;height:24px"><?=svgSpark($ssr['cpu'], 70, 24, $cpuCardCol, 'ssr-cpu')?><canvas class="res-spark" id="sp-cpu"></canvas></span>
    </div>
    <div class="res-meta" id="rm-cpu">Load: <?=number_format($load1,2)?> / <?=number_format($load5,2)?> / <?=number_format($load15,2)?><?=($rState !== null || $dState !== null) ? ' &middot; run ' . (int)$rState . ' / blk ' . (int)$dState : ''?></div>
  </div>
  <div class="res-card" id="rc-ram" style="--c:<?=$ramCardCol?><?=cardBorderCss($ramCardCol)?>">
    <div class="res-top">
      <div class="res-left"><i class="ti ti-server res-icon"></i><span class="res-name">RAM</span></div>
      <span class="res-val" id="rv-ram"><?=$memUsagePercent?>%</span>
    </div>
    <div class="res-middle">
      <div class="res-bar-wrap"><div class="res-bar-track"><div class="res-bar-fill" id="rb-ram" style="width:<?=$memUsagePercent?>%"></div></div></div>
      <span class="spark-wrap" style="width:70px;height:24px"><?=svgSpark($ssr['ram'], 70, 24, $ramCardCol, 'ssr-ram')?><canvas class="res-spark" id="sp-ram"></canvas></span>
    </div>
    <div class="res-meta" id="rm-ram"><?=$memUsedGB?> / <?=$memTotalGB?> GB<?=$shmemGB >= 1 ? ' · <span style="color:' . $shmemCol . '">shmem ' . $shmemGB . ' GB</span>' : ''?><?=$swapTotalGB ? ' · swap ' . $swapUsedGB . '/' . $swapTotalGB . ' GB' : ''?></div>
  </div>
  <div class="res-card" id="rc-disk" style="--c:<?=$diskCardCol?><?=cardBorderCss($diskCardCol)?>">
    <div class="res-top">
      <div class="res-left"><i class="ti ti-database res-icon"></i><span class="res-name">Disk</span></div>
      <span class="res-val" id="rv-disk"><?=$diskUsagePercent?>%</span>
    </div>
    <div class="res-middle">
      <div class="res-bar-wrap"><div class="res-bar-track"><div class="res-bar-fill" id="rb-disk" style="width:<?=$diskUsagePercent?>%"></div></div></div>
      <span class="spark-wrap" style="width:70px;height:24px"><?=svgSpark($ssr['disk'], 70, 24, $diskCardCol, 'ssr-disk')?><canvas class="res-spark" id="sp-disk"></canvas></span>
    </div>
    <div class="res-meta" id="rm-disk"><?=$diskUsedGB?> / <?=$diskTotalGB?> GB<?=$inodePct !== null ? ' &middot; <span style="color:' . $inodeCol . '">inode ' . $inodePct . '%</span>' : ''?><?=($raidState !== null && $raidState !== 'ok') ? ' &middot; <span style="color:' . $raidCol . '">' . htmlspecialchars($raidTxt) . '</span>' : ''?><?=$raidMismatch > 0 ? ' &middot; <span style="color:var(--warn)">' . $raidMismatch . ' mismatch</span>' : ''?><?=$smartTxt !== '' ? ' &middot; <span style="color:var(--danger)">' . $smartTxt . '</span>' : ''?><?=$diskGrow !== '' ? ' &middot; ' . $diskGrow : ''?></div>
  </div>
  <div class="res-card" id="rc-iow" style="--c:<?=$iowCardCol?><?=cardBorderCss($iowCardCol)?>">
    <div class="res-top">
      <div class="res-left"><i class="ti ti-activity res-icon"></i><span class="res-name">IO Wait</span></div>
      <span class="res-val" id="rv-iow"><?=$ioWait?>%</span>
    </div>
    <div class="res-middle">
      <div class="res-bar-wrap"><div class="res-bar-track"><div class="res-bar-fill" id="rb-iow" style="width:<?=min($ioWait,100)?>%"></div></div></div>
      <span class="spark-wrap" style="width:70px;height:24px"><?=svgSpark($ssr['iow'], 70, 24, $iowCardCol, 'ssr-iow')?><canvas class="res-spark" id="sp-iow"></canvas></span>
    </div>
<?php
  // IO Wait metası: disk R/W hızı + D-state (diskte bloklanan süreç). D-state,
  // "load yüksek ama CPU düşük" durumunun kanıtıdır — load'a girer, CPU'da görünmez.
  $iowParts = [];
  if ($ioRead !== null) { $iowParts[] = 'R ' . fmtBytes($ioRead); $iowParts[] = 'W ' . fmtBytes($ioWrite); }
  if ($dState !== null) $iowParts[] = $dState . ' blocked';
?>
    <div class="res-meta" id="rm-iow"><?=$iowParts ? implode(' · ', $iowParts) : 'Disk I/O pressure'?></div>
  </div>
</div>

<div class="sec" style="margin-top:12px">System info</div>
<div class="info-row">
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-arrow-down"></i></div>
    <div class="info-body">
      <div class="info-label">Network IN</div>
      <div class="info-val" id="iv-rx" style="color:<?=$netRxCol?>"><?=fmtBytes($rxRate)?></div>
      <div class="info-sub" id="iv-rx-sub"><?=$netRxSat !== null ? $netRxSat . '% of link' : 'incoming traffic'?></div>
    </div>
    <span class="info-spark spark-wrap"><?=svgSpark($ssr['rx'], 64, 30, $netRxCol, 'ssr-rx')?><canvas class="info-spark-canvas" id="sp-rx"></canvas></span>
  </div>
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-arrow-up"></i></div>
    <div class="info-body">
      <div class="info-label">Network OUT</div>
      <div class="info-val" id="iv-tx" style="color:<?=$netTxCol?>"><?=fmtBytes($txRate)?></div>
      <div class="info-sub" id="iv-tx-sub"><?=$netTxSat !== null ? $netTxSat . '% of link' : 'outgoing traffic'?></div>
    </div>
    <span class="info-spark spark-wrap"><?=svgSpark($ssr['tx'], 64, 30, $netTxCol, 'ssr-tx')?><canvas class="info-spark-canvas" id="sp-tx"></canvas></span>
  </div>
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-cpu"></i></div>
    <div class="info-body">
      <div class="info-label">PHP Workers</div>
      <div class="info-val" id="iv-lsphp" style="color:<?=lsphpCol($lsphpTotal, $coreCount)?>"><?=$lsphpTotal !== null ? $lsphpTotal : '—'?></div>
      <div class="info-sub" id="iv-lsphp-sub" title="Value = active workers (R/D state); the lsphp/account table lists all processes incl. the idle pool"><?=$lsphpIdle !== null ? 'active &middot; ' . $lsphpIdle . ' idle' : 'running lsphp'?></div>
    </div>
    <span class="info-spark spark-wrap"><?=svgSpark($ssr['wrk'], 64, 30, 'var(--accent)', 'ssr-wrk')?><canvas class="info-spark-canvas" id="sp-wrk"></canvas></span>
  </div>
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-mail"></i></div>
    <div class="info-body">
      <div class="info-label">Mail Queue</div>
      <div class="info-val" id="iv-mailq" style="color:<?=mqCol($mailQ, $whmAcctCount)?>"><?=$mailQ !== null ? $mailQ : '—'?></div>
      <div class="info-sub">messages queued</div>
    </div>
    <span class="info-spark spark-wrap"><?=svgSpark($ssr['mq'], 64, 30, 'var(--accent)', 'ssr-mq')?><canvas class="info-spark-canvas" id="sp-mq"></canvas></span>
  </div>
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-bolt"></i></div>
    <div class="info-body">
      <div class="info-label">Web Response</div>
      <div class="info-val" id="iv-web" style="color:<?=rtCol($webResponseTime)?>"><?=$webResponseTime !== null ? $webResponseTime . ' ms' : '—'?></div>
      <div class="info-sub">HTTP response time</div>
    </div>
  </div>
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-database"></i></div>
    <div class="info-body">
      <div class="info-label">MySQL Response</div>
      <div class="info-val" id="iv-mysql" style="color:<?=rtCol($mysqlResponseTime)?>"><?=$mysqlResponseTime !== null ? $mysqlResponseTime . ' ms' : '—'?></div>
      <div class="info-sub">TCP response time</div>
    </div>
  </div>
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-users"></i></div>
    <div class="info-body">
      <div class="info-label">Hosted Accounts</div>
      <div class="info-val" id="iv-acct"><?=$whmAcctCount !== null ? $whmAcctCount : '—'?></div>
      <div class="info-sub">cPanel accounts</div>
    </div>
  </div>
  <div class="info-card">
    <div class="info-icon"><i class="ti ti-lock"></i></div>
    <div class="info-body">
      <div class="info-label">SSL &middot; <?=htmlspecialchars(gethostname(),ENT_QUOTES,'UTF-8')?></div>
      <div class="info-val" id="iv-ssl" style="color:<?=$sslColorCss?>"><?=$sslDaysLeft !== null ? $sslDaysLeft . ' days' : '—'?></div>
      <div class="info-sub" id="iv-ssl-sub"><?=$sslExpiry ?? 'unavailable'?></div>
    </div>
  </div>
</div>

<div class="sec" style="margin-top:12px">Services</div>
<div class="svcs-row1">
  <div class="svc-card">
    <div class="svc-top">
      <div class="svc-icon" id="si-web" style="background:var(--accent-bg);color:var(--accent)"><i class="ti ti-bolt"></i></div>
      <div class="svc-info"><div class="svc-name">Web server</div><div class="svc-count" id="sk-web"><?=$webOk?>/<?=$webTotal?> checks passed</div></div>
      <div class="badge <?=bclass($webStatus)?>" id="bd-web"><?=blabel($webStatus)?></div>
    </div>
    <div class="svc-checks" id="ch-web"><?=renderChecks($webChecks)?></div>
  </div>
  <div class="svc-card">
    <div class="svc-top">
      <div class="svc-icon" id="si-mail" style="background:var(--accent-bg);color:var(--accent)"><i class="ti ti-mail"></i></div>
      <div class="svc-info"><div class="svc-name">Mail services</div><div class="svc-count" id="sk-mail"><?=$mailOk?>/<?=$mailTotal?> checks passed</div></div>
      <div class="badge <?=bclass($mailStatus)?>" id="bd-mail"><?=blabel($mailStatus)?></div>
    </div>
    <div class="svc-checks" id="ch-mail"><?=renderChecks($mailChecks)?></div>
  </div>
  <div class="svc-card">
    <div class="svc-top">
      <div class="svc-icon" id="si-dns" style="background:var(--accent-bg);color:var(--accent)"><i class="ti ti-world"></i></div>
      <div class="svc-info"><div class="svc-name">DNS</div><div class="svc-count" id="sk-dns"><?=$dnsOk?>/<?=$dnsTotal?> checks passed</div></div>
      <div class="badge <?=bclass($dnsStatus)?>" id="bd-dns"><?=blabel($dnsStatus)?></div>
    </div>
    <div class="svc-checks" id="ch-dns"><?=renderChecks($dnsChecks)?></div>
  </div>
</div>
<div class="svcs-row2">
  <div class="svc-card">
    <div class="svc-top">
      <div class="svc-icon" id="si-sec" style="background:var(--accent-bg);color:var(--accent)"><i class="ti ti-shield-check"></i></div>
      <div class="svc-info"><div class="svc-name">Security</div><div class="svc-count" id="sk-sec"><?=$secOk?>/<?=$secTotal?> verified active</div></div>
      <div class="badge <?=bclass($secStatus)?>" id="bd-sec"><?=blabel($secStatus)?></div>
    </div>
    <div class="svc-checks" id="ch-sec"><?=renderChecks($secChecks)?></div>
  </div>
  <div class="svc-card">
    <div class="svc-top">
      <div class="svc-icon" id="si-db" style="background:var(--accent-bg);color:var(--accent)"><i class="ti ti-database"></i></div>
      <div class="svc-info"><div class="svc-name">Database</div><div class="svc-count" id="sk-db"><?=$dbOk?>/<?=$dbTotal?> checks passed</div></div>
      <div class="badge <?=bclass($dbStatus)?>" id="bd-db"><?=blabel($dbStatus)?></div>
    </div>
    <div class="svc-checks" id="ch-db"><?=renderChecks($dbChecks)?></div>
  </div>
  <div class="svc-card">
    <div class="svc-top">
      <div class="svc-icon" id="si-cache" style="background:var(--accent-bg);color:var(--accent)"><i class="ti ti-topology-star-ring"></i></div>
      <div class="svc-info"><div class="svc-name">Cache</div><div class="svc-count" id="sk-cache"><?=$cacheOk?>/<?=$cacheTotal?> active</div></div>
      <div class="badge <?=bclass($cacheStatus)?>" id="bd-cache"><?=blabel($cacheStatus)?></div>
    </div>
    <div class="svc-checks" id="ch-cache"><?=renderChecks($cacheChecks)?></div>
  </div>
  <div class="svc-card">
    <div class="svc-top">
      <div class="svc-icon" id="si-ftp" style="background:var(--accent-bg);color:var(--accent)"><i class="ti ti-file-arrow-right"></i></div>
      <div class="svc-info"><div class="svc-name">FTP</div><div class="svc-count" id="sk-ftp"><?=$ftpOk?>/<?=$ftpTotal?> checks passed</div></div>
      <div class="badge <?=bclass($ftpStatus)?>" id="bd-ftp"><?=blabel($ftpStatus)?></div>
    </div>
    <div class="svc-checks" id="ch-ftp"><?=renderChecks($ftpChecks)?></div>
  </div>
</div>

<?php if ($procCpu || $procRam || $procPhp): ?>
<div class="sec" style="margin-top:12px">Processes
  <span class="proc-age<?=($procAge !== null && $procAge > 180) ? ' stale' : ''?>" id="proc-age">&middot; root snapshot, <?=$procAge?>s ago<?=($procAge !== null && $procAge > 180) ? ' — STALE (cron?)' : ''?></span>
  <span id="act-chips"><?php foreach ($actChips as $ac) echo '<span class="bk-chip">' . htmlspecialchars($ac) . '</span>'; ?></span>
</div>
<div class="proc-row" id="proc-row"><?=renderProcTables($procCpu, $procRam, $procPhp, $diskAcct)?></div>
<div class="proc-row-sql"><?=renderSqlTable($procSql, $sqlMinSec, $mysqlThr, $mysqlThrCol)?></div>
<?php endif; ?>

<div class="sec" style="margin-top:12px">Event log</div>
<div class="log-card">
  <div class="log-hdr">
    <i class="ti ti-list" style="font-size:15px;color:var(--hint)"></i>
    <span class="log-hdr-title">Recent alerts &amp; status changes</span>
    <button class="log-clear" id="log-clear-btn">Clear</button>
  </div>
  <div class="log-list" id="log-list">
<?php if ($seedLogs): foreach (array_reverse($seedLogs) as $L): ?>
    <div class="log-item"><div class="log-dot <?=htmlspecialchars($L['type'])?>"></div><span class="log-txt"><?=htmlspecialchars($L['msg'])?></span><span class="log-ts"><?=htmlspecialchars($L['ts'])?></span></div>
<?php endforeach; else: ?>
    <div style="font-size:11px;color:var(--hint);padding:6px 8px;">No events yet.</div>
<?php endif; ?>
  </div>
</div>

<div class="footer">
  <div id="footer-mode"><span class="dot"></span>Auto-refresh every 30 seconds</div>
<?php if ($CREDIT_TEXT): ?>
  <div class="footer-credit"><?php if ($CREDIT_URL): ?><a href="<?=htmlspecialchars($CREDIT_URL, ENT_QUOTES, 'UTF-8')?>" target="_blank" rel="noopener"><?=htmlspecialchars($CREDIT_TEXT, ENT_QUOTES, 'UTF-8')?></a><?php else: ?><?=htmlspecialchars($CREDIT_TEXT, ENT_QUOTES, 'UTF-8')?><?php endif; ?></div>
<?php endif; ?>
  <div id="footer-time"><?=date('Y-m-d H:i:s')?><?=isset($svcVer['kernel']) ? ' · ' . htmlspecialchars($svcVer['kernel']) : ''?></div>
</div>
</div>
<div class="toast" id="toast"></div>

<script>
(function(){
  const saved  = localStorage.getItem('az-theme');
  const system = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  const theme  = saved || system;
  document.documentElement.setAttribute('data-theme', theme);
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addListener(function(e) {
      if (!localStorage.getItem('az-theme')) {
        const t = e.matches ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', t);
        const icon = document.getElementById('theme-icon');
        if (icon) icon.className = t === 'dark' ? 'ti ti-sun' : 'ti ti-moon';
      }
    });
  }
})();

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('az-theme', theme);
  const icon = document.getElementById('theme-icon');
  if (icon) icon.className = theme === 'dark' ? 'ti ti-sun' : 'ti ti-moon';
}

document.addEventListener('DOMContentLoaded', function() {
  const cur = document.documentElement.getAttribute('data-theme') || 'light';
  const icon = document.getElementById('theme-icon');
  if (icon) icon.className = cur === 'dark' ? 'ti ti-sun' : 'ti ti-moon';
  document.getElementById('theme-btn').addEventListener('click', function() {
    applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    if(typeof redrawSparks==='function')redrawSparks(); // tepe noktası dolgusu yeni temanın --card'ıyla çizilsin
  });
});

const hist={l1:[],l5:[],l15:[],cpu:[],ram:[],disk:[],iow:[],wrk:[],rx:[],tx:[],mq:[]},MAX=92; // güvenlik tavanı — pencereyi HIST_WIN (süre) belirler
const seed=<?=json_encode($histSeed, JSON_PRETTY_PRINT)?>;
const init={l1:<?=json_encode($load1)?>,l5:<?=json_encode($load5)?>,l15:<?=json_encode($load15)?>,t:<?=(int)$coreCount?>,cpu:<?=(int)$cpuUsage?>,ram:<?=(int)$memUsagePercent?>,disk:<?=(int)$diskUsagePercent?>,iow:<?=(int)$ioWait?>,wrk:<?=(int)($lsphpTotal ?? 0)?>,rx:<?=(int)round(($rxRate ?? 0)/1024)?>,tx:<?=(int)round(($txRate ?? 0)/1024)?>,mq:<?=(int)($mailQ ?? 0)?>,time:'<?=date('H:i:s')?>'};
Object.keys(hist).forEach(k=>{if(seed[k]&&seed[k].length)hist[k]=seed[k].slice();});
let histT=(seed.t&&seed.t.length)?seed.t.slice():[];
let lsphpIdle=<?=json_encode($lsphpIdle)?>; // anlık boşta worker (kart alt satırı için)
let lastCardCol={}; // metrik kartı renkleri (sunucudan); tema geçişinde spark yeniden çizimi için
function pushT(v){histT.push(v);if(histT.length>MAX)histT.shift();}
const HIST_WIN=1830; // sn — pencere: son 30 dk (+30 sn tolerans)
function tSec(s){const p=s.split(':');return (+p[0])*3600+(+p[1])*60+(p[2]?+p[2]:0);}
function trimHist(nowStr){
  const n=tSec(nowStr);
  while(histT.length&&(((n-tSec(histT[0]))+86400)%86400)>HIST_WIN){
    histT.shift();Object.keys(hist).forEach(k=>hist[k].shift());
  }
}
function updRange(){const mr=document.getElementById('metrics-range');if(mr&&histT.length)mr.textContent='\u00b7 '+histT[0].slice(0,5)+' \u2013 '+histT[histT.length-1].slice(0,5);}
let prev={},logs=[];
const seedLogs=<?=json_encode($seedLogs, JSON_PRETTY_PRINT)?>;
if(seedLogs&&seedLogs.length)logs=seedLogs.slice().reverse();
const mlvl=Object.assign({load:'ok',cpu:'ok',ram:'ok',iow:'ok',webrt:'ok',dbrt:'ok',ssl:'ok',snap:'ok',swap:'ok',shmem:'ok',inode:'ok',raid:'ok',smart:'ok',mismatch:'ok',net:'ok',mysqlthr:'ok'},<?=json_encode($seedLvl)?>);
const mpend={};
function lvlOf(v,cr,hi){return v>=cr?'err':(v>=hi?'warn':'ok');}
function checkSnap(data,now){
  const sl=(data.procAge==null||data.procAge>180)?'err':'ok';
  if(sl!==mlvl.snap){
    if(sl==='err')addLog('err',data.procAge==null?'Root snapshot missing — cron down?':'Root snapshot stale ('+data.procAge+'s) — cron down?',now);
    else addLog('ok','Root snapshot fresh again ('+data.procAge+'s)',now);
    mlvl.snap=sl;
  }
}
function transLog(key,v,cr,hi,mErr,mWarn,mOk,now){
  const nl=lvlOf(v,cr,hi);
  if(nl===mlvl[key]){mpend[key]=null;return;}          // mevcut seviyede — beklemede bir şey varsa iptal
  if(!mpend[key]||mpend[key].lvl!==nl){mpend[key]={lvl:nl,n:1};return;} // yeni aday seviye — 1. gözlem
  if(++mpend[key].n<2)return;                          // henüz doğrulanmadı
  if(nl==='err')addLog('err',mErr,now);                // 2 ardışık tick (~60sn) — doğrulandı
  else if(nl==='warn')addLog('warn',mWarn,now);
  else if(mlvl[key]!=='ok')addLog('ok',mOk,now);
  mlvl[key]=nl;mpend[key]=null;
}

function scol(v,hi,cr,ok){return v>=cr?'var(--danger)':v>=hi?'var(--warn)':(ok||'var(--accent)');}
function lcol(v,t,ok){const r=v/Math.max(t,1);return r>=2.0?'var(--danger)':r>=1.0?'var(--warn)':(ok||'var(--accent)');}
function rtcol(ms){if(ms==null)return'var(--accent)';if(ms>=100)return'var(--danger)';if(ms>=30)return'var(--warn)';return'var(--accent)';}
// IO Wait kart metası — PHP şablonundaki $iowParts ile birebir aynı mantık
function iowMeta(d){const p=[];if(d.ioR!=null){p.push('R '+d.ioR,'W '+d.ioW);}if(d.dstate!=null)p.push(d.dstate+' blocked');return p.length?p.join(' · '):'Disk I/O pressure';}
// RAM/CPU kart metaları — PHP şablonuyla birebir aynı mantık
function ramMeta(d){if(d.memUsedGB==null)return d.ram+'% used';let s=d.memUsedGB+' / '+d.memTotalGB+' GB';if(d.shmemGB>=1){const c=d.shmemCol||'var(--hint)';s+=' · <span style="color:'+c+'">shmem '+d.shmemGB+' GB</span>';}if(d.swapTotalGB)s+=' · swap '+d.swapUsedGB+'/'+d.swapTotalGB+' GB';return s;}
function cpuMeta(d){let s='Load: '+d.load1.toFixed(2)+' / '+d.load5.toFixed(2)+' / '+d.load15.toFixed(2);if(d.rstate!=null||d.dstate!=null)s+=' · run '+(d.rstate||0)+' / blk '+(d.dstate||0);return s;}
function diskMeta(d){if(d.diskUsedGB==null)return d.disk+'% used';let s=d.diskUsedGB+' / '+d.diskTotalGB+' GB';if(d.inodePct!=null)s+=' · <span style="color:'+(d.inodeCol||'var(--hint)')+'">inode '+d.inodePct+'%</span>';if(d.raidTxt&&d.raidState!=='ok')s+=' · <span style="color:'+(d.raidCol||'var(--hint)')+'">'+esc(d.raidTxt)+'</span>';if(d.raidMismatch>0)s+=' · <span style="color:var(--warn)">'+d.raidMismatch+' mismatch</span>';if(d.smartTxt)s+=' · <span style="color:var(--danger)">'+d.smartTxt+'</span>';if(d.diskGrow)s+=' · '+d.diskGrow;return s;}
function push(a,v){a.push(v);if(a.length>MAX)a.shift();}
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
function pcls(v){v=parseFloat(v)||0;return v>=50?'hot':v>=20?'warm':'';}
function pmcls(v){v=parseFloat(v)||0;return v>=15?'hot':v>=5?'warm':'';}
function etimeS(t){const m=String(t||'').match(/^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/);return m?(+(m[1]||0))*86400+(+(m[2]||0))*3600+(+m[3])*60+(+m[4]):null;}
function ageShort(s){return s>=86400?Math.floor(s/86400)+'d':s>=3600?Math.floor(s/3600)+'h':Math.max(1,Math.floor(s/60))+'m';}
function fmtCount(n){return n>=1e6?(Math.round(n/1e5)/10)+'M':n>=1000?Math.round(n/1000)+'k':''+(n|0);}

function spark(id,data,color,W,H){
  const c=document.getElementById(id);if(!c)return;
  c._d=data.slice();
  const cW=W||c.offsetWidth||100,cH=H||c.offsetHeight||28;
  c.width=cW;c.height=cH;
  const ctx=c.getContext('2d');ctx.clearRect(0,0,cW,cH);
  if(data.length<2)return;
  const mn=Math.min(...data),mx=Math.max(...data),rng=mx-mn||1;
  const pts=data.map((v,i)=>({x:i*(cW/(data.length-1)),y:cH-2-((v-mn)/rng)*(cH-4)}));
  const col=color.startsWith('var(') ? getComputedStyle(document.documentElement).getPropertyValue(color.slice(4,-1).trim()).trim() : color;
  ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
  for(let i=1;i<pts.length;i++){const m=(pts[i-1].x+pts[i].x)/2;ctx.bezierCurveTo(m,pts[i-1].y,m,pts[i].y,pts[i].x,pts[i].y);}
  ctx.strokeStyle=col;ctx.lineWidth=1.5;ctx.stroke();
  const ss=document.getElementById('ssr-'+id.slice(3));if(ss)ss.remove();
  const l=pts[pts.length-1];ctx.beginPath();ctx.arc(l.x,l.y,2.5,0,Math.PI*2);ctx.fillStyle=col;ctx.fill();
  if(mx>mn){
    let mi=0;for(let i=1;i<data.length;i++)if(data[i]>data[mi])mi=i;
    if(mi!==pts.length-1){
      // Tepe: içi ÇİZGİ renginde dolu (her temada görünür), halkası kart
      // renginde — çizgiden ayrılsın. Eski "içi kart renginde" tasarım zemine
      // karışıp hiçbir temada seçilmiyordu.
      const mp=pts[mi],bg=(getComputedStyle(document.documentElement).getPropertyValue('--card')||'').trim()||'#fff';
      ctx.beginPath();ctx.arc(mp.x,mp.y,3,0,Math.PI*2);ctx.fillStyle=col;ctx.fill();ctx.strokeStyle=bg;ctx.lineWidth=1.5;ctx.stroke();
    }
  }
}

// Tema değişince tüm sparkline'ları güncel değerlerin renkleriyle yeniden çiz.
// Canvas tema geçişini kendiliğinden izlemez: tepe noktasının içi çizim
// anındaki --card ile doldurulur; yeniden çizilmezse eski temanın rengi kalır
// (koyu moda geçince "beyaz nokta" görünmesinin sebebi buydu).
function redrawSparks(){
  const t=init.t||1,L=k=>hist[k].length?hist[k][hist[k].length-1]:0;
  spark('sp-l1',hist.l1,lcol(L('l1'),t),80,32);
  spark('sp-l5',hist.l5,lcol(L('l5'),t),80,32);
  spark('sp-l15',hist.l15,lcol(L('l15'),t),80,32);
  spark('sp-cpu',hist.cpu,lastCardCol.cpu||scol(L('cpu'),80,90,'var(--c-cpu)'),70,24);
  spark('sp-ram',hist.ram,lastCardCol.ram||scol(L('ram'),70,85,'var(--c-ram)'),70,24);
  spark('sp-disk',hist.disk,lastCardCol.disk||scol(L('disk'),75,90,'var(--c-disk)'),70,24);
  spark('sp-iow',hist.iow,lastCardCol.iow||scol(L('iow'),8,15,'var(--c-iow)'),70,24);
  spark('sp-wrk',hist.wrk,'var(--accent)',64,30);
  spark('sp-rx',hist.rx,lastCardCol.rx||'var(--accent)',64,30);
  spark('sp-tx',hist.tx,lastCardCol.tx||'var(--accent)',64,30);
  spark('sp-mq',hist.mq,'var(--accent)',64,30);
}

// Sparkline hover tooltip — imlecin geldiği noktanın değerini gösterir
const tipEl=document.createElement('div');
tipEl.className='spark-tip';
document.body.appendChild(tipEl);
const sparkFmt={'sp-l1':v=>v.toFixed(2),'sp-l5':v=>v.toFixed(2),'sp-l15':v=>v.toFixed(2),
  'sp-cpu':v=>Math.round(v)+'%','sp-ram':v=>Math.round(v)+'%','sp-disk':v=>Math.round(v)+'%','sp-iow':v=>Math.round(v)+'%',
  'sp-rx':v=>Math.round(v)+' KB/s','sp-tx':v=>Math.round(v)+' KB/s','sp-wrk':v=>Math.round(v)+' running','sp-mq':v=>Math.round(v)+' msg'};
document.addEventListener('mousemove',e=>{
  const c=e.target.closest?e.target.closest('canvas.load-spark,canvas.res-spark,canvas.info-spark-canvas'):null;
  if(!c||!c._d||c._d.length<2){tipEl.style.opacity=0;return;}
  const r=c.getBoundingClientRect();
  const i=Math.max(0,Math.min(c._d.length-1,Math.round((e.clientX-r.left)/(r.width/(c._d.length-1)))));
  const f=sparkFmt[c.id]||(v=>v);
  const tm=histT[i];
  tipEl.innerHTML='<span class="tip-v">'+f(c._d[i])+'</span>'+(tm?'<span class="tip-t">'+esc(tm)+'</span>':'');
  tipEl.style.left=(e.clientX+10)+'px';
  tipEl.style.top=(e.clientY-40)+'px';
  tipEl.style.opacity=1;
});
document.addEventListener('mouseleave',()=>{tipEl.style.opacity=0;});

// Sorun renginde (danger/warn) kart kenarlığı da renklenir — sunucu render'ıyla
// (cardBorderCss) aynı davranış; sağlıklıyken kenarlık nötr kalır.
function isProblemCol(c){return c==='var(--danger)'||c==='var(--warn)';}
function setLoad(vid,cardId,sparkId,histKey,val,t){
  const color=lcol(val,t);
  const el=document.getElementById(vid);if(el){el.textContent=val.toFixed(2);el.style.color=color;}
  const card=document.getElementById(cardId);if(card){card.style.setProperty('--c',color);card.style.borderColor=isProblemCol(color)?color:'';}
  const pct=document.getElementById('p-'+histKey);
  if(pct)pct.textContent=Math.round(val/t*100)+'% of '+t+' cores';
  push(hist[histKey],val);spark(sparkId,hist[histKey],color,80,32);
}

function setRes(valId,cardId,barId,sparkId,metaId,histKey,val,color,meta){
  const ve=document.getElementById(valId);if(ve){ve.textContent=Math.round(val)+'%';ve.style.color=color;}
  const card=document.getElementById(cardId);if(card){card.style.setProperty('--c',color);card.style.borderColor=isProblemCol(color)?color:'';}
  const bf=document.getElementById(barId);if(bf){bf.style.width=Math.min(val,100)+'%';bf.style.background=color;}
  // innerHTML: meta içeriği bizim ürettiğimiz sayısal metin (RAM metasındaki
  // shmem renk span'i için). Değerler sayı, kullanıcı girdisi yok — güvenli.
  if(metaId&&meta!=null){const m=document.getElementById(metaId);if(m)m.innerHTML=meta;}
  push(hist[histKey],val);spark(sparkId,hist[histKey],color,70,24);
}

// Tepe durumu artık sunucuda birleşik sağlık modelinden gelir (data.overall):
// TÜM metrik/servis kontrollerinin en kötü seviyesi + sorun detayları. Eşik
// Sekme başlığı + favicon durumu yansıtır — arka plandaki sekmeden bakışta belli
// olsun. Favicon: durum renginde yuvarlak-kare + beyaz "A" (marka kimliği korunur);
// başlık: sorun varsa öne "Issues/Degraded" eklenir. Favicon yalnız renk DEĞİŞİNCE
// yeniden çizilir (canvas+toDataURL bedava ama gereksiz yere her tick yapılmaz).
const FAV_OK=<?=json_encode($FAVICON_URL)?>;            // config: favicon_url (boş olabilir)
const SITE_TITLE=<?=json_encode($SITE_TITLE)?>;         // config: site_title
const FAV_INITIAL=<?=json_encode(substr($INITIALS, 0, 1))?>; // sorunlu favicon harf fallback'i
let _favCol=null, _favImg=null, _favImgOk=false;
// Tek favicon link'i: yeni eklemek yerine sayfadaki mevcut <link rel="icon"> güncellenir.
function _favLink(){let l=document.querySelector('link[rel~="icon"]');if(!l){l=document.createElement('link');l.rel='icon';document.head.appendChild(l);}return l;}
// Sorunlu favicon: GERÇEK Ayzeta ikonu (rengi KORUNUR) + durum renginde çerçeve
// (turuncu/kırmızı) — ikonu beyazlatmaz, sadece etrafını boyar. Panel + ikon aynı
// origin (ayzeta.net) → canvas taint olmaz. İkon yüklenemezse (yerel test/taint)
// renkli kare + beyaz "A" güvenlik ağı.
(function(){if(!FAV_OK)return;_favImg=new Image();_favImg.onload=()=>{_favImgOk=true;if(_favCol==='var(--danger)'||_favCol==='var(--warn)')_paintProblemFav(_favCol);};_favImg.src=FAV_OK;})();
function _paintProblemFav(colorVar){
  const r=getComputedStyle(document.documentElement);
  const col=(colorVar==='var(--danger)'?r.getPropertyValue('--danger'):r.getPropertyValue('--warn')).trim()||'#f59e0b';
  // Favicon saydam olduğundan SADECE kenar boyamak ortayı beyaz bırakır. Bu yüzden
  // TÜM yuvarlak-kare zemini durum rengiyle doldurup gerçek "A"yı (rengi korunur)
  // üstüne basarız → "A" komple renkli zeminde durur. withImg=false: taint (yerel
  // test) durumunda ikon yerine beyaz "A" harfi — en azından durum belli olur.
  const draw=(withImg)=>{
    const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d');
    x.fillStyle=col; if(x.roundRect){x.beginPath();x.roundRect(2,2,60,60,14);x.fill();}else x.fillRect(2,2,60,60);
    if(withImg&&_favImgOk){x.drawImage(_favImg,9,9,46,46);}
    else{x.fillStyle='#fff';x.font='bold 42px Arial,system-ui';x.textAlign='center';x.textBaseline='middle';x.fillText(FAV_INITIAL||'!',32,36);}
    return c.toDataURL('image/png'); // taint ise throw eder
  };
  let href; try{href=draw(true);}catch(e){try{href=draw(false);}catch(_){href=FAV_OK;}}
  _favLink().href=href;
}
function setStatusIcon(colorVar, shortStatus){
  document.title=(shortStatus&&shortStatus!=='OK')?shortStatus+' · '+SITE_TITLE:SITE_TITLE;
  if(colorVar===_favCol)return;
  _favCol=colorVar;
  if(colorVar!=='var(--danger)'&&colorVar!=='var(--warn)'){if(FAV_OK)_favLink().href=FAV_OK;return;} // sağlıklı: gerçek favicon
  _paintProblemFav(colorVar);
}
// İlk yükte sunucu render'ındaki durumdan (ilk fetch'i beklemeden)
{const d=document.getElementById('hdr-dot'),s=document.getElementById('hdr-short');
 if(d&&s)setStatusIcon(d.style.background||'var(--ok)',s.textContent.trim());}

// mantığı tek yerde (PHP) yaşasın diye JS burada yeniden hesaplamaz, uygular.
function updateOverall(data){
  const o=data.overall; if(!o)return;
  const res=getComputedStyle(document.documentElement);
  const col=o.color==='var(--danger)'?res.getPropertyValue('--danger').trim()
           :o.color==='var(--warn)'  ?res.getPropertyValue('--warn').trim()
           :res.getPropertyValue('--ok').trim();
  const dot=document.getElementById('hdr-dot'),txt=document.getElementById('hdr-txt'),det=document.getElementById('hdr-detail'),sh=document.getElementById('hdr-short'),st=document.getElementById('hdr-status');
  const shortLbl=o.color==='var(--danger)'?'Issues':o.color==='var(--warn)'?'Degraded':'OK';
  if(dot)dot.style.background=col;
  if(txt)txt.textContent=o.status;
  if(sh)sh.textContent=shortLbl;
  if(det){if(o.detail){det.textContent=o.detail;det.style.display='';}else{det.style.display='none';}}
  setStatusIcon(o.color,shortLbl); // sekme başlığı + favicon durumu yansıtsın
  // Mobil dokun-aç: detay varsa rozet tıklanabilir; detay kalmayınca paneli kapat
  if(st){if(o.detail){st.classList.add('has-detail');}else{st.classList.remove('has-detail');st.classList.remove('st-open');}}
}

// Mobil: durum rozetine dokununca sorun detayları açılır panelde görünür
// (masaüstünde detay zaten satır içi; st-open kuralları yalnız mobil query'de).
(function(){
  const st=document.getElementById('hdr-status');
  if(!st)return;
  st.addEventListener('click',e=>{
    if(!st.classList.contains('has-detail'))return; // sorun yoksa açılmaz
    e.stopPropagation();
    st.classList.toggle('st-open');
  });
  document.addEventListener('click',()=>st.classList.remove('st-open')); // dışarı dokun → kapat
})();

let toastTimer;
function showToast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg;t.classList.add('show');
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),1800);
}
document.addEventListener('click',function(e){
  const btn=e.target.closest('.copy-btn');if(!btn)return;
  const cmd=btn.dataset.cmd;
  navigator.clipboard.writeText(cmd).then(()=>{
    btn.classList.add('copied');setTimeout(()=>btn.classList.remove('copied'),1500);
    showToast('Copied: '+cmd);
  }).catch(()=>{
    const ta=document.createElement('textarea');ta.value=cmd;
    document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);
    showToast('Copied: '+cmd);
  });
});

// Kesik komut/sorgu metnine dokun -> tam metin açılır (mobil için; hover yok)
document.addEventListener('click',function(e){
  const c=e.target.closest('.proc-cmd');
  if(c)c.classList.toggle('expanded');
});

// ── Tablo sıralama ────────────────────────────────────────────
// Başlığa tıkla: büyükten küçüğe, ikinci tıklama ters çevirir. 30sn
// yenilemede korunur (renderProcs sonunda reapplySort). Mail ekinde JS
// ölü olduğundan cron'un CPU/RAM sıralaması geçerli kalır.
const sortState={};
function sortVal(td){
  if(!td)return null;
  const t=td.textContent.trim();
  if(t===''||t==='—')return -Infinity;
  let m=t.match(/^([\d.]+)\s*(GB|MB|KB)$/i);          // RSS: "5.1 GB" / "386 MB"
  if(m)return parseFloat(m[1])*({KB:1,MB:1024,GB:1048576}[m[2].toUpperCase()]);
  m=t.match(/^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/);   // ps etime: [gün-][saat:]dk:sn
  if(m)return (+(m[1]||0))*86400+(+(m[2]||0))*3600+(+m[3])*60+(+m[4]);
  const n=parseFloat(t);
  return isNaN(n)?null:n;
}
function sortTable(tb,ci,dir){
  const rows=[...tb.querySelectorAll('tr')].filter(r=>!r.querySelector('.sql-empty'));
  rows.sort((a,b)=>{
    const va=sortVal(a.cells[ci]),vb=sortVal(b.cells[ci]);
    const c=(va!=null&&vb!=null)?va-vb
      :(a.cells[ci]?a.cells[ci].textContent.trim():'').localeCompare(b.cells[ci]?b.cells[ci].textContent.trim():'');
    return dir==='asc'?c:-c;
  });
  rows.forEach(r=>tb.appendChild(r));
}
function reapplySort(){
  for(const k in sortState){const tb=document.getElementById(k);if(tb)sortTable(tb,sortState[k].ci,sortState[k].dir);}
}
document.addEventListener('click',e=>{
  const th=e.target.closest('.proc-table th');if(!th)return;
  const tb=th.closest('table').querySelector('tbody');if(!tb||!tb.id)return;
  const ci=[...th.parentNode.children].indexOf(th);
  const cur=sortState[tb.id];
  const dir=(cur&&cur.ci===ci&&cur.dir==='desc')?'asc':'desc';
  sortState[tb.id]={ci,dir};
  th.parentNode.querySelectorAll('th').forEach(h=>h.classList.remove('sorted-asc','sorted-desc'));
  th.classList.add('sorted-'+dir);
  sortTable(tb,ci,dir);
});

function renderSvc(key,data){
  const s=data.status;
  const icon=document.getElementById('si-'+key),badge=document.getElementById('bd-'+key);
  const count=document.getElementById('sk-'+key),checks=document.getElementById('ch-'+key);
  if(icon){icon.style.background=s==='operational'?'var(--accent-bg)':s==='degraded'?'var(--warn-bg)':'var(--danger-bg)';icon.style.color=s==='operational'?'var(--accent)':s==='degraded'?'var(--warn)':'var(--danger)';}
  if(badge){badge.className='badge '+(s==='operational'?'badge-ok':s==='degraded'?'badge-warn':'badge-err');badge.textContent=s==='operational'?'Operational':s==='degraded'?'Degraded':'Offline';}
  if(count){const u={web:'checks passed',mail:'checks passed',dns:'checks passed',sec:'verified active',db:'checks passed',cache:'active',ftp:'checks passed'};count.textContent=data.ok+'/'+data.total+' '+(u[key]||'');}
  if(checks&&data.checks){
    checks.innerHTML=data.checks.map(ch=>{
      if(ch.type==='cmd'){
        return `<div class="sub-check"><span class="sub-dot muted"></span><span class="sub-lbl">${ch.label}</span><button class="copy-btn" data-cmd="${ch.cmd}" title="Copy"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button><code class="sub-cmd-inline">${ch.cmd}</code></div>`;
      }
      const age='<span class="sub-age"'+(ch.up?' title="up '+esc(ch.up)+'"':'')+'>'+(ch.upS?esc(ch.upS):'')+'</span>';
      const ver=ch.ver?'<span class="sub-ver" title="'+esc(ch.verT||ch.ver)+'">'+esc(ch.ver)+'</span>':'';
      return `<div class="sub-check"><span class="sub-dot ${ch.ok?'ok':'err'}"></span><span class="sub-lbl">${ch.label}${ver}</span><span class="sub-note${ch.warn?' note-warn':''}">${ch.note||''}</span>${age}</div>`;
    }).join('');
  }
}

let lastSnapMtime=<?=json_encode($procMtime)?>; // PHP render'ın damgası — ilk tick boşa kurmasın
let actWas=null; // aktivite çipleri durum izleme (null = henüz gözlem yok)
function renderProcs(data){
  if(!document.getElementById('proc-row'))return;
  const age=document.getElementById('proc-age');
  if(age&&data.procAge!=null){
    const stale=data.procAge>180;
    age.textContent=' · root snapshot, '+data.procAge+'s ago'+(stale?' — STALE (cron?)':'');
    age.className='proc-age'+(stale?' stale':'');
  }
  const thr=document.getElementById('sql-thr');
  // Değerler sayı + sabit renk anahtarı (kullanıcı girdisi yok) — innerHTML güvenli.
  if(thr)thr.innerHTML=data.mysqlThr!=null?' &middot; Threads_running: <span id="sql-thr-n" style="color:'+(data.mysqlThrCol||'var(--hint)')+'">'+data.mysqlThr+'</span>':'';
  const ac=document.getElementById('act-chips');
  if(ac&&data.procCpu){
    // Desen listesi PHP'deki $actDefs ile senkron; süre birincil olarak
    // data.acts'ten (cron, tüm süreç listesi), yoksa Top-15 taramasından.
    // minCpu: kalıcı daemon'ları eler (yoksa çip hiç sönmez).
    const defs=[['backup running',/pkgacct|cpbackup/i,0],['system update',/upcp|updatenow|dnf (upgrade|update)|yum (upgrade|update)/i,0],['wp-toolkit task',/wordpress-toolkit|wp-toolkit/i,15],['imunify scan',/im360\.run|aibolit|rustbolit/i,15]];
    const chips=defs.map(([lbl,re,minCpu],i)=>{
      // imunify artımlı = sürekli gürültü, gizle (sadece hesap taramasında göster)
      if(i===3&&data.actImunifyP==='incremental')return null;
      let mx=(data.acts&&data.acts[i]!=null)?data.acts[i]:null;
      if(mx==null)for(const p of data.procCpu){if((parseFloat(p[2])||0)<minCpu)continue;if(!re.test((p[1]||'')+' '+(p[5]||'')))continue;const s=etimeS(p[4]);if(s!=null&&(mx==null||s>mx))mx=s;}
      if(mx==null)return null;
      let c=lbl+' · '+ageShort(mx);
      if(i===3){ // imunify: hesap adı + varsa dosya sayısı
        if(data.actImunifyP&&data.actImunifyP!=='-')c+=' · '+esc(data.actImunifyP);
        if(data.actImunifyN>0)c+=' · '+fmtCount(data.actImunifyN)+' files';
      }
      return c;});
    ac.innerHTML=chips.filter(Boolean).map(c=>'<span class="bk-chip">'+esc(c)+'</span>').join('');
    // Başlangıç/bitiş Event log'a düşsün — pill gözden kaçsa da iz kalır.
    // İlk gözlemde sadece durum kaydedilir (sayfa açılışında sahte "started" olmasın).
    const st=chips.map(c=>c!=null?'1':'0').join('');
    if(actWas===null)actWas=st;
    else if(st!==actWas){
      defs.forEach(([lbl],i)=>{
        if(st[i]!==actWas[i])addLog('ok',lbl.replace(' running','')+(st[i]==='1'?' started':' finished'),data.time.split(' ')[1]);});
      actWas=st;
    }
  }
  // Snapshot değişmediyse tabloları yeniden kurma (genişletilmiş satırlar da korunur)
  if(data.snapMtime!=null&&data.snapMtime===lastSnapMtime)return;
  lastSnapMtime=data.snapMtime;
  const cpu=document.getElementById('pt-cpu');
  if(cpu&&data.procCpu)cpu.innerHTML=data.procCpu.map(p=>
    `<tr><td>${esc(p[0])}</td><td class="proc-user">${esc(p[1])}</td>`+
    `<td class="num ${pcls(p[2])}">${esc(p[2])}</td><td class="num ${pmcls(p[3])}">${esc(p[3])}</td>`+
    `<td>${esc(p[4])}</td><td class="td-fill"><span class="proc-cmd" title="${esc(p[5])}">${esc(p[5])}</span></td></tr>`).join('');
  const ram=document.getElementById('pt-ram');
  if(ram&&data.procRam)ram.innerHTML=data.procRam.map(p=>{
    const mc=pmcls(p[3]);
    return `<tr><td>${esc(p[0])}</td><td class="proc-user">${esc(p[1])}</td>`+
    `<td class="num ${mc}">${esc(p[3])}</td><td class="num ${mc}">${esc(p[4])}</td>`+
    `<td class="td-fill"><span class="proc-cmd proc-cmd-sm" title="${esc(p[5])}">${esc(p[5])}</span></td></tr>`;}).join('');
  const php=document.getElementById('pt-php');
  if(php&&data.procPhp){
    const mx=Math.max(1,...data.procPhp.map(p=>p[1]));
    php.innerHTML=data.procPhp.map(p=>{
      const c=p[1]>=10?'hot':p[1]>=5?'warm':'';
      const w=Math.round(p[1]/mx*100);
      return `<tr><td class="proc-user">${esc(p[0])}</td><td class="php-bar-cell"><span class="php-bar" style="width:${w}%"></span></td><td class="num ${c}">${p[1]}</td></tr>`;}).join('');
  }
  const dsk=document.getElementById('pt-disk'); // en dolu hesaplar (3. sütun, dikey tablo)
  if(dsk&&data.diskAcct&&data.diskAcct.length){
    const mx=Math.max(0.1,...data.diskAcct.map(p=>p[1]));
    const tot=data.diskTotalGB||0;
    dsk.innerHTML=data.diskAcct.map(p=>{
      const w=Math.round(p[1]/mx*100);
      const gb=(''+(Math.round(p[1]*10)/10)).replace(/\.0$/,'');
      const pct=tot>0?p[1]/tot*100:0,cls=pct>=3?'hot':pct>=1?'warm':''; // PHP diskAcctCls ile aynı
      return `<tr><td class="proc-user">${esc(p[0])}</td><td class="php-bar-cell"><span class="php-bar" style="width:${w}%"></span></td><td class="num ${cls}">${gb}</td></tr>`;}).join('');
  }
  const sqlMin=5; // $sqlMinSec ile aynı tutulmalı (cron 'time >= N')
  const sql=document.getElementById('pt-sql');
  if(sql&&data.procSql){
    sql.innerHTML=data.procSql.length?data.procSql.map(p=>{
      const c=parseInt(p[3])>=60?'hot':parseInt(p[3])>=10?'warm':'';
      return `<tr><td>${esc(p[0])}</td><td class="proc-user">${esc(p[1])}</td><td>${esc(p[2])}</td>`+
        `<td class="num ${c}">${esc(p[3])}</td><td>${esc(p[4])}</td>`+
        `<td class="td-fill"><span class="proc-cmd proc-cmd-sql" title="${esc(p[5])}">${esc(p[5])}</span></td></tr>`;}).join('')
    :'<tr><td colspan="6" class="sql-empty" style="color:var(--hint)">No queries running longer than '+sqlMin+'s at snapshot time</td></tr>';
  }
  reapplySort(); // tbody yeniden kurulunca kullanıcının seçtiği sıralamayı koru
}

function addLog(type,msg,ts){logs.unshift({type,msg,ts});if(logs.length>30)logs.pop();renderLog();}
function renderLog(){
  const el=document.getElementById('log-list');if(!el)return;
  if(!logs.length){el.innerHTML='<div style="font-size:11px;color:var(--hint);padding:6px 8px;">No events yet.</div>';return;}
  // msg + ts tek yerde escape (üreticiler artık ham metin verir) — XSS savunması
  el.innerHTML=logs.map(l=>`<div class="log-item"><div class="log-dot ${l.type==='err'?'err':l.type==='warn'?'warn':'ok'}"></div><span class="log-txt">${esc(l.msg)}</span><span class="log-ts">${esc(l.ts)}</span></div>`).join('');
}

function checkAlerts(data){
  const t=data.threads,now=data.time.split(' ')[1];
  // Şüpheli iliştirme (canlı): snapshot'ın top-CPU süreci. Alarm anı ile snapshot
  // anı 60-90sn ayrışabilir — yanıltmamak için sadece tazeyken eklenir ve
  // "(snap Xs)" yaş etiketi taşır. RAM'e eklenmez (top-CPU faili olmayabilir).
  let top='';
  if(data.procCpu&&data.procCpu.length&&data.procAge!=null&&data.procAge<=180){
    const p=data.procCpu[0],n=String(p[5]||'').split(' ')[0].split('/').pop(); // renderLog tek yerde escape eder
    if(n)top=' — top: '+n+' '+p[2]+'% (snap '+data.procAge+'s)';
  }
  transLog('load',data.load1/t,2.0,1.0,
    'High load: '+data.load1.toFixed(2)+' (1m)'+top,
    'Load elevated: '+data.load1.toFixed(2)+' (1m)'+top,
    'Load back to normal: '+data.load1.toFixed(2),now);
  transLog('cpu',data.cpu,90,80,
    'CPU critical: '+data.cpu+'%'+top,'CPU high: '+data.cpu+'%'+top,'CPU back to normal: '+data.cpu+'%',now);
  transLog('ram',data.ram,85,70,
    'RAM critical: '+data.ram+'%','RAM high: '+data.ram+'%','RAM back to normal: '+data.ram+'%',now);
  transLog('iow',data.iowait,15,8,
    'IO Wait critical: '+data.iowait+'%'+top,'IO Wait high: '+data.iowait+'%'+top,'IO Wait back to normal: '+data.iowait+'%',now);
  if(data.swapPct!=null&&data.swapTotalGB)transLog('swap',data.swapPct,50,10,
    'Swap heavily in use: '+data.swapUsedGB+' GB ('+data.swapPct+'%)','Swap in use: '+data.swapUsedGB+' GB ('+data.swapPct+'%)','Swap cleared',now);
  if(data.shmemPct!=null)transLog('shmem',data.shmemPct,55,40,
    'Shared memory very high: '+data.shmemGB+' GB ('+data.shmemPct+'% of RAM)','Shared memory elevated: '+data.shmemGB+' GB ('+data.shmemPct+'% of RAM)','Shared memory back to normal',now);
  if(data.inodePct!=null)transLog('inode',data.inodePct,90,80,
    'Inodes critically high: '+data.inodePct+'% (disk may fail despite free space)','Inode usage high: '+data.inodePct+'%','Inode usage back to normal',now);
  if(data.netRxSat!=null||data.netTxSat!=null){const ns=Math.max(data.netRxSat||0,data.netTxSat||0);
    transLog('net',ns,90,70,'Network link saturated: '+ns+'% of line rate','Network link busy: '+ns+'% of line rate','Network load back to normal',now);}
  if(data.mysqlThr!=null){const cc=data.coreCount||1;
    transLog('mysqlthr',data.mysqlThr,cc*2,cc,'MySQL threads_running very high: '+data.mysqlThr+' (query pileup)','MySQL threads_running elevated: '+data.mysqlThr,'MySQL threads_running back to normal',now);}
  if(data.raidState){const rl=data.raidState==='degraded'?'err':data.raidState==='resync'?'warn':'ok';
    if(rl!==mlvl.raid){
      if(rl==='err')addLog('err',data.raidTxt+' — a disk is down; replace before a second fails',now);
      else if(rl==='warn')addLog('warn',data.raidTxt+' — array rebuilding',now);
      else if(mlvl.raid!=='ok')addLog('ok','RAID array healthy again',now);
      mlvl.raid=rl;}}
  {const sl=data.smartMsg?'err':'ok';
   if(sl!==mlvl.smart){
     if(sl==='err')addLog('err',data.smartMsg,now);
     else if(mlvl.smart!=='ok')addLog('ok','SMART pre-failure cleared',now);
     mlvl.smart=sl;}}
  {const ml=data.raidMismatch>0?'warn':'ok';
   if(ml!==mlvl.mismatch){
     if(ml==='warn')addLog('warn','RAID mismatch count: '+data.raidMismatch+' — data inconsistency found in last scrub',now);
     else if(mlvl.mismatch!=='ok')addLog('ok','RAID mismatch cleared',now);
     mlvl.mismatch=ml;}}
  if(data.webResponseTime!=null)transLog('webrt',data.webResponseTime,100,100,
    'Web response time high: '+data.webResponseTime+'ms','',
    'Web response time normal: '+data.webResponseTime+'ms',now);
  if(data.mysqlResponseTime!=null)transLog('dbrt',data.mysqlResponseTime,100,100,
    'MySQL response time high: '+data.mysqlResponseTime+'ms','',
    'MySQL response time normal: '+data.mysqlResponseTime+'ms',now);
  if(data.sslDaysLeft!=null){
    const sl=data.sslDaysLeft<=7?'err':(data.sslDaysLeft<=30?'warn':'ok');
    if(sl!==mlvl.ssl){
      if(sl==='err')addLog('err','SSL expires in '+data.sslDaysLeft+' days!',now);
      else if(sl==='warn')addLog('warn','SSL expires in '+data.sslDaysLeft+' days',now);
      mlvl.ssl=sl;
    }
  }
  const names={web:'Web server',mail:'Mail',dns:'DNS',sec:'Security',db:'Database',cache:'Cache',ftp:'FTP'};
  ['web','mail','dns','sec','db','cache','ftp'].forEach(k=>{
    const cs=data[k]?data[k].status:null;if(!cs)return;
    if(prev[k]&&prev[k]!=='offline'&&cs==='offline')   addLog('err',names[k]+' went offline',now);
    if(prev[k]==='offline'&&cs!=='offline')             addLog('ok', names[k]+' restored',now);
    if(prev[k]==='operational'&&cs==='degraded')        addLog('warn',names[k]+' degraded',now);
    prev[k]=cs;
  });
}

// Ortak metrik render'ı — render + renderMetrics'in TEK kaynağı (eskiden ikisinde
// birebir kopyaydı, biri değişince diğeri unutulur riskiydi). Başlık meta + load +
// kaynak kartları (birleşik sağlık renkleriyle) + Network IN/OUT. render bunun üstüne
// info-şerit + servis kartları + updateOverall + checkAlerts ekler.
function applyMetrics(data){
  document.getElementById('hostname').textContent=data.hostname;
  document.getElementById('threads').textContent=data.threads;
  document.getElementById('uptime').textContent=data.uptime||'—';
  document.getElementById('time-val').textContent=data.time.split(' ')[1];
  document.getElementById('footer-time').textContent=data.time+(data.vers&&data.vers.kernel?' · '+data.vers.kernel:'');
  pushT(data.time.split(' ')[1]);
  trimHist(data.time.split(' ')[1]);
  updRange();
  const t=data.threads;
  setLoad('v-l1','lc-l1','sp-l1','l1',data.load1,t);
  setLoad('v-l5','lc-l5','sp-l5','l5',data.load5,t);
  setLoad('v-l15','lc-l15','sp-l15','l15',data.load15,t);
  // Kart renkleri sunucudaki birleşik sağlık modelinden (data.cardCol): disk
  // kartı RAID/SMART/inode sorununda da kızarır, %'si düşük olsa bile. Snapshot
  // eksikse metriğin kendi eşik rengine düşülür; redrawSparks (tema) için stash.
  const cc=data.cardCol||{};
  lastCardCol={cpu:cc.cpu||scol(data.cpu,80,90,'var(--c-cpu)'),ram:cc.ram||scol(data.ram,70,85,'var(--c-ram)'),disk:cc.disk||scol(data.disk,75,90,'var(--c-disk)'),iow:cc.iow||scol(data.iowait,8,15,'var(--c-iow)'),rx:data.netRxCol||'var(--accent)',tx:data.netTxCol||'var(--accent)'};
  setRes('rv-cpu','rc-cpu','rb-cpu','sp-cpu','rm-cpu','cpu',data.cpu,lastCardCol.cpu,cpuMeta(data));
  setRes('rv-ram','rc-ram','rb-ram','sp-ram','rm-ram','ram',data.ram,lastCardCol.ram,ramMeta(data));
  setRes('rv-disk','rc-disk','rb-disk','sp-disk','rm-disk','disk',data.disk,lastCardCol.disk,diskMeta(data));
  setRes('rv-iow','rc-iow','rb-iow','sp-iow','rm-iow','iow',data.iowait,lastCardCol.iow,iowMeta(data));
  // Network IN/OUT: değer + spark + alt-etiket, hat doygunluğuna göre renkli
  {const c=data.netRxCol||'var(--accent)',e=document.getElementById('iv-rx'),s=document.getElementById('iv-rx-sub');
   if(e&&data.rxRate){e.textContent=data.rxRate;e.style.color=c;}
   if(s)s.textContent=data.netRxSat!=null?data.netRxSat+'% of link':'incoming traffic';
   if(data.rxK!=null){push(hist.rx,data.rxK);spark('sp-rx',hist.rx,c,64,30);}}
  {const c=data.netTxCol||'var(--accent)',e=document.getElementById('iv-tx'),s=document.getElementById('iv-tx-sub');
   if(e&&data.txRate){e.textContent=data.txRate;e.style.color=c;}
   if(s)s.textContent=data.netTxSat!=null?data.netTxSat+'% of link':'outgoing traffic';
   if(data.txK!=null){push(hist.tx,data.txK);spark('sp-tx',hist.tx,c,64,30);}}
}
// Servis beslemesi yok (snapshot bayat) — metrik + süreç + TEPE DURUMU güncel kalsın
// (favicon/başlık dahil); servis kartları + canlı alertler atlanır (yanlış servis
// alarmı üretmemek için).
function renderMetrics(data){
  applyMetrics(data);
  renderProcs(data);
  updateOverall(data);
}

function render(data){
  applyMetrics(data); // başlık meta + load + kaynak kartları + Network IN/OUT (ortak)
  const ew=document.getElementById('iv-web');
  if(ew){ew.textContent=data.webResponseTime!=null?data.webResponseTime+' ms':'—';ew.style.color=rtcol(data.webResponseTime);}
  const em=document.getElementById('iv-mysql');
  if(em){em.textContent=data.mysqlResponseTime!=null?data.mysqlResponseTime+' ms':'—';em.style.color=rtcol(data.mysqlResponseTime);}
  if(data.acctCount!=null){const e=document.getElementById('iv-acct');if(e)e.textContent=data.acctCount;}
  {const e=document.getElementById('iv-mailq');if(e){const q=data.mailQ,b=data.acctForMailq||50;e.textContent=q!=null?q:'—';e.style.color=q==null?'var(--muted)':q>=b*3?'var(--danger)':q>=b*1?'var(--warn)':'var(--accent)';}}
  {const q=data.mqRaw;if(q!=null){push(hist.mq,q);spark('sp-mq',hist.mq,'var(--accent)',64,30);}}
  if(data.lsphpIdle!=null)lsphpIdle=data.lsphpIdle;
  {const s=document.getElementById('iv-lsphp-sub');if(s)s.innerHTML=data.lsphpIdle!=null?'active &middot; '+data.lsphpIdle+' idle':'running lsphp';}
  {const e=document.getElementById('iv-lsphp');if(e){const n=data.lsphpTotal,c=data.coreCount||1;e.textContent=n!=null?n:'—';e.style.color=n==null?'var(--muted)':n>=c*2?'var(--danger)':n>=c?'var(--warn)':'var(--accent)';}}
  {const n=data.lsphpTotal;if(n!=null){push(hist.wrk,n);spark('sp-wrk',hist.wrk,'var(--accent)',64,30);}}
  if(data.sslDaysLeft!=null){
    const e=document.getElementById('iv-ssl'),s=document.getElementById('iv-ssl-sub');
    const col=data.sslDaysLeft<=7?'var(--danger)':data.sslDaysLeft<=30?'var(--warn)':'var(--accent)';
    if(e){e.textContent=data.sslDaysLeft+' days';e.style.color=col;}
    if(s&&data.sslExpiry)s.textContent=data.sslExpiry;
  }
  ['web','mail','dns','sec','db','cache','ftp'].forEach(k=>{if(data[k])renderSvc(k,data[k]);});
  renderProcs(data);
  updateOverall(data);
  checkAlerts(data);
}

let whmWasDown=false;

async function fetchWithRetry(url, retries=2, delay=2000){
  for(let i=0; i<=retries; i++){
    try{
      const r=await fetch(url);
      if(r.ok) return await r.json();
    }catch(e){}
    if(i<retries) await new Promise(res=>setTimeout(res,delay));
  }
  return null;
}

let lastFetch=0;
async function tick(){
  lastFetch=Date.now();
  const data=await fetchWithRetry(window.location.pathname+'?json=1&_='+Date.now());

  if(!data){
    // Fetch tamamen başarısız — ağ sorunu
    if(!whmWasDown){
      whmWasDown=true;
      addLog('err','Server unreachable',new Date().toTimeString().slice(0,8));
    }
    return;
  }

  const now=data.time.split(' ')[1];
  checkSnap(data,now);

  if(!data.whmApiOk){
    // Sayfa geldi ama servis beslemesi yok (taze snapshot da API de yok)
    renderMetrics(data);
    if(!whmWasDown){
      whmWasDown=true;
      addLog('warn','Service feed unavailable (root snapshot stale?)',now);
    }
    return;
  }

  // Her şey normal
  if(whmWasDown){
    addLog('ok','Service feed restored',now);
    whmWasDown=false;
  }
  render(data);
}

document.getElementById('log-clear-btn').addEventListener('click',()=>{logs=[];renderLog();});
renderLog();

// İlk açılışta sparkline'ları cron geçmişi + anlık değerle çiz
(function(){
  pushT(init.time);
  trimHist(init.time);
  updRange();
  push(hist.l1,init.l1);push(hist.l5,init.l5);push(hist.l15,init.l15);
  push(hist.cpu,init.cpu);push(hist.ram,init.ram);push(hist.disk,init.disk);push(hist.iow,init.iow);push(hist.wrk,init.wrk);push(hist.rx,init.rx);push(hist.tx,init.tx);push(hist.mq,init.mq);
  spark('sp-l1',hist.l1,lcol(init.l1,init.t),80,32);
  spark('sp-l5',hist.l5,lcol(init.l5,init.t),80,32);
  spark('sp-l15',hist.l15,lcol(init.l15,init.t),80,32);
  spark('sp-cpu',hist.cpu,scol(init.cpu,80,90,'var(--c-cpu)'),70,24);
  spark('sp-ram',hist.ram,scol(init.ram,70,85,'var(--c-ram)'),70,24);
  spark('sp-disk',hist.disk,scol(init.disk,75,90,'var(--c-disk)'),70,24);
  spark('sp-iow',hist.iow,scol(init.iow,8,15,'var(--c-iow)'),70,24);
  spark('sp-wrk',hist.wrk,'var(--accent)',64,30);
  spark('sp-rx',hist.rx,lastCardCol.rx||'var(--accent)',64,30);
  spark('sp-tx',hist.tx,lastCardCol.tx||'var(--accent)',64,30);
  spark('sp-mq',hist.mq,'var(--accent)',64,30);
})();

if(location.protocol==='file:'){
  // CSF mail eki olarak açıldı — canlı yenileme yapılamaz, statik görüntü
  document.body.classList.add('static-mode');
  const ul=document.getElementById('updated-lbl');if(ul)ul.textContent='Snapshot';
  const fm=document.getElementById('footer-mode');if(fm)fm.textContent='Static snapshot (mail attachment)';
  addLog('warn','Static snapshot (mail attachment) — live refresh disabled',
         new Date().toTimeString().slice(0,8));
}else{
  tick();
  setInterval(tick,30000);
  // Mobil/arka plan dayanıklılığı: tarayıcı arka plandaki sekmenin canvas'ını
  // bellekten atabilir (geri dönünce grafikler BOŞ görünür) ve 30sn timer'ı
  // dondurur (ilk hareket bir sonraki tick'e kadar gelmez). Sekme tekrar
  // görünür olunca: (1) hafızadaki hist'ten ANINDA yeniden çiz (ağ beklemeden),
  // (2) veri bayatsa (>15sn) hemen tazele. redrawSparks bedava (yalnız canvas).
  const onVisible=()=>{
    if(document.visibilityState!=='visible')return;
    const gap=Date.now()-lastFetch;
    // Uzun ara (>5dk): canlı geçmiş 30dk penceresinden düşmüş/bayatlamış olur →
    // trimHist boşaltır, grafikler "sıfırdan" çizer. 30dk'lık gerçek geçmiş sadece
    // tam yüklemede (cron seed) gelir; o yüzden yeniden yükleyip hazır getiririz.
    if(gap>300000){location.reload();return;}
    redrawSparks();                 // kısa ara: hafızadan anında çiz (ağ beklemeden)
    if(gap>15000)tick();            // bayatsa hemen tazele
  };
  document.addEventListener('visibilitychange',onVisible);
  window.addEventListener('pageshow',e=>{if(e.persisted)onVisible();});
}
</script>
</body>
</html>