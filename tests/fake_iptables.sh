#!/bin/sh
# Sahte iptables. Davranis CALISTIRMA aninda $IPT_MODE ile secilir:
#   ok    -> zincir var (cikis 0)
#   perm  -> yetki hatasi (stderr'de Permission denied, cikis 4)
#   diger -> zincir yok (stderr'de No chain, cikis 1)
case "$IPT_MODE" in
  ok)   exit 0 ;;
  perm) echo "iptables: Permission denied (you must be root?)" >&2; exit 4 ;;
  *)    echo "iptables: No chain/target/match by that name." >&2; exit 1 ;;
esac
