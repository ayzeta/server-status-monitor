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
| cPanel & WHM | 138.0.15 (2026-10-08) |
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

## Review log

**2026-10-19** — cPanel 138 series through 138.0.15 and CSF through 16.33-1.
Nothing that required a change.

**CSF 16.33-1 (2026-10-08)** — *package upgrades no longer leave the firewall
unloaded.* The firewall indicator could not see that state: it only looked at
`csf.disable`. Since 1.5.28 it works through missing / off / testing / norules /
ok in order, and reports `unknown` when it cannot read — which counts as "not a
problem" rather than an alarm. Bad news needs two consecutive samples, because
the rule chain is briefly absent while CSF reloads.
