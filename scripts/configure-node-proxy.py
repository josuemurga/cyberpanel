#!/usr/bin/env python3
"""SOFTI: idempotent OLS reverse proxy for a Softi Node app."""
import argparse
import os
import sys

sys.path.insert(0, "/usr/local/CyberCP")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CyberCP.settings")


def main():
    parser = argparse.ArgumentParser(description="Configure Softi Node OLS proxy")
    parser.add_argument("domain")
    parser.add_argument("port", type=int)
    parser.add_argument("--app-name", default="app")
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--restart", action="store_true", default=True)
    args = parser.parse_args()

    from plogical import softiNodeProxy

    if args.remove:
        ok, msg = softiNodeProxy.remove(args.domain, restart=args.restart)
    else:
        ok, msg = softiNodeProxy.configure(
            args.domain, args.port, app_name=args.app_name, restart=args.restart
        )
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
