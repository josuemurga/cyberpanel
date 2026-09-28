"""
pm2_agent.py — Agente root para control de PM2 (Softi Node PaaS).
Corre como root via systemd, escucha en Unix socket /run/pm2-agent.sock.

Protocolo JSON por línea:
  {"cmd": "list"|"restart"|"start"|"stop"|"delete"|"create"|"logs"|"set_env"|"get_env"|"status", ...}
  Response: {"status": 1, "data": ...} | {"status": 0, "error": "..."}
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

SOCKET_PATH = "/run/pm2-agent.sock"
PM2_BIN = "/root/.nvm/versions/node/v20.19.6/bin/pm2"
NODE_BIN = "/root/.nvm/versions/node/v20.19.6/bin/node"
PM2_ENV = {
    "NVM_DIR": "/root/.nvm",
    "PATH": "/root/.nvm/versions/node/v20.19.6/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
}

ALLOWED_CMDS = {
    "list",
    "restart",
    "start",
    "stop",
    "delete",
    "create",
    "logs",
    "flush_logs",
    "set_env",
    "get_env",
    "upsert_env",
    "delete_env",
    "import_env",
    "status",
    "proxy_configure",
    "proxy_remove",
    "proxy_inspect",
    "guess_port",
    "registry_load",
    "registry_save",
    "chown_tree",
    "list_node_versions",
    "redeploy",
    "deploy_archive",
    "list_deploys",
    "mark_deploy",
}

NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,96}$")
PORT_MIN, PORT_MAX = 30000, 39999


def run_pm2(args, timeout=30, extra_env=None):
    env = dict(PM2_ENV)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [PM2_BIN] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def _valid_name(name: str) -> bool:
    return bool(name and NAME_RE.match(name) and "/" not in name)


def _valid_cwd(cwd: str) -> bool:
    if not cwd or ".." in cwd or ";" in cwd:
        return False
    p = Path(cwd).resolve()
    return str(p).startswith("/home/") and p.is_dir()


def _valid_script(script: str) -> bool:
    if not script or ".." in script or script.startswith("/") or ";" in script:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_./-]{1,128}$", script))


def _pm2_names():
    stdout, _, rc = run_pm2(["jlist"])
    if rc != 0:
        return None, "No se pudo leer lista de PM2"
    try:
        return [p["name"] for p in json.loads(stdout)], None
    except Exception:
        return None, "Error leyendo apps PM2"


def _find_proc(name: str):
    stdout, _, rc = run_pm2(["jlist"])
    if rc != 0:
        return None
    try:
        for proc in json.loads(stdout):
            if proc.get("name") == name:
                return proc
    except Exception:
        return None
    return None


def _cwd_disk_mb(cwd: str) -> float | None:
    """Apparent size of the Node app directory (cwd), in MiB.

    This is the app project folder (often /home/<domain>/nodejs/<app>), not the
    whole website home (mail, logs, other vhosts). Timed out / inaccessible → None.
    """
    if not cwd or not _valid_cwd(cwd):
        return None
    try:
        r = subprocess.run(
            ["du", "-sm", cwd],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return float(r.stdout.strip().split()[0])
    except Exception:
        return None


def handle_list():
    stdout, stderr, rc = run_pm2(["jlist"])
    if rc != 0:
        return {"status": 0, "error": stderr or "PM2 error"}
    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
        return {"status": 0, "error": "Error parseando salida de PM2"}
    apps = []
    for proc in raw:
        env = proc.get("pm2_env", {})
        cwd = env.get("cwd") or env.get("pm_cwd", "")
        disk = _cwd_disk_mb(cwd)
        apps.append(
            {
                "id": proc.get("pm_id"),
                "name": proc.get("name"),
                "status": env.get("status", "unknown"),
                "pid": proc.get("pid"),
                "uptime": env.get("pm_uptime"),
                "restarts": env.get("restart_time", 0),
                "cpu": proc.get("monit", {}).get("cpu", 0),
                "memory_mb": round(proc.get("monit", {}).get("memory", 0) / 1024 / 1024, 1),
                "disk_mb": disk,
                "cwd": cwd,
                "script": env.get("pm_exec_path", ""),
                "port": (env.get("env") or {}).get("PORT")
                or (env.get("env") or {}).get("port"),
            }
        )
    return {"status": 1, "data": apps}


def handle_restart(name):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    names, err = _pm2_names()
    if err:
        return {"status": 0, "error": err}
    if name not in names:
        return {"status": 0, "error": f"App '{name}' no encontrada"}
    _, stderr, rc = run_pm2(["restart", name, "--update-env"])
    if rc != 0:
        return {"status": 0, "error": stderr or "Error al reiniciar"}
    return {"status": 1, "data": f"App '{name}' reiniciada"}


def handle_start(name):
    """Start a stopped PM2 process.

    Do NOT use `pm2 start <name>`: with names like domain__app, PM2 treats the
    arg as a script path relative to the agent's cwd (/usr/local/CyberCP) and
    fails with "Script not found: /usr/local/CyberCP/<name>". Restart works for
    stopped apps; start by numeric id is also safe.
    """
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    proc = _find_proc(name)
    if not proc:
        return {"status": 0, "error": f"App '{name}' no encontrada en PM2"}
    status = (proc.get("pm2_env") or {}).get("status", "")
    if status == "online":
        return {"status": 1, "data": f"App '{name}' ya está en línea"}
    pm_id = proc.get("pm_id")
    if pm_id is not None:
        _, stderr, rc = run_pm2(["start", str(int(pm_id))])
    else:
        _, stderr, rc = run_pm2(["restart", name, "--update-env"])
    if rc != 0:
        # last resort: ecosystem in app cwd
        cwd = (proc.get("pm2_env") or {}).get("cwd") or (proc.get("pm2_env") or {}).get(
            "pm_cwd"
        )
        eco = Path(cwd) / "ecosystem.config.cjs" if cwd else None
        if eco and eco.is_file():
            _, stderr2, rc2 = run_pm2(["start", str(eco), "--only", name], timeout=45)
            if rc2 == 0:
                return {"status": 1, "data": f"App '{name}' iniciada"}
            return {"status": 0, "error": stderr2 or stderr or "Error al iniciar"}
        return {"status": 0, "error": stderr or "Error al iniciar"}
    return {"status": 1, "data": f"App '{name}' iniciada"}


def handle_stop(name):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    names, err = _pm2_names()
    if err:
        return {"status": 0, "error": err}
    if name not in names:
        return {"status": 0, "error": f"App '{name}' no encontrada"}
    _, stderr, rc = run_pm2(["stop", name])
    if rc != 0:
        return {"status": 0, "error": stderr or "Error al detener"}
    return {"status": 1, "data": f"App '{name}' detenida"}


def handle_delete(name):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    names, err = _pm2_names()
    if err:
        return {"status": 0, "error": err}
    if name not in names:
        return {"status": 0, "error": f"App '{name}' no encontrada"}
    _, stderr, rc = run_pm2(["delete", name])
    if rc != 0:
        return {"status": 0, "error": stderr or "Error al eliminar"}
    return {"status": 1, "data": f"App '{name}' eliminada de PM2"}


def handle_status(name):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    proc = _find_proc(name)
    if not proc:
        return {"status": 0, "error": f"App '{name}' no encontrada"}
    env = proc.get("pm2_env", {})
    return {
        "status": 1,
        "data": {
            "id": proc.get("pm_id"),
            "name": proc.get("name"),
            "status": env.get("status", "unknown"),
            "pid": proc.get("pid"),
            "restarts": env.get("restart_time", 0),
            "cwd": env.get("cwd") or env.get("pm_cwd", ""),
            "script": env.get("pm_exec_path", ""),
            "port": (env.get("env") or {}).get("PORT"),
        },
    }


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b\([AB0-2]")


def _strip_ansi(text: str) -> str:
    if not text:
        return ""
    return ANSI_RE.sub("", text)


def _tail_text(path: Path, max_lines: int) -> str:
    if not path.is_file():
        return ""
    try:
        # read last ~512KB then take lines (cheap enough for panel)
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > 524288:
                f.seek(size - 524288)
                f.readline()  # drop partial first line
            raw = f.read().decode("utf-8", errors="replace")
        lines = raw.splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _iso_mtime(path: Path):
    try:
        if path.is_file():
            import time as _t

            return _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(path.stat().st_mtime))
    except Exception:
        pass
    return None


def handle_logs(name, lines=100):
    """Return cleaned PM2 out/err tails separately (strip ANSI)."""
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    try:
        lines = int(lines)
    except (TypeError, ValueError):
        lines = 100
    lines = max(10, min(lines, 500))
    proc = _find_proc(name)
    if not proc:
        return {"status": 0, "error": f"App '{name}' no encontrada"}
    env = proc.get("pm2_env") or {}
    out_path = Path(env.get("pm_out_log_path") or f"/root/.pm2/logs/{name}-out.log")
    err_path = Path(env.get("pm_err_log_path") or f"/root/.pm2/logs/{name}-error.log")

    import time as _t

    fetched_at = _t.strftime("%Y-%m-%d %H:%M:%S %z").strip() or _t.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    out_body = _strip_ansi(_tail_text(out_path, lines)) or "(vacío)"
    err_body = _strip_ansi(_tail_text(err_path, lines)) or "(vacío)"
    # legacy combined text (compat)
    text = (
        f"=== Softi logs @ {fetched_at} ===\n"
        f"--- stderr ---\n{err_body}\n\n--- stdout ---\n{out_body}\n"
    )
    return {
        "status": 1,
        "data": {
            "text": text[-120000:],
            "stdout": out_body[-100000:],
            "stderr": err_body[-100000:],
            "fetched_at": fetched_at,
            "out_mtime": _iso_mtime(out_path),
            "err_mtime": _iso_mtime(err_path),
            "out_bytes": out_path.stat().st_size if out_path.is_file() else 0,
            "err_bytes": err_path.stat().st_size if err_path.is_file() else 0,
        },
    }


def handle_flush_logs(name):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    names, err = _pm2_names()
    if err:
        return {"status": 0, "error": err}
    if name not in names:
        return {"status": 0, "error": f"App '{name}' no encontrada"}
    _, stderr, rc = run_pm2(["flush", name], timeout=30)
    if rc != 0:
        # fallback: truncate known paths
        proc = _find_proc(name)
        env = (proc or {}).get("pm2_env") or {}
        for key in ("pm_out_log_path", "pm_err_log_path"):
            p = env.get(key)
            if p and Path(p).is_file():
                try:
                    Path(p).write_text("")
                except Exception as e:
                    return {"status": 0, "error": f"flush falló: {e}"}
        return {"status": 1, "data": "logs vaciados (truncate)"}
    return {"status": 1, "data": stderr or "logs vaciados"}


def _env_path(cwd: str) -> Path:
    return Path(cwd) / ".env"


def _parse_env_value(raw: str) -> str:
    v = raw.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    # strip inline comment only if unquoted and preceded by space
    if " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return v


def _format_env_value(value: str) -> str:
    s = str(value)
    if re.search(r'[\s#"\'\\]', s) or s == "":
        return json.dumps(s)  # double-quoted JSON-style escape
    return s


def _parse_env_file(path: Path) -> dict:
    """KEY→value map (last wins). Comments/blank ignored."""
    result = {}
    for item in _parse_env_items(path):
        result[item["key"]] = item["value"]
    return result


def _parse_env_items(path: Path) -> list:
    """Ordered unique keys as they appear in file (first wins for order)."""
    if not path.is_file():
        return []
    seen = set()
    items = []
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            continue
        k, _, raw = stripped.partition("=")
        k = k.strip()
        if not k or k in seen:
            continue
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", k):
            continue
        seen.add(k)
        items.append({"key": k, "value": _parse_env_value(raw)})
    return items


def _validate_env_key(key: str):
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", str(key)):
        return f"Clave env inválida: {key}"
    return None


def _validate_env_value(key: str, value: str):
    vs = str(value)
    if "\n" in vs or "\x00" in vs:
        return f"Valor env inválido: {key}"
    if len(vs) > 8192:
        return f"Valor demasiado largo: {key}"
    return None


def _line_env_key(line: str):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return None
    k = stripped.split("=", 1)[0].strip()
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", k):
        return k
    return None


def _upsert_env_in_file(path: Path, key: str, value: str) -> str:
    """Update or append KEY=value; preserve comments and blank lines. Returns action."""
    formatted = f"{key}={_format_env_value(value)}"
    if not path.is_file():
        path.write_text(formatted + "\n")
        return "created"
    text = path.read_text(errors="replace")
    # keep original newlines style
    lines = text.splitlines(keepends=True)
    if not lines and text == "":
        path.write_text(formatted + "\n")
        return "created"
    found = False
    for i, line in enumerate(lines):
        if _line_env_key(line) == key:
            nl = "\n"
            if line.endswith("\r\n"):
                nl = "\r\n"
            elif line.endswith("\n"):
                nl = "\n"
            else:
                nl = "\n"
            lines[i] = formatted + nl
            found = True
            break
    if found:
        path.write_text("".join(lines))
        return "updated"
    # append
    if text and not text.endswith("\n") and not text.endswith("\r\n"):
        text = text + "\n"
    path.write_text(text + formatted + "\n")
    return "added"


def _delete_env_in_file(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(errors="replace")
    lines = text.splitlines(keepends=True)
    new_lines = [ln for ln in lines if _line_env_key(ln) != key]
    if len(new_lines) == len(lines):
        return False
    path.write_text("".join(new_lines))
    return True


def _write_env_file(path: Path, env: dict) -> None:
    """Full rewrite (legacy). Prefer upsert/delete for UI."""
    lines = [f"{k}={_format_env_value(v)}" for k, v in sorted(env.items())]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def _resolve_app_cwd(name: str, cwd=None):
    proc = _find_proc(name)
    if cwd:
        if not _valid_cwd(cwd):
            return None, None, "cwd inválido"
        return cwd, proc, None
    if proc:
        cwd = proc.get("pm2_env", {}).get("cwd") or proc.get("pm2_env", {}).get(
            "pm_cwd"
        )
    if not cwd or not _valid_cwd(cwd):
        return None, proc, "No se pudo resolver cwd de la app"
    return cwd, proc, None


def _apply_env_restart(name: str, cwd: str, proc, restart: bool):
    full = _parse_env_file(_env_path(cwd))
    _patch_ecosystem_env(cwd, full)
    if restart and proc:
        _, stderr, rc = run_pm2(["restart", name, "--update-env"])
        if rc != 0:
            return False, stderr or "Env guardado pero falló restart"
    return True, "OK"


def handle_get_env(name, cwd=None):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    cwd, _, err = _resolve_app_cwd(name, cwd)
    if err:
        return {"status": 0, "error": err}
    items = _parse_env_items(_env_path(cwd))
    env = {i["key"]: i["value"] for i in items}
    return {"status": 1, "data": {"env": env, "items": items}}


def handle_set_env(name, env, cwd=None, restart=True):
    """Legacy full rewrite — prefer upsert_env / import_env."""
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    if not isinstance(env, dict):
        return {"status": 0, "error": "env debe ser un objeto"}
    clean = {}
    for k, v in env.items():
        ke = _validate_env_key(k)
        if ke:
            return {"status": 0, "error": ke}
        ve = _validate_env_value(k, v)
        if ve:
            return {"status": 0, "error": ve}
        clean[str(k)] = str(v)
    cwd, proc, err = _resolve_app_cwd(name, cwd)
    if err:
        return {"status": 0, "error": err}
    _write_env_file(_env_path(cwd), clean)
    ok, msg = _apply_env_restart(name, cwd, proc, restart)
    if not ok:
        return {"status": 0, "error": msg}
    return {"status": 1, "data": "Variables de entorno guardadas"}


def handle_upsert_env(name, key, value, cwd=None, restart=True):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    ke = _validate_env_key(key)
    if ke:
        return {"status": 0, "error": ke}
    ve = _validate_env_value(key, value)
    if ve:
        return {"status": 0, "error": ve}
    cwd, proc, err = _resolve_app_cwd(name, cwd)
    if err:
        return {"status": 0, "error": err}
    action = _upsert_env_in_file(_env_path(cwd), str(key), str(value))
    ok, msg = _apply_env_restart(name, cwd, proc, restart)
    if not ok:
        return {"status": 0, "error": msg}
    return {
        "status": 1,
        "data": {
            "action": action,
            "key": key,
            "items": _parse_env_items(_env_path(cwd)),
        },
    }


def handle_delete_env(name, key, cwd=None, restart=True):
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    ke = _validate_env_key(key)
    if ke:
        return {"status": 0, "error": ke}
    if key == "PORT":
        return {"status": 0, "error": "PORT lo gestiona Softi; no se puede eliminar"}
    cwd, proc, err = _resolve_app_cwd(name, cwd)
    if err:
        return {"status": 0, "error": err}
    if not _delete_env_in_file(_env_path(cwd), str(key)):
        return {"status": 0, "error": f"Variable '{key}' no encontrada"}
    ok, msg = _apply_env_restart(name, cwd, proc, restart)
    if not ok:
        return {"status": 0, "error": msg}
    return {
        "status": 1,
        "data": {"key": key, "items": _parse_env_items(_env_path(cwd))},
    }


def handle_import_env(name, content, cwd=None, restart=True):
    """Merge KEY=value from dotenv text; preserve existing comments/blank/other keys."""
    if not _valid_name(name):
        return {"status": 0, "error": "Nombre de app inválido"}
    if content is None:
        return {"status": 0, "error": "content vacío"}
    text = str(content)
    if len(text) > 200000:
        return {"status": 0, "error": "Archivo .env demasiado grande"}
    cwd, proc, err = _resolve_app_cwd(name, cwd)
    if err:
        return {"status": 0, "error": err}
    path = _env_path(cwd)
    merged = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            continue
        k, _, raw = stripped.partition("=")
        k = k.strip()
        ke = _validate_env_key(k)
        if ke:
            return {"status": 0, "error": ke}
        v = _parse_env_value(raw)
        ve = _validate_env_value(k, v)
        if ve:
            return {"status": 0, "error": ve}
        _upsert_env_in_file(path, k, v)
        merged += 1
    ok, msg = _apply_env_restart(name, cwd, proc, restart)
    if not ok:
        return {"status": 0, "error": msg}
    return {
        "status": 1,
        "data": {"merged": merged, "items": _parse_env_items(path)},
    }


def _patch_ecosystem_env(cwd: str, env: dict) -> None:
    eco = Path(cwd) / "ecosystem.config.cjs"
    if not eco.is_file():
        return
    # Rewrite env block simply by regenerating from known structure if we create it
    try:
        text = eco.read_text()
        # naive: if Softi marker, regenerate full file from sidecar meta
        meta = Path(cwd) / ".softi-node.json"
        if meta.is_file():
            info = json.loads(meta.read_text())
            _write_ecosystem(cwd, info, env)
    except Exception:
        pass


def _write_ecosystem(cwd: str, info: dict, env: dict) -> None:
    name = info["pm2_name"]
    script = info["script"]
    port = int(info["port"])
    merged = dict(env)
    merged["PORT"] = str(port)
    merged["NODE_ENV"] = merged.get("NODE_ENV", "production")
    env_js = json.dumps(merged)
    content = (
        "// Softi Node PaaS — managed ecosystem (do not edit by hand)\n"
        "module.exports = {\n"
        "  apps: [{\n"
        f"    name: {json.dumps(name)},\n"
        f"    script: {json.dumps(script)},\n"
        f"    cwd: {json.dumps(cwd)},\n"
        f"    interpreter: {json.dumps(NODE_BIN)},\n"
        "    instances: 1,\n"
        "    autorestart: true,\n"
        "    max_memory_restart: '512M',\n"
        f"    env: {env_js}\n"
        "  }]\n"
        "};\n"
    )
    Path(cwd).joinpath("ecosystem.config.cjs").write_text(content)


def _site_owner_ids(cwd: str):
    """UID/GID of /home/<domain> so File Manager can edit nodejs apps."""
    try:
        parts = Path(cwd).resolve().parts
        # / home / domain / ...
        if len(parts) >= 3 and parts[1] == "home":
            home = Path("/home") / parts[2]
            st = home.stat()
            return st.st_uid, st.st_gid
    except Exception:
        pass
    return None, None


def _chown_tree(path: str, uid: int, gid: int) -> None:
    p = Path(path)
    if not p.exists():
        return
    os.chown(str(p), uid, gid)
    if p.is_dir():
        for root, dirs, files in os.walk(str(p)):
            try:
                os.chown(root, uid, gid)
            except OSError:
                pass
            for name in dirs + files:
                try:
                    os.chown(os.path.join(root, name), uid, gid)
                except OSError:
                    pass


def handle_create(payload: dict):
    """
    Create PM2 app:
      pm2_name, cwd, script, port, env(optional), ensure_dir(optional)
    """
    name = (payload.get("pm2_name") or payload.get("name") or "").strip()
    cwd = (payload.get("cwd") or "").strip()
    script = (payload.get("script") or "server.js").strip()
    port = payload.get("port")
    env = payload.get("env") or {}
    ensure_dir = bool(payload.get("ensure_dir", False))

    if not _valid_name(name):
        return {"status": 0, "error": "pm2_name inválido"}
    try:
        port = int(port)
    except (TypeError, ValueError):
        return {"status": 0, "error": "Puerto inválido"}
    if port < PORT_MIN or port > PORT_MAX:
        return {"status": 0, "error": f"Puerto fuera de rango {PORT_MIN}-{PORT_MAX}"}

    if ensure_dir:
        # Only allow mkdir under /home/<domain>/nodejs/
        if ".." in cwd or not cwd.startswith("/home/") or "/nodejs/" not in (cwd + "/"):
            return {"status": 0, "error": "cwd inválido para ensure_dir (usa .../nodejs/...)"}
        Path(cwd).mkdir(parents=True, exist_ok=True)
        uid, gid = _site_owner_ids(cwd)
        if uid is not None:
            nodejs = Path(cwd)
            while nodejs.name != "nodejs" and nodejs != nodejs.parent:
                nodejs = nodejs.parent
            if nodejs.name == "nodejs":
                _chown_tree(str(nodejs), uid, gid)
            _chown_tree(cwd, uid, gid)

    if not _valid_cwd(cwd):
        return {"status": 0, "error": "cwd inválido o no existe"}
    if not _valid_script(script):
        return {"status": 0, "error": "script inválido"}

    script_path = Path(cwd) / script
    if not script_path.is_file():
        # Write minimal HTTP server if missing (Hostinger-like bootstrap)
        if payload.get("bootstrap", True):
            script_path.write_text(
                "const http = require('http');\n"
                "const port = process.env.PORT || 3000;\n"
                "http.createServer((req, res) => {\n"
                "  res.writeHead(200, {'Content-Type': 'text/plain'});\n"
                "  res.end('Softi Node app is running on port ' + port + '\\n');\n"
                "}).listen(port, '127.0.0.1');\n"
            )
        else:
            return {"status": 0, "error": f"Script no encontrado: {script}"}

    names, err = _pm2_names()
    if err:
        return {"status": 0, "error": err}
    if name in names:
        return {"status": 0, "error": f"App '{name}' ya existe en PM2"}

    # Port conflict among Softi apps / listening
    if _port_in_use(port):
        return {"status": 0, "error": f"Puerto {port} en uso"}

    clean_env = {"PORT": str(port), "NODE_ENV": "production"}
    if isinstance(env, dict):
        for k, v in env.items():
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", str(k)):
                clean_env[str(k)] = str(v)

    info = {"pm2_name": name, "script": script, "port": port}
    Path(cwd).joinpath(".softi-node.json").write_text(json.dumps(info, indent=2))
    _write_env_file(_env_path(cwd), clean_env)
    _write_ecosystem(cwd, info, clean_env)

    # File Manager / SFTP: files must belong to site linux user, not root
    uid, gid = _site_owner_ids(cwd)
    if uid is not None:
        _chown_tree(cwd, uid, gid)
        # parent nodejs/
        parent = Path(cwd).parent
        if parent.name == "nodejs":
            try:
                os.chown(str(parent), uid, gid)
            except OSError:
                pass

    eco = str(Path(cwd) / "ecosystem.config.cjs")
    _, stderr, rc = run_pm2(["start", eco], timeout=45)
    if rc != 0:
        return {"status": 0, "error": stderr or "pm2 start falló"}

    run_pm2(["save"], timeout=15)
    return {
        "status": 1,
        "data": {
            "pm2_name": name,
            "cwd": cwd,
            "script": script,
            "port": port,
        },
    }


def handle_registry_load():
    try:
        DATA_DIR = Path("/usr/local/CyberCP/nodeManager/data")
        REGISTRY = DATA_DIR / "apps.json"
        LEGACY = Path("/etc/cyberpanel/softi-node-apps.json")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for path in (REGISTRY, LEGACY):
            if path.is_file():
                data = json.loads(path.read_text())
                if isinstance(data, dict) and isinstance(data.get("apps"), list):
                    if path == LEGACY and not REGISTRY.is_file():
                        REGISTRY.write_text(json.dumps(data, indent=2))
                        os.chmod(str(REGISTRY), 0o666)
                    return {"status": 1, "data": data}
        return {"status": 1, "data": {"apps": [], "updated_at": None}}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def handle_registry_save(data):
    try:
        if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
            return {"status": 0, "error": "payload registry inválido"}
        DATA_DIR = Path("/usr/local/CyberCP/nodeManager/data")
        REGISTRY = DATA_DIR / "apps.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(str(DATA_DIR), 0o777)
        fd, tmp = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, str(REGISTRY))
            os.chmod(str(REGISTRY), 0o666)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        return {"status": 1, "data": "saved"}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def handle_chown_tree(path):
    if not path or ".." in path or not str(path).startswith("/home/"):
        return {"status": 0, "error": "path inválido"}
    uid, gid = _site_owner_ids(path)
    if uid is None:
        return {"status": 0, "error": "no se pudo resolver dueño del sitio"}
    try:
        _chown_tree(path, uid, gid)
        return {"status": 1, "data": {"uid": uid, "gid": gid}}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def handle_list_node_versions():
    try:
        base = Path("/root/.nvm/versions/node")
        versions = []
        if base.is_dir():
            for p in sorted(base.iterdir()):
                if p.is_dir() and p.name.startswith("v") and (p / "bin" / "node").is_file():
                    versions.append(p.name.lstrip("v"))
        return {"status": 1, "data": {"versions": versions, "default": "20.19.6"}}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def _resolve_node_bins(node_version: str):
    ver = (node_version or "20.19.6").lstrip("v")
    base = Path(f"/root/.nvm/versions/node/v{ver}")
    if not (base / "bin" / "node").is_file():
        # try major match e.g. 20 -> highest 20.x
        root = Path("/root/.nvm/versions/node")
        cands = []
        if root.is_dir():
            for p in root.iterdir():
                if p.name.startswith(f"v{ver.split('.')[0]}."):
                    cands.append(p)
        if cands:
            base = sorted(cands, key=lambda x: x.name)[-1]
            ver = base.name.lstrip("v")
        else:
            return None, None, None, f"Node v{ver} no instalado en nvm"
    node = str(base / "bin" / "node")
    npm = str(base / "bin" / "npm")
    return node, npm, ver, None


def _safe_rel_path(root: str, rel: str):
    rel = (rel or ".").strip() or "."
    if ".." in rel or rel.startswith("/"):
        return None
    base = Path(root).resolve()
    target = (base / rel).resolve()
    if not str(target).startswith(str(base)):
        return None
    return target


def _validate_build_command(cmd: str) -> list | None:
    """Return argv list or None if invalid. Empty/none => skip build."""
    cmd = (cmd or "").strip()
    if not cmd or cmd.lower() in ("none", "-", "null"):
        return []
    # allowlist common forms
    allowed_exact = {
        "npm run build",
        "npm run build:prod",
        "npm run build:production",
        "pnpm run build",
        "yarn build",
        "yarn run build",
        "npx nest build",
        "npm run nest:build",
    }
    if cmd in allowed_exact:
        return cmd.split()
    # restricted custom: must start with npm|pnpm|yarn|npx and safe chars
    if not re.match(r"^(npm|pnpm|yarn|npx)(\s+[A-Za-z0-9_./:@=-]+)+$", cmd):
        return None
    return cmd.split()


def handle_redeploy(payload: dict):
    """
    install + optional build + rewrite ecosystem interpreter + pm2 restart.
    Payload: pm2_name, cwd, script, port, node_version, package_manager,
             root_directory, build_command, entry_file
    """
    try:
        name = (payload.get("pm2_name") or "").strip()
        cwd = (payload.get("cwd") or "").strip()
        port = int(payload.get("port") or 0)
        node_version = payload.get("node_version") or "20.19.6"
        pkg = (payload.get("package_manager") or "npm").strip().lower()
        root_rel = payload.get("root_directory") or "."
        build_cmd = payload.get("build_command") or ""
        entry = (payload.get("entry_file") or payload.get("script") or "server.js").strip()

        if not _valid_name(name):
            return {"status": 0, "error": "pm2_name inválido"}
        if not _valid_cwd(cwd):
            return {"status": 0, "error": "cwd inválido"}
        if pkg not in ("npm", "pnpm", "yarn"):
            return {"status": 0, "error": "package_manager inválido"}
        if not _valid_script(entry.replace("\\", "/").lstrip("./")) and not _valid_script(entry):
            # allow paths like scripts/start.js
            if not re.match(r"^[a-zA-Z0-9_./-]{1,128}$", entry) or ".." in entry:
                return {"status": 0, "error": "entry_file inválido"}

        work = _safe_rel_path(cwd, root_rel)
        if work is None or not work.is_dir():
            return {"status": 0, "error": "root_directory inválido"}

        node_bin, npm_bin, ver, err = _resolve_node_bins(str(node_version))
        if err:
            return {"status": 0, "error": err}

        build_argv = _validate_build_command(build_cmd)
        if build_argv is None:
            return {"status": 0, "error": "build_command no permitido"}

        log_path = Path(cwd) / ".softi-deploy.log"
        lines = [f"=== Softi redeploy {time_stamp()} node=v{ver} pkg={pkg} ===\n"]

        env = dict(PM2_ENV)
        env["PATH"] = f"{Path(node_bin).parent}:{env['PATH']}"
        env["NPM_CONFIG_PRODUCTION"] = "false"

        # install
        if pkg == "npm":
            install_argv = [npm_bin, "ci"] if (work / "package-lock.json").is_file() else [npm_bin, "install"]
        elif pkg == "pnpm":
            install_argv = [str(Path(node_bin).parent / "pnpm"), "install"]
            if not Path(install_argv[0]).is_file():
                install_argv = [npm_bin, "exec", "--", "pnpm", "install"]
        else:
            yarn = str(Path(node_bin).parent / "yarn")
            install_argv = [yarn, "install"] if Path(yarn).is_file() else [npm_bin, "exec", "--", "yarn", "install"]

        lines.append(f"$ {' '.join(install_argv)}\n")
        r = subprocess.run(
            install_argv, cwd=str(work), env=env, capture_output=True, text=True, timeout=600
        )
        lines.append(r.stdout or "")
        lines.append(r.stderr or "")
        if r.returncode != 0:
            log_path.write_text("".join(lines)[-200000:])
            return {"status": 0, "error": f"install falló (code {r.returncode})", "log": "".join(lines)[-8000:]}

        if build_argv:
            lines.append(f"$ {' '.join(build_argv)}\n")
            r = subprocess.run(
                build_argv, cwd=str(work), env=env, capture_output=True, text=True, timeout=900
            )
            lines.append(r.stdout or "")
            lines.append(r.stderr or "")
            if r.returncode != 0:
                log_path.write_text("".join(lines)[-200000:])
                return {"status": 0, "error": f"build falló (code {r.returncode})", "log": "".join(lines)[-8000:]}

        # entry relative to app cwd (not necessarily work root)
        entry_path = Path(cwd) / entry
        if not entry_path.is_file():
            # try under work dir
            alt = work / entry
            if alt.is_file():
                try:
                    entry = str(alt.relative_to(Path(cwd)))
                except ValueError:
                    entry = entry
            else:
                log_path.write_text("".join(lines)[-200000:])
                return {"status": 0, "error": f"entry_file no encontrado: {entry}"}

        # refresh ecosystem with selected node interpreter
        info = {"pm2_name": name, "script": entry, "port": port}
        env_file = _parse_env_file(_env_path(cwd))
        env_file["PORT"] = str(port)
        env_file["NODE_ENV"] = env_file.get("NODE_ENV", "production")
        # temporarily override NODE_BIN for ecosystem
        global NODE_BIN
        old_node = NODE_BIN
        NODE_BIN = node_bin
        try:
            _write_ecosystem(cwd, info, env_file)
        finally:
            NODE_BIN = old_node

        # pm2 delete+start or restart with new ecosystem
        names, _ = _pm2_names()
        if names and name in names:
            run_pm2(["delete", name], timeout=30)
        eco = str(Path(cwd) / "ecosystem.config.cjs")
        # patch interpreter in ecosystem already set via NODE_BIN
        # rewrite ecosystem again ensuring node_bin
        content = (Path(cwd) / "ecosystem.config.cjs").read_text()
        # force interpreter path
        _write_ecosystem_with_node(cwd, info, env_file, node_bin)

        _, stderr, rc = run_pm2(["start", eco], timeout=60)
        lines.append(stderr or "")
        if rc != 0:
            log_path.write_text("".join(lines)[-200000:])
            return {"status": 0, "error": stderr or "pm2 start falló", "log": "".join(lines)[-8000:]}
        run_pm2(["save"], timeout=15)

        uid, gid = _site_owner_ids(cwd)
        if uid is not None:
            _chown_tree(cwd, uid, gid)

        lines.append("=== OK ===\n")
        log_path.write_text("".join(lines)[-200000:])
        return {
            "status": 1,
            "data": {
                "pm2_name": name,
                "node_version": ver,
                "entry_file": entry,
                "log_tail": "".join(lines)[-4000:],
            },
        }
    except subprocess.TimeoutExpired:
        return {"status": 0, "error": "Timeout en install/build"}
    except Exception as e:
        return {"status": 0, "error": str(e)}


# --- Zip/tar deploy (Hostinger-like) -----------------------------------------

PRESERVE_ON_REPLACE = {
    ".env",
    ".softi-node.json",
    ".softi-deploys.json",
    ".softi-deploy.log",
    "ecosystem.config.cjs",
    "uploads",
}

UPLOAD_DIR = Path("/tmp/softi-node-uploads")
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024  # 200 MB


def _deploys_path(cwd: str) -> Path:
    return Path(cwd) / ".softi-deploys.json"


def _read_deploys(cwd: str) -> list:
    p = _deploys_path(cwd)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(errors="replace"))
        return list(data.get("deploys") or [])
    except Exception:
        return []


def _append_deploy(cwd: str, entry: dict) -> list:
    deploys = _read_deploys(cwd)
    deploys.insert(0, entry)
    deploys = deploys[:30]  # keep last 30
    path = _deploys_path(cwd)
    path.write_text(json.dumps({"deploys": deploys}, indent=2) + "\n")
    uid, gid = _site_owner_ids(cwd)
    if uid is not None:
        try:
            os.chown(path, uid, gid)
        except Exception:
            pass
    return deploys


def _valid_upload_archive(path: Path) -> str | None:
    """Return error string or None if OK."""
    if not path.is_file():
        return "Archivo no encontrado"
    try:
        resolved = path.resolve()
    except Exception:
        return "Ruta inválida"
    # only /tmp/softi-node-uploads or /tmp
    allowed_roots = [UPLOAD_DIR.resolve(), Path("/tmp").resolve()]
    if not any(str(resolved).startswith(str(r) + os.sep) or resolved == r for r in allowed_roots):
        return "Archivo fuera de zona de upload"
    if ".." in str(path):
        return "Ruta inválida"
    size = path.stat().st_size
    if size <= 0:
        return "Archivo vacío"
    if size > MAX_ARCHIVE_BYTES:
        return f"Archivo demasiado grande (máx {MAX_ARCHIVE_BYTES // (1024*1024)} MB)"
    name = path.name.lower()
    if not (
        name.endswith(".zip")
        or name.endswith(".tar.gz")
        or name.endswith(".tgz")
        or name.endswith(".tar")
    ):
        return "Formato no soportado (.zip, .tar.gz, .tgz, .tar)"
    return None


def _clear_cwd_preserve(cwd: Path) -> None:
    for child in list(cwd.iterdir()):
        if child.name in PRESERVE_ON_REPLACE:
            continue
        if child.is_dir() and not child.is_symlink():
            subprocess.run(["rm", "-rf", str(child)], check=False)
        else:
            try:
                child.unlink()
            except Exception:
                subprocess.run(["rm", "-f", str(child)], check=False)


def _safe_extract_members(members, dest: Path):
    """Yield members that stay under dest (zip-slip guard)."""
    dest_res = dest.resolve()
    for m in members:
        name = getattr(m, "filename", None) or getattr(m, "name", "")
        if not name or name.startswith("/") or ".." in Path(name).parts:
            continue
        target = (dest / name).resolve()
        if not str(target).startswith(str(dest_res)):
            continue
        yield m


def _extract_archive(archive: Path, dest: Path) -> None:
    import tarfile
    import zipfile

    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            for m in _safe_extract_members(zf.infolist(), dest):
                zf.extract(m, path=dest)
    else:
        mode = "r:gz" if (name.endswith(".tar.gz") or name.endswith(".tgz")) else "r:"
        with tarfile.open(archive, mode) as tf:
            members = list(_safe_extract_members(tf.getmembers(), dest))
            # Python 3.12+ has filter=; keep compatible
            try:
                tf.extractall(path=dest, members=members, filter="data")
            except TypeError:
                tf.extractall(path=dest, members=members)


def _flatten_single_root(dest: Path) -> None:
    """If extract produced one top-level dir, move its contents up."""
    kids = [c for c in dest.iterdir() if c.name not in PRESERVE_ON_REPLACE]
    if len(kids) != 1 or not kids[0].is_dir():
        return
    root = kids[0]
    for item in list(root.iterdir()):
        target = dest / item.name
        if target.exists():
            if target.is_dir():
                subprocess.run(["rm", "-rf", str(target)], check=False)
            else:
                target.unlink(missing_ok=True)
        item.rename(target)
    try:
        root.rmdir()
    except Exception:
        subprocess.run(["rm", "-rf", str(root)], check=False)


def handle_deploy_archive(payload: dict):
    """
    Extract uploaded archive into app cwd.
    Payload: cwd, archive_path, replace (bool), filename (optional),
             pm2_name (optional, for history)
    """
    try:
        cwd = (payload.get("cwd") or "").strip()
        archive_path = (payload.get("archive_path") or "").strip()
        replace = bool(payload.get("replace", True))
        filename = (payload.get("filename") or Path(archive_path).name).strip()
        pm2_name = (payload.get("pm2_name") or "").strip()

        if not _valid_cwd(cwd):
            return {"status": 0, "error": "cwd inválido"}
        arch = Path(archive_path)
        err = _valid_upload_archive(arch)
        if err:
            return {"status": 0, "error": err}

        dest = Path(cwd)
        if replace:
            _clear_cwd_preserve(dest)

        _extract_archive(arch, dest)
        _flatten_single_root(dest)

        uid, gid = _site_owner_ids(cwd)
        if uid is not None:
            _chown_tree(cwd, uid, gid)

        import time as _t
        import uuid as _uuid

        entry = {
            "id": str(_uuid.uuid4()),
            "at": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
            "source": "upload",
            "filename": filename,
            "replace": replace,
            "pm2_name": pm2_name,
            "status": "extracted",
            "error": "",
        }
        deploys = _append_deploy(cwd, entry)

        # cleanup upload
        try:
            arch.unlink(missing_ok=True)
        except Exception:
            pass

        return {
            "status": 1,
            "data": {
                "deploy": entry,
                "deploys": deploys[:10],
                "cwd": cwd,
            },
        }
    except Exception as e:
        return {"status": 0, "error": str(e)}


def handle_list_deploys(cwd: str):
    if not _valid_cwd(cwd):
        return {"status": 0, "error": "cwd inválido"}
    return {"status": 1, "data": {"deploys": _read_deploys(cwd)[:20]}}


def handle_mark_deploy(cwd: str, deploy_id: str, status: str, error: str = ""):
    if not _valid_cwd(cwd):
        return {"status": 0, "error": "cwd inválido"}
    deploys = _read_deploys(cwd)
    for d in deploys:
        if d.get("id") == deploy_id:
            d["status"] = status
            d["error"] = (error or "")[:2000]
            break
    path = _deploys_path(cwd)
    path.write_text(json.dumps({"deploys": deploys}, indent=2) + "\n")
    return {"status": 1, "data": {"deploys": deploys[:20]}}


def time_stamp():
    import time as _t

    return _t.strftime("%Y-%m-%d %H:%M:%S")


def _write_ecosystem_with_node(cwd: str, info: dict, env: dict, node_bin: str) -> None:
    name = info["pm2_name"]
    script = info["script"]
    port = int(info["port"])
    merged = dict(env)
    merged["PORT"] = str(port)
    merged["NODE_ENV"] = merged.get("NODE_ENV", "production")
    env_js = json.dumps(merged)
    content = (
        "// Softi Node PaaS — managed ecosystem (do not edit by hand)\n"
        "module.exports = {\n"
        "  apps: [{\n"
        f"    name: {json.dumps(name)},\n"
        f"    script: {json.dumps(script)},\n"
        f"    cwd: {json.dumps(cwd)},\n"
        f"    interpreter: {json.dumps(node_bin)},\n"
        "    instances: 1,\n"
        "    autorestart: true,\n"
        "    max_memory_restart: '512M',\n"
        f"    env: {env_js}\n"
        "  }]\n"
        "};\n"
    )
    Path(cwd).joinpath("ecosystem.config.cjs").write_text(content)


def handle_proxy_configure(domain, port, app_name="app", restart=True):
    try:
        import sys

        if "/usr/local/CyberCP" not in sys.path:
            sys.path.insert(0, "/usr/local/CyberCP")
        from plogical.softiNodeProxy import _configure_impl

        ok, msg = _configure_impl(domain, int(port), app_name or "app", bool(restart))
        if ok:
            return {"status": 1, "data": msg}
        return {"status": 0, "error": msg}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def handle_proxy_remove(domain, restart=True):
    try:
        import sys

        if "/usr/local/CyberCP" not in sys.path:
            sys.path.insert(0, "/usr/local/CyberCP")
        from plogical.softiNodeProxy import _remove_impl

        ok, msg = _remove_impl(domain, bool(restart))
        if ok:
            return {"status": 1, "data": msg}
        return {"status": 0, "error": msg}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def handle_proxy_inspect(domain):
    try:
        import sys

        if "/usr/local/CyberCP" not in sys.path:
            sys.path.insert(0, "/usr/local/CyberCP")
        from plogical.softiNodeProxy import _inspect_impl

        return {"status": 1, "data": _inspect_impl(domain)}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def handle_guess_port(cwd):
    """Read PORT from cwd as root (panel user often cannot traverse site homes)."""
    if not cwd or ".." in cwd or not str(cwd).startswith("/home/"):
        return {"status": 0, "error": "cwd inválido"}
    try:
        port = None
        pdir = Path(cwd)
        if not pdir.is_dir():
            return {"status": 0, "error": "cwd no existe"}
        meta = pdir / ".softi-node.json"
        if meta.is_file():
            data = json.loads(meta.read_text())
            if data.get("port"):
                port = int(data["port"])
        if port is None:
            envf = pdir / ".env"
            if envf.is_file():
                for line in envf.read_text(errors="replace").splitlines():
                    if line.strip().startswith("PORT="):
                        port = int(line.split("=", 1)[1].strip().strip('"'))
                        break
        return {"status": 1, "data": {"port": port}}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def _port_in_use(port: int) -> bool:
    try:
        out = subprocess.check_output(
            ["ss", "-ltn"], text=True, stderr=subprocess.DEVNULL
        )
        return f":{port} " in out or f":{port}\n" in out
    except Exception:
        return False


async def handle_client(reader, writer):
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=30)
        request = json.loads(line.decode())
        cmd = request.get("cmd")
        if cmd not in ALLOWED_CMDS:
            response = {"status": 0, "error": f"Comando '{cmd}' no permitido"}
        elif cmd == "list":
            response = handle_list()
        elif cmd == "restart":
            response = handle_restart(request.get("name", ""))
        elif cmd == "start":
            response = handle_start(request.get("name", ""))
        elif cmd == "stop":
            response = handle_stop(request.get("name", ""))
        elif cmd == "delete":
            response = handle_delete(request.get("name", ""))
        elif cmd == "status":
            response = handle_status(request.get("name", ""))
        elif cmd == "logs":
            response = handle_logs(request.get("name", ""), request.get("lines", 100))
        elif cmd == "flush_logs":
            response = handle_flush_logs(request.get("name", ""))
        elif cmd == "get_env":
            response = handle_get_env(request.get("name", ""), request.get("cwd"))
        elif cmd == "set_env":
            response = handle_set_env(
                request.get("name", ""),
                request.get("env") or {},
                request.get("cwd"),
                request.get("restart", True),
            )
        elif cmd == "upsert_env":
            response = handle_upsert_env(
                request.get("name", ""),
                request.get("key", ""),
                request.get("value", ""),
                request.get("cwd"),
                request.get("restart", True),
            )
        elif cmd == "delete_env":
            response = handle_delete_env(
                request.get("name", ""),
                request.get("key", ""),
                request.get("cwd"),
                request.get("restart", True),
            )
        elif cmd == "import_env":
            response = handle_import_env(
                request.get("name", ""),
                request.get("content", ""),
                request.get("cwd"),
                request.get("restart", True),
            )
        elif cmd == "create":
            response = handle_create(request)
        elif cmd == "proxy_configure":
            response = handle_proxy_configure(
                request.get("domain", ""),
                request.get("port"),
                request.get("app_name", "app"),
                request.get("restart", True),
            )
        elif cmd == "proxy_remove":
            response = handle_proxy_remove(
                request.get("domain", ""),
                request.get("restart", True),
            )
        elif cmd == "proxy_inspect":
            response = handle_proxy_inspect(request.get("domain", ""))
        elif cmd == "guess_port":
            response = handle_guess_port(request.get("cwd", ""))
        elif cmd == "registry_load":
            response = handle_registry_load()
        elif cmd == "registry_save":
            response = handle_registry_save(request.get("data") or {})
        elif cmd == "chown_tree":
            response = handle_chown_tree(request.get("path", ""))
        elif cmd == "list_node_versions":
            response = handle_list_node_versions()
        elif cmd == "redeploy":
            response = handle_redeploy(request)
        elif cmd == "deploy_archive":
            response = handle_deploy_archive(request)
        elif cmd == "list_deploys":
            response = handle_list_deploys(request.get("cwd", ""))
        elif cmd == "mark_deploy":
            response = handle_mark_deploy(
                request.get("cwd", ""),
                request.get("deploy_id", ""),
                request.get("status", ""),
                request.get("error", ""),
            )
        else:
            response = {"status": 0, "error": "Comando desconocido"}
    except (json.JSONDecodeError, asyncio.TimeoutError) as e:
        response = {"status": 0, "error": str(e)}
    except Exception as e:
        response = {"status": 0, "error": str(e)}
    writer.write(json.dumps(response).encode() + b"\n")
    await writer.drain()
    writer.close()


async def main():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = await asyncio.start_unix_server(handle_client, path=SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o660)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
