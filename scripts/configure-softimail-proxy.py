#!/usr/bin/env python3
"""
SOFTI — Configura proxy SoftiMail (SnappyMail) en vhosts webmail.*.

Cada sitio recibe un extprocessor único:
  snappymail_webmail_ejemplo_com → https://cyberpanel.softi.host:8090/snappymail

Uso:
  python3 /usr/local/CyberCP/scripts/configure-softimail-proxy.py
  python3 /usr/local/CyberCP/scripts/configure-softimail-proxy.py webmail.moralestechs.com
  python3 /usr/local/CyberCP/scripts/configure-softimail-proxy.py --backend https://cyberpanel.softi.host:8090
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/usr/local/CyberCP")

from plogical.softiWebmailProxy import configure, configure_all  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Configure SoftiMail OLS proxy for webmail.*")
    p.add_argument("domain", nargs="?", help="Single webmail.* domain (default: all)")
    p.add_argument(
        "--backend",
        default=None,
        help="Upstream SnappyMail base (default: https://cyberpanel.softi.host:8090)",
    )
    p.add_argument("--no-restart", action="store_true", help="Do not restart LiteSpeed")
    args = p.parse_args()

    restart = not args.no_restart
    if args.domain:
        ok, msg = configure(args.domain, backend=args.backend, restart=restart)
        print(msg)
        return 0 if ok else 1

    for line in configure_all(restart=restart):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
