import json
import os
import re
import time
import uuid

from django.shortcuts import HttpResponse
from plogical.httpProc import httpProc
from plogical.acl import ACLManager
from . import pm2Manager
from . import nodeRegistry


def _require_admin(request):
    userID = request.session.get("userID")
    currentACL = ACLManager.loadedACL(userID)
    if currentACL.get("admin") != 1:
        return None, ACLManager.loadErrorJson()
    return currentACL, None


def _json(payload, status=200):
    return HttpResponse(json.dumps(payload), status=status, content_type="application/json")


def listAppsPage(request):
    proc = httpProc(request, "nodeManager/listApps.html", {"status": 1}, "admin")
    return proc.render()


def createAppPage(request):
    proc = httpProc(request, "nodeManager/createApp.html", {"status": 1}, "admin")
    return proc.render()


def appDetailPage(request, app_id):
    app = nodeRegistry.get_by_id(app_id)
    proc = httpProc(
        request,
        "nodeManager/appDetail.html",
        {"status": 1, "app_id": app_id, "app": app or {}},
        "admin",
    )
    return proc.render()


def listApps(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err

        pm2_apps, error = pm2Manager.list_apps()
        if pm2_apps is None:
            pm2_apps = []
            # still return registry with missing status
            if error and "socket" in error.lower():
                return _json({"status": 0, "error_message": error})

        registry = nodeRegistry.list_apps()
        apps = nodeRegistry.merge_pm2_status(registry, pm2_apps)
        orphan = nodeRegistry.unregistered_pm2(pm2_apps)
        return _json(
            {
                "status": 1,
                "apps": apps,
                "pm2_raw_count": len(pm2_apps),
                "unregistered_count": len(orphan),
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def listUnregistered(request):
    """PM2 processes not yet in Softi registry."""
    try:
        _, err = _require_admin(request)
        if err:
            return err
        pm2_apps, error = pm2Manager.list_apps()
        if pm2_apps is None:
            return _json({"status": 0, "error_message": error})
        return _json(
            {
                "status": 1,
                "apps": nodeRegistry.unregistered_pm2(pm2_apps),
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def importApp(request):
    """
    Register an existing PM2 process as Softi Node App + optional OLS proxy.
    Body: { pm2_name, domain, name?, port?, configure_proxy?: true }
    """
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})

        data = json.loads(request.body)
        pm2_name = (data.get("pm2_name") or data.get("name") or "").strip()
        domain = (data.get("domain") or "").strip().lower()
        friendly = (data.get("app_name") or data.get("friendly_name") or "").strip()
        configure_proxy = bool(data.get("configure_proxy", True))
        force_proxy = bool(data.get("force_proxy", False))

        if not pm2_name:
            return _json({"status": 0, "error_message": "Falta pm2_name"})
        if not domain or "/" in domain or ".." in domain:
            return _json({"status": 0, "error_message": "Dominio inválido"})

        if nodeRegistry.get_by_pm2_name(pm2_name):
            return _json({"status": 0, "error_message": "Ya está registrada"})

        for existing in nodeRegistry.list_apps():
            if existing.get("domain") == domain:
                return _json(
                    {
                        "status": 0,
                        "error_message": f"Ya hay una Node app en {domain}",
                    }
                )

        try:
            from websiteFunctions.models import Websites, ChildDomains

            exists = (
                Websites.objects.filter(domain=domain).exists()
                or ChildDomains.objects.filter(domain=domain).exists()
            )
            if not exists:
                return _json(
                    {
                        "status": 0,
                        "error_message": f"Dominio '{domain}' no existe en CyberPanel",
                    }
                )
        except Exception as e:
            return _json({"status": 0, "error_message": f"Error validando dominio: {e}"})

        from plogical import softiNodeProxy

        proxy_info = softiNodeProxy.inspect(domain)
        proxy_msg = ""
        # Safety: do not rewrite vhost/htaccess if any proxy already exists
        if configure_proxy and proxy_info.get("has_proxy") and not force_proxy:
            configure_proxy = False
            proxy_msg = (
                "Proxy OLS ya existía — se dejó intacto. "
                + (proxy_info.get("summary") or "")
            )
        elif not configure_proxy and proxy_info.get("has_proxy"):
            proxy_msg = "Import sin tocar proxy. " + (proxy_info.get("summary") or "")

        pm2_apps, error = pm2Manager.list_apps()
        if pm2_apps is None:
            return _json({"status": 0, "error_message": error})
        match = next((p for p in pm2_apps if p.get("name") == pm2_name), None)
        if not match:
            return _json(
                {"status": 0, "error_message": f"Proceso PM2 '{pm2_name}' no encontrado"}
            )

        if not friendly:
            # derive from pm2 name
            friendly = pm2_name.split("__")[-1] if "__" in pm2_name else pm2_name
            friendly = re.sub(r"[^a-zA-Z0-9_-]", "-", friendly)[:48]
            if nodeRegistry.validate_name(friendly):
                friendly = "app"

        name_err = nodeRegistry.validate_name(friendly)
        if name_err:
            return _json({"status": 0, "error_message": name_err})

        preferred = data.get("port")
        if preferred in (None, "",):
            preferred = nodeRegistry.guess_port_from_pm2(match)
        port, perr = nodeRegistry.alloc_port(preferred if preferred else None)
        if perr:
            # if guessed port outside Softi range, still allow if explicitly set
            if preferred is not None:
                try:
                    port = int(preferred)
                    if port < 1 or port > 65535:
                        return _json({"status": 0, "error_message": "Puerto inválido"})
                    if port in nodeRegistry.used_ports():
                        return _json(
                            {"status": 0, "error_message": f"Puerto {port} ya asignado"}
                        )
                except (TypeError, ValueError):
                    return _json({"status": 0, "error_message": perr})
            else:
                return _json(
                    {
                        "status": 0,
                        "error_message": perr
                        + ". Indica el puerto en el que escucha la app.",
                    }
                )

        cwd = match.get("cwd") or f"/home/{domain}/nodejs/{friendly}"
        script = match.get("script") or "server.js"
        # script may be absolute path
        if isinstance(script, str) and script.startswith("/") and cwd:
            try:
                script = os.path.relpath(script, cwd)
            except Exception:
                script = os.path.basename(script)

        if configure_proxy:
            ok, cfg_msg = softiNodeProxy.configure(
                domain, port, app_name=friendly, restart=True
            )
            if not ok:
                return _json(
                    {
                        "status": 0,
                        "error_message": f"No se pudo configurar proxy: {cfg_msg}",
                    }
                )
            proxy_msg = cfg_msg

        app = {
            "id": str(uuid.uuid4()),
            "name": friendly,
            "pm2_name": pm2_name,
            "domain": domain,
            "port": port,
            "cwd": cwd,
            "script": script,
            "url": f"https://{domain}/",
            "imported": True,
            "proxy_managed_by_softi": bool(configure_proxy),
            "proxy_preexisting": bool(proxy_info.get("has_proxy")),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        nodeRegistry.upsert(app)
        return _json(
            {
                "status": 1,
                "app": app,
                "message": proxy_msg or "Importada sin cambiar proxy",
                "proxy": proxy_info,
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def inspectProxy(request):
    """GET /nodemanager/inspectProxy?domain=... — detect existing OLS proxy."""
    try:
        _, err = _require_admin(request)
        if err:
            return err
        domain = (request.GET.get("domain") or "").strip().lower()
        if not domain:
            return _json({"status": 0, "error_message": "Falta domain"})
        from plogical import softiNodeProxy

        return _json({"status": 1, "proxy": softiNodeProxy.inspect(domain)})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def listWebsites(request):
    """Domains available for Node apps (admin)."""
    try:
        _, err = _require_admin(request)
        if err:
            return err
        from websiteFunctions.models import Websites, ChildDomains

        domains = []
        for w in Websites.objects.all().order_by("domain"):
            domains.append({"domain": w.domain, "type": "website"})
        for c in ChildDomains.objects.all().order_by("domain"):
            domains.append({"domain": c.domain, "type": "child"})
        return _json({"status": 1, "domains": domains})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def createApp(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})

        data = json.loads(request.body)
        name = (data.get("name") or "").strip()
        domain = (data.get("domain") or "").strip().lower()
        script = (data.get("entry_file") or data.get("script") or "server.js").strip()
        preferred_port = data.get("port")

        preset = (data.get("framework_preset") or "other").strip().lower()
        if preset not in ("other", "nestjs", "next", "express"):
            preset = "other"
        pkg = (data.get("package_manager") or "npm").strip().lower()
        if pkg not in ("npm", "pnpm", "yarn"):
            pkg = "npm"
        root_dir = (data.get("root_directory") or ".").strip() or "."
        if ".." in root_dir or root_dir.startswith("/"):
            return _json({"status": 0, "error_message": "root_directory inválido"})
        if ".." in script or script.startswith("/"):
            return _json({"status": 0, "error_message": "entry_file inválido"})
        build_cmd = (data.get("build_command") or "").strip()
        output_dir = (data.get("output_directory") or "").strip()
        if output_dir and (".." in output_dir or output_dir.startswith("/")):
            return _json({"status": 0, "error_message": "output_directory inválido"})
        node_version = (data.get("node_version") or "20.19.6").strip().lstrip("v")

        name_err = nodeRegistry.validate_name(name)
        if name_err:
            return _json({"status": 0, "error_message": name_err})
        if not domain or "/" in domain or ".." in domain:
            return _json({"status": 0, "error_message": "Dominio inválido"})

        # Domain must exist as website or child
        try:
            from websiteFunctions.models import Websites, ChildDomains

            exists = (
                Websites.objects.filter(domain=domain).exists()
                or ChildDomains.objects.filter(domain=domain).exists()
            )
            if not exists:
                return _json(
                    {
                        "status": 0,
                        "error_message": f"Dominio '{domain}' no existe en CyberPanel",
                    }
                )
        except Exception as e:
            return _json({"status": 0, "error_message": f"Error validando dominio: {e}"})

        # One Softi Node app per domain in MVP
        for existing in nodeRegistry.list_apps():
            if existing.get("domain") == domain:
                return _json(
                    {
                        "status": 0,
                        "error_message": f"Ya hay una Node app en {domain}",
                    }
                )

        port, perr = nodeRegistry.alloc_port(preferred_port if preferred_port else None)
        if perr:
            return _json({"status": 0, "error_message": perr})

        cwd = f"/home/{domain}/nodejs/{name}"
        pm2_name = nodeRegistry.pm2_name_for(domain, name)

        created, cerr = pm2Manager.create_app(
            {
                "pm2_name": pm2_name,
                "cwd": cwd,
                "script": script,
                "port": port,
                "ensure_dir": True,
                "bootstrap": True,
            }
        )
        if created is None:
            return _json({"status": 0, "error_message": cerr})

        from plogical import softiNodeProxy

        ok, msg = softiNodeProxy.configure(
            domain, port, app_name=name, restart=True
        )
        if not ok:
            # rollback PM2
            pm2Manager.delete_app(pm2_name)
            return _json(
                {"status": 0, "error_message": f"App creada en PM2 pero proxy falló: {msg}"}
            )

        app = {
            "id": str(uuid.uuid4()),
            "name": name,
            "pm2_name": pm2_name,
            "domain": domain,
            "port": port,
            "cwd": cwd,
            "script": script,
            "entry_file": script,
            "framework_preset": preset,
            "node_version": node_version,
            "package_manager": pkg,
            "root_directory": root_dir,
            "build_command": build_cmd,
            "output_directory": output_dir,
            "url": f"https://{domain}/",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        nodeRegistry.upsert(app)
        return _json({"status": 1, "app": app, "message": msg})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def restartApp(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        name = (data.get("name") or data.get("pm2_name") or "").strip()
        if not name:
            return _json({"status": 0, "error_message": "Falta el nombre de la app"})
        ok, message = pm2Manager.restart_app(name)
        return _json({"status": 1 if ok else 0, "error_message": message})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def stopApp(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        name = (data.get("name") or data.get("pm2_name") or "").strip()
        ok, message = pm2Manager.stop_app(name)
        return _json({"status": 1 if ok else 0, "error_message": message})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def startApp(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        name = (data.get("name") or data.get("pm2_name") or "").strip()
        ok, message = pm2Manager.start_app(name)
        return _json({"status": 1 if ok else 0, "error_message": message})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def deleteApp(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        app_id = (data.get("id") or "").strip()
        pm2_name = (data.get("pm2_name") or data.get("name") or "").strip()

        app = None
        if app_id:
            app = nodeRegistry.get_by_id(app_id)
        if not app and pm2_name:
            app = nodeRegistry.get_by_pm2_name(pm2_name)
        if not app:
            return _json({"status": 0, "error_message": "App no encontrada en registro"})

        pm2_name = app["pm2_name"]
        domain = app["domain"]

        pm2Manager.delete_app(pm2_name)  # ignore failure if already gone
        from plogical import softiNodeProxy

        softiNodeProxy.remove(domain, restart=True)
        for alias in app.get("aliases") or []:
            try:
                softiNodeProxy.remove(str(alias).strip(), restart=False)
            except Exception:
                pass
        nodeRegistry.delete(pm2_name=pm2_name)
        return _json({"status": 1, "error_message": f"App '{app.get('name')}' eliminada"})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def attachDomain(request):
    """
    Attach an extra Softi website (alias) to an existing Node app.
    Does not create a second PM2 process — only OLS proxy → same port.
    Requires the domain website to already exist in Softi/CyberPanel.
    """
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        app_id = (data.get("id") or "").strip()
        pm2_name = (data.get("pm2_name") or "").strip()
        alias = (data.get("domain") or data.get("alias") or "").strip().lower()
        app = nodeRegistry.get_by_id(app_id) if app_id else None
        if not app and pm2_name:
            app = nodeRegistry.get_by_pm2_name(pm2_name)
        if not app:
            return _json({"status": 0, "error_message": "App no encontrada"})
        if not alias or ".." in alias or "/" in alias or " " in alias:
            return _json({"status": 0, "error_message": "Dominio inválido"})
        primary = (app.get("domain") or "").strip().lower()
        if alias == primary:
            return _json({"status": 0, "error_message": "Ese ya es el dominio principal"})
        aliases = [str(a).strip().lower() for a in (app.get("aliases") or []) if a]
        if alias in aliases:
            return _json({"status": 0, "error_message": "Alias ya asignado a esta app"})

        # Must exist as Softi website / child
        try:
            from websiteFunctions.models import Websites, ChildDomains

            exists = (
                Websites.objects.filter(domain=alias).exists()
                or ChildDomains.objects.filter(domain=alias).exists()
            )
        except Exception as e:
            return _json({"status": 0, "error_message": f"Error validando dominio: {e}"})
        if not exists:
            return _json(
                {
                    "status": 0,
                    "error_message": (
                        f"Crea primero el sitio web «{alias}» en Softi "
                        "(Websites → Create Website) y luego asígnalo aquí."
                    ),
                }
            )

        # Not used by another Softi Node app
        for other in nodeRegistry.list_apps():
            if other.get("id") == app.get("id"):
                continue
            od = (other.get("domain") or "").strip().lower()
            oaliases = [str(a).strip().lower() for a in (other.get("aliases") or []) if a]
            if alias == od or alias in oaliases:
                return _json(
                    {
                        "status": 0,
                        "error_message": f"Dominio ya usado por app «{other.get('name')}»",
                    }
                )

        port = app.get("port")
        try:
            port = int(port)
        except (TypeError, ValueError):
            return _json({"status": 0, "error_message": "La app no tiene puerto válido"})

        from plogical import softiNodeProxy

        friendly = app.get("name") or "app"
        ok, msg = softiNodeProxy.configure(
            alias, port, app_name=friendly, restart=True
        )
        if not ok:
            return _json({"status": 0, "error_message": f"No se pudo configurar proxy: {msg}"})

        aliases.append(alias)
        app["aliases"] = aliases
        nodeRegistry.upsert(app)
        return _json(
            {
                "status": 1,
                "app": app,
                "error_message": f"Alias {alias} → puerto {port}",
                "message": msg,
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def detachDomain(request):
    """Remove Softi OLS proxy from an alias domain (keeps the website)."""
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        app_id = (data.get("id") or "").strip()
        pm2_name = (data.get("pm2_name") or "").strip()
        alias = (data.get("domain") or data.get("alias") or "").strip().lower()
        app = nodeRegistry.get_by_id(app_id) if app_id else None
        if not app and pm2_name:
            app = nodeRegistry.get_by_pm2_name(pm2_name)
        if not app:
            return _json({"status": 0, "error_message": "App no encontrada"})
        aliases = [str(a).strip().lower() for a in (app.get("aliases") or []) if a]
        if alias not in aliases:
            return _json({"status": 0, "error_message": "Ese dominio no es alias de esta app"})

        from plogical import softiNodeProxy

        softiNodeProxy.remove(alias, restart=True)
        app["aliases"] = [a for a in aliases if a != alias]
        nodeRegistry.upsert(app)
        return _json(
            {
                "status": 1,
                "app": app,
                "error_message": f"Alias {alias} desasignado (sitio Softi intacto)",
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def appLogs(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        pm2_name = (request.GET.get("pm2_name") or "").strip()
        lines = request.GET.get("lines", 100)
        if not pm2_name:
            return _json({"status": 0, "error_message": "Falta pm2_name"})
        logs, error = pm2Manager.app_logs(pm2_name, lines)
        if logs is None:
            return _json({"status": 0, "error_message": error})
        # agent may return str (legacy) or {text, fetched_at, ...}
        if isinstance(logs, dict):
            return _json(
                {
                    "status": 1,
                    "logs": logs.get("text") or "",
                    "stdout": logs.get("stdout") or "",
                    "stderr": logs.get("stderr") or "",
                    "fetched_at": logs.get("fetched_at"),
                    "out_mtime": logs.get("out_mtime"),
                    "err_mtime": logs.get("err_mtime"),
                    "out_bytes": logs.get("out_bytes"),
                    "err_bytes": logs.get("err_bytes"),
                }
            )
        return _json({"status": 1, "logs": logs, "stdout": logs, "stderr": ""})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def flushLogs(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        pm2_name = (data.get("pm2_name") or data.get("name") or "").strip()
        if not pm2_name:
            return _json({"status": 0, "error_message": "Falta pm2_name"})
        ok, message = pm2Manager.flush_logs(pm2_name)
        return _json(
            {
                "status": 1 if ok else 0,
                "error_message": message if isinstance(message, str) else ("OK" if ok else "Error"),
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def getEnv(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        pm2_name = (request.GET.get("pm2_name") or "").strip()
        app = nodeRegistry.get_by_pm2_name(pm2_name)
        cwd = app.get("cwd") if app else None
        data, error = pm2Manager.get_env(pm2_name, cwd)
        if data is None:
            return _json({"status": 0, "error_message": error})
        # New shape: {env, items}; legacy: flat dict
        if isinstance(data, dict) and "items" in data:
            return _json(
                {
                    "status": 1,
                    "env": data.get("env") or {},
                    "items": data.get("items") or [],
                }
            )
        return _json({"status": 1, "env": data, "items": [
            {"key": k, "value": data[k]} for k in sorted(data.keys())
        ]})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def setEnv(request):
    """Legacy full rewrite — UI uses upsertEnv / deleteEnv / importEnv."""
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        pm2_name = (data.get("pm2_name") or "").strip()
        env = data.get("env") or {}
        app = nodeRegistry.get_by_pm2_name(pm2_name)
        cwd = app.get("cwd") if app else None
        if app and "PORT" not in env:
            env["PORT"] = str(app["port"])
        ok, message = pm2Manager.set_env(pm2_name, env, cwd=cwd, restart=True)
        return _json({"status": 1 if ok else 0, "error_message": message})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def upsertEnv(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        pm2_name = (data.get("pm2_name") or "").strip()
        key = (data.get("key") or "").strip()
        value = data.get("value")
        if value is None:
            value = ""
        restart = data.get("restart", True)
        app = nodeRegistry.get_by_pm2_name(pm2_name)
        cwd = app.get("cwd") if app else None
        result, error = pm2Manager.upsert_env(
            pm2_name, key, value, cwd=cwd, restart=bool(restart)
        )
        if result is None:
            return _json({"status": 0, "error_message": error})
        return _json(
            {
                "status": 1,
                "action": result.get("action"),
                "items": result.get("items") or [],
                "error_message": f"Variable {key} guardada",
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def deleteEnv(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        pm2_name = (data.get("pm2_name") or "").strip()
        key = (data.get("key") or "").strip()
        restart = data.get("restart", True)
        app = nodeRegistry.get_by_pm2_name(pm2_name)
        cwd = app.get("cwd") if app else None
        result, error = pm2Manager.delete_env(
            pm2_name, key, cwd=cwd, restart=bool(restart)
        )
        if result is None:
            return _json({"status": 0, "error_message": error})
        return _json(
            {
                "status": 1,
                "items": result.get("items") or [],
                "error_message": f"Variable {key} eliminada",
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def importEnv(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        pm2_name = (data.get("pm2_name") or "").strip()
        content = data.get("content") or ""
        restart = data.get("restart", True)
        app = nodeRegistry.get_by_pm2_name(pm2_name)
        cwd = app.get("cwd") if app else None
        result, error = pm2Manager.import_env(
            pm2_name, content, cwd=cwd, restart=bool(restart)
        )
        if result is None:
            return _json({"status": 0, "error_message": error})
        return _json(
            {
                "status": 1,
                "merged": result.get("merged", 0),
                "items": result.get("items") or [],
                "error_message": f"Importadas {result.get('merged', 0)} variables",
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def updateBuildSettings(request):
    """POST: save Hostinger-like build fields on Softi registry (no deploy yet)."""
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        app_id = (data.get("id") or "").strip()
        app = nodeRegistry.get_by_id(app_id) if app_id else None
        if not app and data.get("pm2_name"):
            app = nodeRegistry.get_by_pm2_name(data.get("pm2_name"))
        if not app:
            return _json({"status": 0, "error_message": "App no encontrada"})

        preset = (data.get("framework_preset") or "other").strip().lower()
        if preset not in ("other", "nestjs", "next", "express"):
            preset = "other"

        pkg = (data.get("package_manager") or "npm").strip().lower()
        if pkg not in ("npm", "pnpm", "yarn"):
            return _json({"status": 0, "error_message": "package_manager inválido"})

        root_dir = (data.get("root_directory") or ".").strip() or "."
        if ".." in root_dir or root_dir.startswith("/"):
            return _json({"status": 0, "error_message": "root_directory inválido"})

        entry = (data.get("entry_file") or data.get("script") or app.get("script") or "server.js").strip()
        if ".." in entry or entry.startswith("/"):
            return _json({"status": 0, "error_message": "entry_file inválido"})

        build_cmd = (data.get("build_command") or "").strip()
        output_dir = (data.get("output_directory") or "").strip()
        if output_dir and (".." in output_dir or output_dir.startswith("/")):
            return _json({"status": 0, "error_message": "output_directory inválido"})

        node_version = (data.get("node_version") or "20.19.6").strip().lstrip("v")

        # Preset fill defaults if fields blank
        if preset == "nestjs" and not build_cmd:
            build_cmd = "npm run build"
            if entry in ("server.js", "app.js", ""):
                entry = "dist/main.js"
        elif preset == "next" and not build_cmd:
            build_cmd = "npm run build"
            if entry in ("server.js", "app.js", ""):
                entry = "node_modules/next/dist/bin/next"

        app.update(
            {
                "framework_preset": preset,
                "node_version": node_version,
                "package_manager": pkg,
                "root_directory": root_dir,
                "build_command": build_cmd,
                "output_directory": output_dir,
                "entry_file": entry,
                "script": entry,
            }
        )
        nodeRegistry.upsert(app)
        return _json({"status": 1, "app": app})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def listNodeVersions(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        data, error = pm2Manager.list_node_versions()
        if data is None:
            return _json({"status": 0, "error_message": error})
        return _json({"status": 1, **data})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def redeployApp(request):
    """POST: npm install + optional build + pm2 restart with selected Node."""
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})
        data = json.loads(request.body)
        app_id = (data.get("id") or "").strip()
        app = nodeRegistry.get_by_id(app_id) if app_id else None
        if not app and data.get("pm2_name"):
            app = nodeRegistry.get_by_pm2_name(data.get("pm2_name"))
        if not app:
            return _json({"status": 0, "error_message": "App no encontrada"})

        # Merge any settings sent with request before deploy
        for key in (
            "framework_preset",
            "node_version",
            "package_manager",
            "root_directory",
            "build_command",
            "output_directory",
            "entry_file",
        ):
            if key in data and data[key] is not None:
                app[key] = data[key]
        if data.get("entry_file"):
            app["script"] = data["entry_file"]
        nodeRegistry.upsert(app)

        payload = {
            "pm2_name": app["pm2_name"],
            "cwd": app["cwd"],
            "port": app["port"],
            "node_version": app.get("node_version") or "20.19.6",
            "package_manager": app.get("package_manager") or "npm",
            "root_directory": app.get("root_directory") or ".",
            "build_command": app.get("build_command") or "",
            "entry_file": app.get("entry_file") or app.get("script") or "server.js",
            "script": app.get("entry_file") or app.get("script") or "server.js",
        }
        result, error, log = pm2Manager.redeploy(payload)
        if result is None:
            return _json(
                {
                    "status": 0,
                    "error_message": error,
                    "log": log or "",
                }
            )
        app["last_deploy_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        app["script"] = result.get("entry_file") or app.get("script")
        app["entry_file"] = app["script"]
        app["node_version"] = result.get("node_version") or app.get("node_version")
        nodeRegistry.upsert(app)
        return _json(
            {
                "status": 1,
                "app": app,
                "deploy": result,
                "error_message": "Redeploy OK",
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def listDeploys(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        pm2_name = (request.GET.get("pm2_name") or "").strip()
        app = nodeRegistry.get_by_pm2_name(pm2_name)
        if not app:
            return _json({"status": 0, "error_message": "App no encontrada"})
        data, error = pm2Manager.list_deploys(app["cwd"])
        if data is None:
            return _json({"status": 0, "error_message": error})
        return _json({"status": 1, "deploys": data.get("deploys") or []})
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})


def uploadDeploy(request):
    """
    POST multipart: file + id|pm2_name + replace(0|1) + run_redeploy(0|1).
    Saves under /tmp/softi-node-uploads, agent extracts (optional wipe), then optional redeploy.
    """
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != "POST":
            return _json({"status": 0, "error_message": "Método no permitido"})

        app_id = (request.POST.get("id") or "").strip()
        pm2_name = (request.POST.get("pm2_name") or "").strip()
        app = nodeRegistry.get_by_id(app_id) if app_id else None
        if not app and pm2_name:
            app = nodeRegistry.get_by_pm2_name(pm2_name)
        if not app:
            return _json({"status": 0, "error_message": "App no encontrada"})

        replace = (request.POST.get("replace") or "1") not in ("0", "false", "False")
        run_redeploy = (request.POST.get("run_redeploy") or "1") not in (
            "0",
            "false",
            "False",
        )

        up = request.FILES.get("file")
        if not up:
            return _json({"status": 0, "error_message": "Falta archivo"})

        fname = os.path.basename(up.name or "upload.zip")
        lower = fname.lower()
        if not (
            lower.endswith(".zip")
            or lower.endswith(".tar.gz")
            or lower.endswith(".tgz")
            or lower.endswith(".tar")
        ):
            return _json(
                {
                    "status": 0,
                    "error_message": "Formato no soportado (.zip, .tar.gz, .tgz, .tar)",
                }
            )

        max_bytes = 200 * 1024 * 1024
        if up.size and up.size > max_bytes:
            return _json({"status": 0, "error_message": "Archivo > 200 MB"})

        upload_dir = "/tmp/softi-node-uploads"
        os.makedirs(upload_dir, mode=0o755, exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", fname)[:80]
        dest_name = f"{uuid.uuid4().hex}_{safe}"
        dest_path = os.path.join(upload_dir, dest_name)

        written = 0
        with open(dest_path, "wb") as out:
            for chunk in up.chunks():
                written += len(chunk)
                if written > max_bytes:
                    out.close()
                    try:
                        os.unlink(dest_path)
                    except OSError:
                        pass
                    return _json({"status": 0, "error_message": "Archivo > 200 MB"})
                out.write(chunk)

        extracted, xerr = pm2Manager.deploy_archive(
            {
                "cwd": app["cwd"],
                "archive_path": dest_path,
                "replace": replace,
                "filename": fname,
                "pm2_name": app["pm2_name"],
            }
        )
        if extracted is None:
            try:
                os.unlink(dest_path)
            except OSError:
                pass
            return _json({"status": 0, "error_message": xerr})

        deploy_meta = extracted.get("deploy") or {}
        deploy_id = deploy_meta.get("id") or ""
        redeploy_result = None
        redeploy_log = ""

        if run_redeploy:
            payload = {
                "pm2_name": app["pm2_name"],
                "cwd": app["cwd"],
                "port": app["port"],
                "node_version": app.get("node_version") or "20.19.6",
                "package_manager": app.get("package_manager") or "npm",
                "root_directory": app.get("root_directory") or ".",
                "build_command": app.get("build_command") or "",
                "entry_file": app.get("entry_file") or app.get("script") or "server.js",
                "script": app.get("entry_file") or app.get("script") or "server.js",
            }
            redeploy_result, rerr, redeploy_log = pm2Manager.redeploy(payload)
            status = "ok" if redeploy_result is not None else "fail"
            err_msg = "" if status == "ok" else (rerr or "redeploy falló")
            if deploy_id:
                pm2Manager.mark_deploy(app["cwd"], deploy_id, status, err_msg)
            if redeploy_result is None:
                return _json(
                    {
                        "status": 0,
                        "error_message": f"Archivo extraído pero redeploy falló: {rerr}",
                        "deploy": deploy_meta,
                        "log": redeploy_log or "",
                        "deploys": (extracted.get("deploys") or []),
                    }
                )
            app["last_deploy_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if redeploy_result.get("entry_file"):
                app["script"] = redeploy_result["entry_file"]
                app["entry_file"] = redeploy_result["entry_file"]
            if redeploy_result.get("node_version"):
                app["node_version"] = redeploy_result["node_version"]
            nodeRegistry.upsert(app)
        else:
            # Zip precompilado / sin install+build: al menos restart para cargar archivos nuevos
            rok, rmsg = pm2Manager.restart_app(app["pm2_name"])
            if not rok:
                if deploy_id:
                    pm2Manager.mark_deploy(
                        app["cwd"], deploy_id, "fail", rmsg or "restart falló"
                    )
                return _json(
                    {
                        "status": 0,
                        "error_message": f"Archivo extraído pero restart falló: {rmsg}",
                        "deploy": deploy_meta,
                        "log": rmsg or "",
                        "deploys": (extracted.get("deploys") or []),
                    }
                )
            if deploy_id:
                pm2Manager.mark_deploy(app["cwd"], deploy_id, "ok", "")
            app["last_deploy_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            nodeRegistry.upsert(app)
            redeploy_log = "Extract OK + PM2 restart (sin install/build)"

        deploys_data, _ = pm2Manager.list_deploys(app["cwd"])
        return _json(
            {
                "status": 1,
                "error_message": (
                    "Deploy OK" if run_redeploy else "Extraído + reinicio OK"
                ),
                "deploy": deploy_meta,
                "redeploy": redeploy_result,
                "log": (redeploy_result or {}).get("log_tail") or redeploy_log or "",
                "deploys": (deploys_data or {}).get("deploys") or [],
                "app": app,
            }
        )
    except Exception as e:
        return _json({"status": 0, "error_message": str(e)})
