# Compatibility

The dashboard reads cPanel's and CSF's own files and commands, so a change in
either can quietly turn a card blank. This file records what it depends on and
which releases it has been checked against.

**How it is maintained:** before work on this repo, every cPanel & WHM and CSF
changelog entry published after the last date in the review log is read — not
just the newest one. If an entry touches anything listed below, the effect is
verified in the code (and, where needed, with a read-only command on a real
server) rather than assumed. The log is updated either way.

Sources:
[cPanel & WHM change log](https://docs.cpanel.net/changelogs/138-change-log/) ·
[CSF change log](https://docs.cpanel.net/changelogs/configserver-security-firewall-csf-change-log/).
ConfigServer closed in August 2025; cPanel has maintained CSF as its own fork
since February 2026 and announces it on that separate page, so the two are read
separately.

## Checked against

| | Read through |
|---|---|
| cPanel & WHM | 138.0.19 (2026-10-26) |
| CSF | 16.33-1 (2026-10-08) |

Older and newer releases are not excluded — these are simply the ones whose
notes have been reviewed.

## What a change can affect

**cPanel** — `whmapi1 servicestatus` (service names and output fields), the
version file `/usr/local/cpanel/version`, the `/var/cpanel/users/` format,
`/var/cpanel/whm_server_status_key` and the Apache/LiteSpeed status page, exim
(`exim -bpc`, `exim -bV`) and the mail queue, the ModSecurity configuration
(`modsec2.cpanel.conf`), PHP-FPM / EA-PHP versions, disk quota and account
accounting, the tool paths under `/usr/local/cpanel/3rdparty/bin`, and the
Imunify360 CLI (`imunify360-agent version`, `malware`).

**CSF** — `csf.conf` (notably `PT_APACHESTATUS`), `csf.disable`, and the lfd
service state.

**LiteSpeed "Cache Redis for Users"** — this is a feature of the WHM LiteSpeed
plugin: one Redis instance per account, reachable only through a socket inside
the account's caged `tmp` directory, so it needs CageFS or LiteSpeed
Containers. Its unit template and start script live under `/usr/local/lsws/`
and belong to no RPM, because the plugin writes them itself. The dashboard
reads the per-account cache from three shapes, none of them probed over the
network.

How many instances are *meant* to run comes from the unit names
`/etc/systemd/system/multi-user.target.wants/user-redis@<account>.service`.

How many actually run, and the memory they hold, come from the process table,
where each instance is matched by the **user column**: the unit runs with
`User=%i`, so the process owner is the account itself. The command line is not
used, because it does not carry the socket: a running instance shows up as
`/usr/bin/redis-server *:0`, with neither the socket path nor `--unixsocket` in
its arguments — the unit's own start script passes those. (An earlier version
of this dashboard matched on the socket path in the arguments; nothing matched,
and a healthy server was reported as entirely down. The `*:0` form is also what
tells these instances apart from the shared Redis, which listens on a real
address and port.)

How many accounts actually use the cache comes from the `db0`, `db1`… lines of
an `INFO keyspace` reply over that socket — Redis is the only source for this,
since the configuration LiteSpeed recommends (`save ""`, `appendonly no`)
leaves nothing on disk to inspect. The reply says how many databases hold keys,
not what wrote to them, so that is all the dashboard claims.

If the unit template is renamed, the socket moves out of the caged `tmp`
directory, or the unit stops running as the account, the card loses its numbers
silently — the denominator is then omitted rather than guessed.

## Review log

**2026-11-01** — cPanel 138.0.17, 138.0.18 and 138.0.19; CSF unchanged at
16.33-1. Nothing that required a change. Three entries sat close enough to the
dashboard to be checked in the code rather than waved off: the hourly
`upcp --security` cron no longer mails its output (CPANEL-56561) — the update
detector matches the running process, not the mail, so it still sees the run; a
save of the nftables configuration was dropping the SMTP restriction tables
(CPANEL-57809) — the firewall check asks CSF's own `LOCALINPUT` chain, a
different ruleset; and the cpsrvd "proxy trust miss" log line changed shape
(CPANEL-57789) — that log is never parsed here, cpsrvd is read as a process
name and a port. The rest were package updates (Roundcube, php84, libzip,
unbound) and unrelated UI fixes.

**2026-10-19** — cPanel 138 series through 138.0.15 and CSF through 16.33-1.
Nothing that required a change.

**CSF 16.33-1 (2026-10-08)** — *package upgrades no longer leave the firewall
unloaded.* The firewall indicator could not see that state: it only looked at
`csf.disable`. Since 1.5.28 it works through missing / off / testing / norules /
ok in order, and reports `unknown` when it cannot read — which counts as "not a
problem" rather than an alarm. Bad news needs two consecutive samples, because
the rule chain is briefly absent while CSF reloads.
