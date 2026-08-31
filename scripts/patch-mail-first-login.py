#!/usr/bin/env python3
"""
Parche idempotente SOFTI: primer login webmail (must_change_password).

Aplica en el servidor CyberPanel:
  1. Migración DB (e_users.must_change_password)
  2. mailserverManager.submitEmailCreation — pasa flag al crear cuenta
  3. mailserverManager.submitPasswordChange — limpia flag al cambiar desde panel
  4. mailServer.js — checkbox mustChangePassword en POST
  5. Instala plugin SnappyMail first-login-password

Uso:
  python3 scripts/patch-mail-first-login.py
  python3 scripts/patch-mail-first-login.py --install-plugin-only
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

CYBER = Path('/usr/local/CyberCP')
SCRIPTS = CYBER / 'scripts'
CYBER_PYTHON = CYBER / 'bin' / 'python'


def python_bin() -> str:
    if CYBER_PYTHON.exists():
        return str(CYBER_PYTHON)
    return sys.executable


def run_upgrade_db() -> None:
    upgrade = SCRIPTS / 'upgrade-mail-must-change-password.py'
    if not upgrade.exists():
        print('WARN: falta', upgrade)
        return
    subprocess.check_call([python_bin(), str(upgrade)])


def patch_mailserver_manager(path: Path) -> None:
    text = path.read_text()

    if 'mustChangePassword' in text and 'must_change_password' in text:
        print('mailserverManager.py: ya parcheado')
        return

    old_create = (
        "            result = mailUtilities.createEmailAccount(domainName, userName.lower(), password)\n"
    )
    new_create = (
        "            must_change_password = bool(data.get('mustChangePassword', False))\n"
        "            result = mailUtilities.createEmailAccount(\n"
        "                domainName, userName.lower(), password, None, must_change_password\n"
        "            )\n"
    )
    if old_create not in text:
        raise SystemExit('submitEmailCreation: no se encontró createEmailAccount call')
    text = text.replace(old_create, new_create, 1)

    # submitPasswordChange — limpiar flag tras cambio admin
    marker = '            emailDB.save()\n'
    insert = (
        '            try:\n'
        '                emailDB.must_change_password = False\n'
        '            except Exception:\n'
        '                pass\n'
        '            emailDB.save()\n'
    )
    if 'emailDB.must_change_password = False' not in text:
        count = text.count(marker)
        if count < 1:
            raise SystemExit('submitPasswordChange: no se encontró emailDB.save()')
        text = text.replace(marker, insert, 1)

    path.write_text(text)
    print('mailserverManager.py: parcheado OK')


def patch_mailserver_js(path: Path) -> None:
    text = path.read_text()

    if 'mustChangePassword' in text:
        print(f'{path}: ya parcheado')
        return

    old = (
        "        var data = {\n"
        "            domain: domain,\n"
        "            username: username,\n"
        "            passwordByPass: password,\n"
        "        };\n"
    )
    new = (
        "        var data = {\n"
        "            domain: domain,\n"
        "            username: username,\n"
        "            passwordByPass: password,\n"
        "            mustChangePassword: !!$scope.mustChangePassword,\n"
        "        };\n"
    )
    if old not in text:
        raise SystemExit(f'{path}: bloque data createEmailAccount no encontrado')
    path.write_text(text.replace(old, new, 1))
    print(f'{path}: parcheado OK')


def install_plugin() -> None:
    cmd = (
        '/usr/local/CyberCP/bin/python /usr/local/CyberCP/plogical/mailUtilities.py '
        'InstallFirstLoginPasswordPlugin'
    )
    subprocess.check_call(cmd, shell=True)
    print('Plugin SnappyMail: instalado')


def ensure_cli_handler() -> None:
    """Registra subcomando InstallFirstLoginPasswordPlugin en mailUtilities.py si falta."""
    mu = CYBER / 'plogical' / 'mailUtilities.py'
    text = mu.read_text()
    needle = "elif args.function == 'InstallFirstLoginPasswordPlugin':"
    if needle in text:
        return
    pattern = re.compile(
        r"(elif args\.function == 'InstallMailBoxFoldersPlugin':\n"
        r"\s+mailUtilities\.InstallMailBoxFoldersPlugin\(\))",
        re.M,
    )
    repl = (
        r"\1\n    elif args.function == 'InstallFirstLoginPasswordPlugin':\n"
        r"        mailUtilities.InstallFirstLoginPasswordPlugin()"
    )
    new_text, n = pattern.subn(repl, text, count=1)
    if n != 1:
        print('WARN: no se pudo registrar CLI InstallFirstLoginPasswordPlugin')
        return
    mu.write_text(new_text)
    print('mailUtilities.py CLI: handler registrado')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--install-plugin-only', action='store_true')
    args = parser.parse_args()

    if args.install_plugin_only:
        install_plugin()
        return 0

    run_upgrade_db()
    ensure_cli_handler()

    msm = CYBER / 'mailServer' / 'mailserverManager.py'
    if msm.exists():
        patch_mailserver_manager(msm)
    else:
        print('WARN: no existe', msm)

    js_src = CYBER / 'mailServer' / 'static' / 'mailServer' / 'mailServer.js'
    js_pub = CYBER / 'public' / 'static' / 'mailServer' / 'mailServer.js'

    if js_src.exists():
        patch_mailserver_js(js_src)
    else:
        print('WARN: no existe', js_src)

    if js_pub.exists() and js_pub != js_src:
        patch_mailserver_js(js_pub)

    install_plugin()
    sync_static = CYBER / 'scripts' / 'sync-static.sh'
    if sync_static.exists():
        subprocess.check_call(['bash', str(sync_static)])
        print('static: sync-static.sh ejecutado')
    print('patch-mail-first-login: listo. Reinicia lscpd si el panel no refleja cambios JS.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
