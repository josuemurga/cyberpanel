import json
import socket

AGENT_SOCKET = "/run/pm2-agent.sock"


def _call_agent(payload, timeout=60):
    """Envía un comando al agente PM2 via Unix socket y retorna la respuesta."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(AGENT_SOCKET)
            s.sendall(json.dumps(payload).encode() + b"\n")
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
        return json.loads(data.decode())
    except FileNotFoundError:
        return {
            "status": 0,
            "error": "Agente PM2 no disponible (socket no encontrado)",
        }
    except Exception as e:
        return {"status": 0, "error": str(e)}


def list_apps():
    resp = _call_agent({"cmd": "list"})
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp["data"], None


def restart_app(name):
    resp = _call_agent({"cmd": "restart", "name": name})
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp["data"]


def start_app(name):
    resp = _call_agent({"cmd": "start", "name": name})
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp["data"]


def stop_app(name):
    resp = _call_agent({"cmd": "stop", "name": name})
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp["data"]


def delete_app(name):
    resp = _call_agent({"cmd": "delete", "name": name})
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp["data"]


def create_app(payload: dict):
    body = dict(payload)
    body["cmd"] = "create"
    resp = _call_agent(body, timeout=90)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp["data"], None


def app_logs(name, lines=100):
    resp = _call_agent({"cmd": "logs", "name": name, "lines": lines}, timeout=30)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp["data"], None


def flush_logs(name):
    resp = _call_agent({"cmd": "flush_logs", "name": name}, timeout=30)
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp.get("data", "OK")


def get_env(name, cwd=None):
    payload = {"cmd": "get_env", "name": name}
    if cwd:
        payload["cwd"] = cwd
    resp = _call_agent(payload)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp["data"], None


def set_env(name, env, cwd=None, restart=True):
    payload = {"cmd": "set_env", "name": name, "env": env, "restart": restart}
    if cwd:
        payload["cwd"] = cwd
    resp = _call_agent(payload)
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp["data"]


def upsert_env(name, key, value, cwd=None, restart=True):
    payload = {
        "cmd": "upsert_env",
        "name": name,
        "key": key,
        "value": value,
        "restart": restart,
    }
    if cwd:
        payload["cwd"] = cwd
    resp = _call_agent(payload, timeout=90)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def delete_env(name, key, cwd=None, restart=True):
    payload = {
        "cmd": "delete_env",
        "name": name,
        "key": key,
        "restart": restart,
    }
    if cwd:
        payload["cwd"] = cwd
    resp = _call_agent(payload, timeout=90)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def import_env(name, content, cwd=None, restart=True):
    payload = {
        "cmd": "import_env",
        "name": name,
        "content": content,
        "restart": restart,
    }
    if cwd:
        payload["cwd"] = cwd
    resp = _call_agent(payload, timeout=120)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def app_status(name):
    resp = _call_agent({"cmd": "status", "name": name})
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp["data"], None


def proxy_configure(domain, port, app_name="app", restart=True):
    resp = _call_agent(
        {
            "cmd": "proxy_configure",
            "domain": domain,
            "port": port,
            "app_name": app_name,
            "restart": restart,
        },
        timeout=120,
    )
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp.get("data", "OK")


def proxy_remove(domain, restart=True):
    resp = _call_agent(
        {"cmd": "proxy_remove", "domain": domain, "restart": restart},
        timeout=120,
    )
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp.get("data", "OK")


def proxy_inspect(domain):
    resp = _call_agent({"cmd": "proxy_inspect", "domain": domain}, timeout=30)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def guess_port(cwd):
    resp = _call_agent({"cmd": "guess_port", "cwd": cwd})
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return (resp.get("data") or {}).get("port"), None


def registry_load():
    resp = _call_agent({"cmd": "registry_load"})
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def registry_save(data: dict):
    resp = _call_agent({"cmd": "registry_save", "data": data}, timeout=30)
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp.get("data", "OK")


def chown_tree(path: str):
    resp = _call_agent({"cmd": "chown_tree", "path": path})
    if not resp.get("status"):
        return False, resp.get("error", "Error desconocido")
    return True, resp.get("data")


def list_node_versions():
    resp = _call_agent({"cmd": "list_node_versions"})
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def redeploy(payload: dict):
    resp = _call_agent(dict(payload, cmd="redeploy"), timeout=1200)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido"), resp.get("log")
    return resp.get("data"), None, resp.get("log")


def deploy_archive(payload: dict):
    resp = _call_agent(dict(payload, cmd="deploy_archive"), timeout=300)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def list_deploys(cwd: str):
    resp = _call_agent({"cmd": "list_deploys", "cwd": cwd}, timeout=30)
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None


def mark_deploy(cwd: str, deploy_id: str, status: str, error: str = ""):
    resp = _call_agent(
        {
            "cmd": "mark_deploy",
            "cwd": cwd,
            "deploy_id": deploy_id,
            "status": status,
            "error": error or "",
        },
        timeout=30,
    )
    if not resp.get("status"):
        return None, resp.get("error", "Error desconocido")
    return resp.get("data"), None
