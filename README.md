# Server Status Monitor

A single-file, real-time infrastructure dashboard for **cPanel / CloudLinux**
servers. Load, CPU, RAM, disk, IO wait, network saturation, RAID/SMART health,
services, top processes, per-account disk & PHP workers, and a live event log —
all on one auto-refreshing page, with **zero dependencies** (no database, no npm,
no external services).

Because PHP runs jailed under CageFS and can't see the full process list or
`/sys`, a tiny **root cron collector** gathers that data once a minute and hands
it to the dashboard. Everything else is computed by the page itself.

> The page also renders as a **static HTML email** (e.g. CSF's high-load alert
> attachment): every alarm is server-rendered, and no output line exceeds the
> SMTP 900-byte limit.

---

## Features

- **Unified health model** — one status in the header (`All systems operational`
  / `Degraded` / `Issues detected`) aggregated from *every* metric and service,
  with the actual offenders listed inline. Tab title + favicon reflect it too.
- **Proportional thresholds** — load is scaled to core count, CPU/RAM/disk are
  percentages, network is % of link speed. Sensible on any server, not tuned to
  one box.
- **Network line saturation** — each interface measured against its own link
  speed (max, not sum), so an idle NIC never masks a saturated one.
- **RAID / SMART / inode / mismatch** alarms, shown on the disk card *and* the
  event log (mail-safe).
- **Live event log** with 2-tick confirmation (no flapping) + server-seeded
  history from the last 30 minutes.
- **Mobile-friendly** and **light/dark** aware.
- **Drop-in for CSF & WHMCS** — works as CSF's high-load status page on LiteSpeed
  servers (which have no Apache `mod_status`) and as a WHMCS *Server Status*
  endpoint. See [Integrations](#integrations).

## Requirements

- cPanel / CloudLinux server (root access for the cron collector).
- PHP 7.4+ served for the web account (defaults work; no extensions required
  beyond `posix` for user auto-detect).
- Optional tools are feature-detected: `smartctl`, `mdadm`/`/proc/mdstat`,
  `imunify360-agent`, `csf`, `repquota`. Missing ones are silently skipped.

## Where to host it

This is a **server** dashboard, not a website — but on cPanel a PHP page must
still be served from an account's docroot, and (because of CageFS) the root
collector must drop its feed into that account's home. So point it at a
**dedicated account or subdomain** (e.g. `status.example.com` or a small
`monitor` cPanel user) rather than your live site — the installer asks which
account to use. That keeps your main site's home clean and the panel isolated.

## Install (recommended)

```bash
git clone https://github.com/ayzeta/server-status-monitor.git
cd server-status-monitor
sudo bash install.sh
```

The installer asks for the web account, paths, and branding, then:

1. deploys `src/collector.sh` → `DATA_DIR` (root, `chmod 700`) + writes `config.env`,
2. deploys `src/index.php` → `~<user>/public_html/status/` + writes `config.php`,
3. installs the root cron (every minute) and wires the root→web-user feed,
4. primes the collector and prints the dashboard URL.

Re-run it any time to change settings (answers are remembered).

## Manual install

```bash
# Collector (as root)
mkdir -p /root/server-status-monitor
cp src/collector.sh /root/server-status-monitor/ && chmod 700 /root/server-status-monitor/collector.sh
cp config.env.example /root/server-status-monitor/config.env   # set WEB_USER
( crontab -l 2>/dev/null; echo '* * * * * /root/server-status-monitor/collector.sh >/dev/null 2>&1' ) | crontab -

# Dashboard (in the web account)
cp src/index.php   ~USER/public_html/status/index.php
cp config.php.example ~USER/public_html/status/config.php      # set branding
chown USER:USER ~USER/public_html/status/index.php ~USER/public_html/status/config.php
```

## Configuration

Two small, optional files (the installer writes both):

- **`config.php`** (next to `index.php`) — branding + `web_user`. See
  [`config.php.example`](config.php.example). The dashboard runs with defaults
  if it's missing.
- **`config.env`** (next to `collector.sh`) — `WEB_USER` (required) + `DATA_DIR`.
  See [`config.env.example`](config.env.example).

## Integrations

### CSF high-load alerts (LiteSpeed / no Apache mod_status)

ConfigServer Firewall (CSF) can attach a live server-status page to its
high-load alert emails — but it fetches Apache's `mod_status`, which
**LiteSpeed / OpenLiteSpeed** servers don't provide. Point CSF at this dashboard
instead. In `/etc/csf/csf.conf`:

```
PT_APACHESTATUS = "https://status.example.com/"
```

When load crosses `PT_LOAD`, CSF fetches that URL and includes it in the alert.
Because the dashboard renders every alarm **server-side** and keeps every output
line under the SMTP **900-byte** limit, it arrives intact as a readable HTML
attachment — no JavaScript required.

### WHMCS Server Status

Point a server's **Status Address** (WHM &rarr; *Products/Services &rarr;
Servers &rarr; Edit &rarr; Server Status Address*) to the `?raw=1` endpoint:

```
https://status.example.com/?raw=1
```

It returns the `<load>` and `<uptime>` tags WHMCS's **Server Status** page reads
(WHMCS still runs its own HTTP/FTP/POP3 socket checks). One dashboard now feeds
your firewall alerts, your billing panel, and your own eyes.

## How it works

```
root cron ── collector.sh ──▶ /home/<user>/.proc_snapshot   (chown <user>, 0640)
(every min)                   /home/<user>/.metrics_history  (30-min ring)
                                        │
web account ── index.php ◀──────────────┘  reads the feed, renders + ?json=1 tick
```

- The collector writes to the web user's home and `chown`s it, so the jailed PHP
  can read it. No world-readable root files.
- The dashboard renders server-side (also for the email attachment) and refreshes
  every 30 s via `?json=1`. The same thresholds live in PHP and JS, kept in sync.

## Thresholds (defaults)

| Metric | warn | critical |
|--------|------|----------|
| Load   | ≥ 1.0× cores (at capacity) | ≥ 2.0× cores (overloaded) |
| CPU    | 80% | 90% |
| RAM    | 70% | 85% |
| Disk   | 75% | 90% |
| IO Wait| 8%  | 15% |
| Network| 70% of link | 90% of link |
| Inode  | 80% | 90% |

Load is orange at capacity (a fully-used server isn't "broken") and red only
when genuinely overloaded, so red stays meaningful.

## Uninstall

```bash
crontab -l | grep -v 'collector.sh' | crontab -
rm -rf /root/server-status-monitor
rm -f ~USER/public_html/status/index.php ~USER/public_html/status/config.php
rm -f ~USER/.proc_snapshot ~USER/.metrics_history ~USER/.disk_history
```

## License

MIT — see [LICENSE](LICENSE).
