# -*- coding: utf-8 -*-
"""
SOFTI-MEJORA — SoftiMail reverse proxy for webmail.* vhosts.

Each site gets a unique OpenLiteSpeed extprocessor name so rewrite [P]
targets cannot collide across vhosts (LiteSpeed resolves the hostname in
RewriteRule http(s)://NAME/... to extprocessor NAME).

Proxy rules live in .htaccess (directory context, no leading slash) — same
pattern as cyberpanel.softi.host → HTTP://cyberpanel/$1 [P]. Vhost only
enables rewrite + autoLoadHtaccess and declares the unique extprocessor.

Backend MUST be HTTPS: lscpd:8090 redirects HTTP→HTTPS and breaks [P].
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from plogical import CyberCPLogFileWriter as logging

SNAPPY_BACKEND = os.environ.get(
    "SOFTI_SNAPPYMAIL_BACKEND", "https://cyberpanel.softi.host:8090"
)
ACME_CHALLENGE_ROOT = "/usr/local/lsws/Example/html/.well-known/acme-challenge"
VHOST_ROOT = Path("/usr/local/lsws/conf/vhosts")


def is_softimail_webmail_domain(domain: str) -> bool:
    d = (domain or "").strip().lower()
    return d.startswith("webmail.")


def processor_name(domain: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", domain.strip().lower()).strip("_")
    return f"snappymail_{safe}"


def _rewrite_scheme(backend: str) -> str:
    return "https" if backend.lower().startswith("https://") else "http"


def _vhost_rewrite_enable_only() -> str:
    return (
        "rewrite  {\n"
        " enable                  1\n"
        "  autoLoadHtaccess        1\n"
        "}\n"
    )


def _extprocessor_block(name: str, backend: str) -> str:
    return (
        f"\nextprocessor {name} {{\n"
        "  type                    proxy\n"
        f"  address                 {backend}\n"
        "  maxConns                100\n"
        "  initTimeout             60\n"
        "  retryTimeout            0\n"
        "  respBuffer              0\n"
        "  pcKeepAliveTimeout      60\n"
        "}\n"
    )


def _acme_context_block() -> str:
    return (
        "\ncontext /.well-known/acme-challenge {\n"
        f"  location                {ACME_CHALLENGE_ROOT}\n"
        "  allowBrowse             1\n"
        "\n"
        "  rewrite  {\n"
        "     enable                  0\n"
        "  }\n"
        "  addDefaultCharset       off\n"
        "\n"
        "  phpIniOverride  {\n"
        "\n"
        "  }\n"
        "}\n"
    )


def _write_htaccess(domain: str, name: str, backend: str) -> None:
    """Directory-context [P] rules (no leading slash). Unique processor per site."""
    public = Path(f"/home/{domain}/public_html")
    if not public.is_dir():
        return
    scheme = _rewrite_scheme(backend)
    ht = public / ".htaccess"
    ht.write_text(
        "### Softi SoftiMail: unique extprocessor + HTTPS upstream (lscpd:8090)\n"
        "RewriteEngine On\n"
        "RewriteCond %{REQUEST_URI} !^/\\.well-known/acme-challenge/\n"
        "RewriteCond %{HTTPS} !=on\n"
        "RewriteRule ^/?(.*) https://%{SERVER_NAME}/$1 [R,L]\n"
        "\n"
        "# Preserve /snappymail/* asset paths from SoftiMail HTML\n"
        "RewriteCond %{REQUEST_URI} !^/\\.well-known/acme-challenge/\n"
        f"RewriteRule ^snappymail/(.*) {scheme}://{name}/snappymail/$1 [P,L]\n"
        "\n"
        "# Site root → SoftiMail app\n"
        "RewriteCond %{REQUEST_URI} !^/\\.well-known/acme-challenge/\n"
        f"RewriteRule ^(.*) {scheme}://{name}/snappymail/$1 [P,L]\n"
    )


def configure(domain: str, backend: Optional[str] = None, restart: bool = False) -> Tuple[int, str]:
    """Idempotent: unique extprocessor + htaccess [P] rewrite for SoftiMail."""
    try:
        domain = (domain or "").strip()
        if not is_softimail_webmail_domain(domain):
            return 0, f"not a webmail.* SoftiMail domain: {domain}"

        vh = VHOST_ROOT / domain / "vhost.conf"
        if not vh.is_file():
            return 0, f"missing vhost.conf: {vh}"

        name = processor_name(domain)
        backend = (backend or SNAPPY_BACKEND).rstrip("/")
        text = vh.read_text()

        # Drop prior Softi SoftiMail proxy bits (keep lsapi / other extprocessors).
        text = re.sub(
            r"\n*extprocessor snappymail_[^\s{]+ \{.*?\n\}\n*",
            "\n",
            text,
            flags=re.S,
        )
        text = re.sub(
            r"\n*context /\s*\{\s*type\s+proxy\s*.*?\n\}\s*",
            "\n",
            text,
            flags=re.S,
        )

        # Vhost: enable htaccess only (proxy rules belong in .htaccess).
        enable_only = _vhost_rewrite_enable_only()
        if re.search(r"rewrite\s*\{", text):
            text = re.sub(
                r"rewrite\s*\{.*?^\}\s*",
                enable_only + "\n",
                text,
                count=1,
                flags=re.S | re.M,
            )
        else:
            text = text.rstrip() + "\n" + enable_only + "\n"

        if "context /.well-known/acme-challenge" not in text:
            if re.search(r"^vhssl\s*\{", text, flags=re.M):
                text = re.sub(
                    r"(^vhssl\s*\{)",
                    _acme_context_block() + r"\1",
                    text,
                    count=1,
                    flags=re.M,
                )
            else:
                text = text.rstrip() + _acme_context_block()

        text = text.rstrip() + _extprocessor_block(name, backend) + "\n"
        vh.write_text(text)
        _write_htaccess(domain, name, backend)

        if restart:
            try:
                from plogical import installUtilities

                installUtilities.installUtilities.reStartLiteSpeed()
            except Exception as e:
                logging.CyberCPLogFileWriter.writeToFile(
                    f"SOFTI softiWebmailProxy restart warning for {domain}: {e}"
                )

        msg = f"SOFTI SoftiMail proxy OK: {domain} -> {name} -> {backend}/snappymail"
        logging.CyberCPLogFileWriter.writeToFile(msg)
        return 1, msg
    except BaseException as msg:
        err = f"SOFTI softiWebmailProxy failed for {domain}: {msg}"
        logging.CyberCPLogFileWriter.writeToFile(err)
        return 0, err


def configure_if_webmail(domain: str, restart: bool = False) -> None:
    """Safe hook for createVirtualHost / issueSSL — no-op unless webmail.*."""
    if not is_softimail_webmail_domain(domain):
        return
    configure(domain, restart=restart)


def configure_all(restart: bool = True) -> List[str]:
    results = []
    if not VHOST_ROOT.is_dir():
        return results
    for path in sorted(VHOST_ROOT.iterdir()):
        if path.is_dir() and is_softimail_webmail_domain(path.name):
            ok, msg = configure(path.name, restart=False)
            results.append(msg if ok else f"FAIL {msg}")
    if restart and results:
        try:
            from plogical import installUtilities

            installUtilities.installUtilities.reStartLiteSpeed()
        except Exception as e:
            results.append(f"restart warning: {e}")
    return results
