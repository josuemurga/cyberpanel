"""Softi Node PaaS — JSON registry for apps (evita migrate en MVP).

Readable/writable by OLS LSAPI worker (user lscpd). Not under /etc with 640 root.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

# Primary path: accessible by lscpd (CyberPanel LSAPI)
DATA_DIR = Path("/usr/local/CyberCP/nodeManager/data")
REGISTRY_PATH = DATA_DIR / "apps.json"
# Legacy path (created as root:root 640 — lscpd could not read)
LEGACY_PATH = Path("/etc/cyberpanel/softi-node-apps.json")

NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$")
PORT_MIN, PORT_MAX = 30000, 39999


def _empty() -> dict:
    return {"apps": [], "updated_at": None}


def _ensure_data_dir() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Best-effort so lscpd can write
        os.chmod(str(DATA_DIR), 0o775)
    except Exception:
        pass


def load() -> dict:
    # Prefer agent (root) so panel user never depends on data/ perms
    try:
        from nodeManager import pm2Manager

        data, err = pm2Manager.registry_load()
        if data is not None:
            return data
    except Exception:
        pass
    _ensure_data_dir()
    for path in (REGISTRY_PATH, LEGACY_PATH):
        try:
            if path.is_file():
                data = json.loads(path.read_text())
                if isinstance(data, dict) and isinstance(data.get("apps"), list):
                    return data
        except Exception:
            continue
    return _empty()


def save(data: dict) -> None:
    data = dict(data)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        from nodeManager import pm2Manager

        ok, err = pm2Manager.registry_save(data)
        if ok:
            return
        raise IOError(err or "registry_save failed")
    except ImportError:
        pass
    # Fallback direct write (CLI as root)
    _ensure_data_dir()
    fd, tmp = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, str(REGISTRY_PATH))
        os.chmod(str(REGISTRY_PATH), 0o666)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def list_apps() -> List[dict]:
    return list(load().get("apps") or [])


def get_by_pm2_name(pm2_name: str) -> Optional[dict]:
    for app in list_apps():
        if app.get("pm2_name") == pm2_name:
            return app
    return None


def get_by_id(app_id: str) -> Optional[dict]:
    for app in list_apps():
        if app.get("id") == app_id:
            return app
    return None


def used_ports() -> set:
    return {int(a["port"]) for a in list_apps() if a.get("port")}


def alloc_port(preferred: Optional[int] = None) -> Tuple[Optional[int], Optional[str]]:
    used = used_ports()
    if preferred is not None:
        try:
            p = int(preferred)
        except (TypeError, ValueError):
            return None, "Puerto inválido"
        if p < PORT_MIN or p > PORT_MAX:
            return None, f"Puerto fuera de rango {PORT_MIN}-{PORT_MAX}"
        if p in used:
            return None, f"Puerto {p} ya asignado"
        return p, None
    for p in range(PORT_MIN, PORT_MAX + 1):
        if p not in used:
            return p, None
    return None, "No hay puertos libres"


def pm2_name_for(domain: str, name: str) -> str:
    safe_d = re.sub(r"[^a-zA-Z0-9.-]+", "_", domain.strip().lower())
    return f"{safe_d}__{name}"


def validate_name(name: str) -> Optional[str]:
    if not name or not NAME_RE.match(name):
        return "Nombre inválido (letras, números, _-; máx 48)"
    return None


def upsert(app: dict) -> dict:
    data = load()
    apps = data.get("apps") or []
    found = False
    for i, existing in enumerate(apps):
        if existing.get("id") == app.get("id") or existing.get("pm2_name") == app.get(
            "pm2_name"
        ):
            apps[i] = {**existing, **app}
            found = True
            break
    if not found:
        apps.append(app)
    data["apps"] = apps
    save(data)
    return app


def delete(pm2_name: str = None, app_id: str = None) -> Optional[dict]:
    data = load()
    apps = data.get("apps") or []
    removed = None
    kept = []
    for a in apps:
        if (pm2_name and a.get("pm2_name") == pm2_name) or (
            app_id and a.get("id") == app_id
        ):
            removed = a
            continue
        kept.append(a)
    data["apps"] = kept
    save(data)
    return removed


def merge_pm2_status(registry_apps: List[dict], pm2_apps: List[dict]) -> List[dict]:
    by_name = {p.get("name"): p for p in (pm2_apps or [])}
    out = []
    for app in registry_apps:
        p = by_name.get(app.get("pm2_name"), {})
        row = dict(app)
        row["status"] = p.get("status", "missing")
        row["pid"] = p.get("pid")
        row["restarts"] = p.get("restarts", 0)
        row["cpu"] = p.get("cpu", 0)
        row["memory_mb"] = p.get("memory_mb", 0)
        row["disk_mb"] = p.get("disk_mb")
        row["uptime"] = p.get("uptime")
        out.append(row)
    return out


def guess_port_from_pm2(pm2_app: dict) -> Optional[int]:
    """Try PORT from PM2 env, .env or .softi-node.json in cwd.

    Runs in Django as lscpd/cyberpanel — must not raise on EACCES (site homes
    are often 750 and not traversable by the panel user).
    """
    port = pm2_app.get("port")
    if port:
        try:
            return int(port)
        except (TypeError, ValueError):
            pass
    cwd = (pm2_app.get("cwd") or "").strip()
    if not cwd:
        return None
    try:
        if not Path(cwd).is_dir():
            return None
    except OSError:
        return None
    for rel in (".softi-node.json", ".env"):
        p = Path(cwd) / rel
        try:
            if not p.is_file():
                continue
            text = p.read_text(errors="replace")
        except OSError:
            continue
        try:
            if rel.endswith(".json"):
                data = json.loads(text)
                if data.get("port"):
                    return int(data["port"])
            else:
                for line in text.splitlines():
                    if line.strip().startswith("PORT="):
                        return int(line.split("=", 1)[1].strip().strip('"'))
        except Exception:
            continue
    return None


def unregistered_pm2(pm2_apps: List[dict]) -> List[dict]:
    registered = {a.get("pm2_name") for a in list_apps()}
    out = []
    for p in pm2_apps or []:
        name = p.get("name")
        if not name or name in registered:
            continue
        row = dict(p)
        try:
            row["guessed_port"] = guess_port_from_pm2(p)
        except OSError:
            row["guessed_port"] = None
        # Prefer agent guess when panel cannot read site home
        if row["guessed_port"] is None and p.get("cwd"):
            try:
                from nodeManager import pm2Manager

                port, _ = pm2Manager.guess_port(p.get("cwd"))
                row["guessed_port"] = port
            except Exception:
                pass
        out.append(row)
    return out
