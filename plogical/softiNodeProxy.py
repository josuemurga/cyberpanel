# -*- coding: utf-8 -*-
"""
SOFTI-MEJORA — Softi Node PaaS reverse proxy for Node apps behind OLS.

File writes (vhost.conf, .htaccess) require root. When called from Django
(lscpd/cyberpanel) we delegate to pm2_agent via Unix socket.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple

from plogical import CyberCPLogFileWriter as logging

ACME_CHALLENGE_ROOT = "/usr/local/lsws/Example/html/.well-known/acme-challenge"
VHOST_ROOT = Path("/usr/local/lsws/conf/vhosts")
SOFTI_MARKER = "### Softi Node PaaS"


def inspect(domain: str) -> dict:
    """Detect existing OLS reverse-proxy for a domain (read-only).

    Styles seen in Softi VPS:
      - softi_node: Softi marker + extprocessor node_* + htaccess [P]
      - context_proxy: vhost `context / { type proxy }` (+ named extprocessor)
      - htaccess_p: RewriteRule ... [P] to an extprocessor name
      - none
    """
    if os.geteuid() != 0:
        try:
            from nodeManager import pm2Manager

            data, err = pm2Manager.proxy_inspect(domain)
            if data is None:
                return {
                    "domain": domain,
                    "has_proxy": False,
                    "styles": [],
                    "summary": err or "inspect failed",
                    "recommend_configure": True,
                }
            return data
        except Exception as e:
            return {
                "domain": domain,
                "has_proxy": False,
                "styles": [],
                "summary": str(e),
                "recommend_configure": True,
            }
    return _inspect_impl(domain)


def _inspect_impl(domain: str) -> dict:
    domain = (domain or "").strip()
    result = {
        "domain": domain,
        "has_proxy": False,
        "styles": [],
        "processors": [],
        "backends": [],
        "htaccess_proxy_rules": [],
        "softi_managed": False,
        "summary": "Sin proxy detectado",
        "recommend_configure": True,
    }
    if not domain or ".." in domain or "/" in domain:
        result["summary"] = "dominio inválido"
        return result

    vh = VHOST_ROOT / domain / "vhost.conf"
    text = ""
    if vh.is_file():
        try:
            text = vh.read_text()
        except OSError as e:
            result["summary"] = f"no se pudo leer vhost: {e}"
            return result

    # Named proxy extprocessors (exclude lsphp/lsapi handlers without type proxy)
    for m in re.finditer(
        r"extprocessor\s+(\S+)\s*\{([^}]*)\}", text, flags=re.S
    ):
        name, body = m.group(1), m.group(2)
        if re.search(r"type\s+proxy", body):
            addr = None
            am = re.search(r"address\s+(\S+)", body)
            if am:
                addr = am.group(1)
            result["processors"].append({"name": name, "address": addr})
            if addr:
                result["backends"].append(addr)
            if name.startswith("node_"):
                result["softi_managed"] = True
                if "softi_node" not in result["styles"]:
                    result["styles"].append("softi_node")

    if re.search(r"context\s+/\s*\{[^}]*type\s+proxy", text, flags=re.S):
        if "context_proxy" not in result["styles"]:
            result["styles"].append("context_proxy")

    ht = Path(f"/home/{domain}/public_html/.htaccess")
    try:
        if ht.is_file():
            ht_text = ht.read_text(errors="replace")
            if SOFTI_MARKER in ht_text:
                result["softi_managed"] = True
                if "softi_node" not in result["styles"]:
                    result["styles"].append("softi_node")
            for line in ht_text.splitlines():
                if re.search(r"\[P(?:,|\])", line) or re.search(
                    r"RewriteRule\s+.+\s+\[P", line, re.I
                ):
                    result["htaccess_proxy_rules"].append(line.strip())
                    if "htaccess_p" not in result["styles"]:
                        result["styles"].append("htaccess_p")
    except OSError:
        pass

    result["has_proxy"] = bool(result["styles"] or result["processors"])
    # Only recommend Softi rewrite when nothing proxy-like exists
    result["recommend_configure"] = not result["has_proxy"]

    if result["has_proxy"]:
        bits = []
        if result["softi_managed"]:
            bits.append("proxy Softi Node")
        if "context_proxy" in result["styles"]:
            bits.append("context / proxy en vhost")
        if "htaccess_p" in result["styles"] and not result["softi_managed"]:
            bits.append("RewriteRule [P] en .htaccess")
        procs = ", ".join(
            f"{p['name']}" + (f"→{p['address']}" if p.get("address") else "")
            for p in result["processors"][:4]
        )
        if procs:
            bits.append(f"extprocessors: {procs}")
        result["summary"] = "Ya hay proxy: " + "; ".join(bits)
    return result


def processor_name(domain: str, app_name: str = "app") -> str:
    safe_d = re.sub(r"[^a-zA-Z0-9]+", "_", domain.strip().lower()).strip("_")
    safe_a = re.sub(r"[^a-zA-Z0-9]+", "_", app_name.strip().lower()).strip("_") or "app"
    return f"node_{safe_d}_{safe_a}"[:100]


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


def _write_htaccess(domain: str, name: str, backend_host: str) -> None:
    """Full-site proxy to Node (MVP: entire domain → app)."""
    public = Path(f"/home/{domain}/public_html")
    try:
        exists = public.is_dir()
    except OSError:
        exists = False
    if not exists:
        public.mkdir(parents=True, exist_ok=True)
    ht = public / ".htaccess"
    ht.write_text(
        f"{SOFTI_MARKER}: unique extprocessor → Node on 127.0.0.1\n"
        "RewriteEngine On\n"
        "RewriteCond %{REQUEST_URI} !^/\\.well-known/acme-challenge/\n"
        "RewriteCond %{HTTPS} !=on\n"
        "RewriteRule ^/?(.*) https://%{SERVER_NAME}/$1 [R,L]\n"
        "\n"
        "RewriteCond %{REQUEST_URI} !^/\\.well-known/acme-challenge/\n"
        f"RewriteRule ^(.*) http://{name}/$1 [P,L]\n"
    )


def configure(
    domain: str,
    port: int,
    app_name: str = "app",
    restart: bool = False,
) -> Tuple[int, str]:
    """Idempotent proxy setup. Non-root → pm2_agent (root)."""
    if os.geteuid() != 0:
        try:
            from nodeManager import pm2Manager

            ok, msg = pm2Manager.proxy_configure(domain, port, app_name, restart)
            return (1, msg) if ok else (0, msg)
        except Exception as e:
            return 0, f"proxy via agent failed: {e}"
    return _configure_impl(domain, port, app_name, restart)


def _configure_impl(
    domain: str,
    port: int,
    app_name: str = "app",
    restart: bool = False,
) -> Tuple[int, str]:
    try:
        domain = (domain or "").strip()
        if not domain or ".." in domain or "/" in domain:
            return 0, f"dominio inválido: {domain}"
        try:
            port = int(port)
        except (TypeError, ValueError):
            return 0, "puerto inválido"

        vh = VHOST_ROOT / domain / "vhost.conf"
        if not vh.is_file():
            return 0, f"missing vhost.conf: {vh}"

        name = processor_name(domain, app_name)
        backend = f"http://127.0.0.1:{port}"
        text = vh.read_text()

        text = re.sub(
            r"\n*extprocessor node_[^\s{]+ \{.*?\n\}\n*",
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

                installUtilities.installUtilities.softiFullRestartLiteSpeed()
            except Exception:
                try:
                    from plogical import installUtilities

                    installUtilities.installUtilities.reStartLiteSpeed()
                except Exception as e:
                    logging.CyberCPLogFileWriter.writeToFile(
                        f"SOFTI softiNodeProxy restart warning for {domain}: {e}"
                    )

        msg = f"SOFTI Node proxy OK: {domain} -> {name} -> {backend}"
        logging.CyberCPLogFileWriter.writeToFile(msg)
        return 1, msg
    except BaseException as msg:
        err = f"SOFTI softiNodeProxy failed for {domain}: {msg}"
        logging.CyberCPLogFileWriter.writeToFile(err)
        return 0, err


def remove(domain: str, restart: bool = False) -> Tuple[int, str]:
    if os.geteuid() != 0:
        try:
            from nodeManager import pm2Manager

            ok, msg = pm2Manager.proxy_remove(domain, restart)
            return (1, msg) if ok else (0, msg)
        except Exception as e:
            return 0, f"proxy remove via agent failed: {e}"
    return _remove_impl(domain, restart)


def _remove_impl(domain: str, restart: bool = False) -> Tuple[int, str]:
    try:
        domain = (domain or "").strip()
        vh = VHOST_ROOT / domain / "vhost.conf"
        if not vh.is_file():
            return 0, f"missing vhost.conf: {vh}"

        text = vh.read_text()
        text = re.sub(
            r"\n*extprocessor node_[^\s{]+ \{.*?\n\}\n*",
            "\n",
            text,
            flags=re.S,
        )
        vh.write_text(text)

        ht = Path(f"/home/{domain}/public_html/.htaccess")
        try:
            if ht.is_file():
                content = ht.read_text()
                if SOFTI_MARKER in content:
                    ht.write_text(
                        "# Softi Node PaaS proxy removed\n"
                        "RewriteEngine On\n"
                    )
        except OSError as e:
            logging.CyberCPLogFileWriter.writeToFile(
                f"SOFTI softiNodeProxy htaccess remove warning: {e}"
            )

        if restart:
            try:
                from plogical import installUtilities

                installUtilities.installUtilities.softiFullRestartLiteSpeed()
            except Exception:
                pass

        msg = f"SOFTI Node proxy removed: {domain}"
        logging.CyberCPLogFileWriter.writeToFile(msg)
        return 1, msg
    except BaseException as msg:
        err = f"SOFTI softiNodeProxy remove failed for {domain}: {msg}"
        logging.CyberCPLogFileWriter.writeToFile(err)
        return 0, err
