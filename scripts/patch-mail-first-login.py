#!/usr/bin/env python3
"""
Parche idempotente SOFTI: primer login webmail (must_change_password).

Aplica en el servidor CyberPanel:
  1. Migración DB (e_users.must_change_password)
  2. mailserverManager.submitEmailCreation — pasa flag al crear cuenta
  3. mailserverManager.submitPasswordChange — flag must_change_password (set/clear)
  4. mailServer.js — checkbox mustChangePassword (crear + cambiar contraseña)
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
    changed = False

    old_create = (
        "            result = mailUtilities.createEmailAccount(domainName, userName.lower(), password)\n"
    )
    new_create = (
        "            must_change_password = bool(data.get('mustChangePassword', False))\n"
        "            result = mailUtilities.createEmailAccount(\n"
        "                domainName, userName.lower(), password, None, must_change_password\n"
        "            )\n"
    )
    if old_create in text:
        text = text.replace(old_create, new_create, 1)
        changed = True
        print('submitEmailCreation: parcheado OK')
    elif 'must_change_password = bool(data.get' in text:
        print('submitEmailCreation: ya parcheado')
    else:
        raise SystemExit('submitEmailCreation: no se encontró createEmailAccount call')

    if 'emailDB.must_change_password = False' not in text:
        marker = '            emailDB.save()\n'
        insert = (
            '            try:\n'
            '                emailDB.must_change_password = False\n'
            '            except Exception:\n'
            '                pass\n'
            '            emailDB.save()\n'
        )
        if marker not in text:
            raise SystemExit('submitPasswordChange: no se encontró emailDB.save()')
        text = text.replace(marker, insert, 1)
        changed = True
        print('submitPasswordChange base: parcheado OK')

    if changed:
        path.write_text(text)


def patch_submit_password_change(path: Path) -> None:
    text = path.read_text()
    needle = "if bool(data.get('mustChangePassword', False)):"
    if needle in text:
        print('submitPasswordChange flag: ya parcheado')
        return

    old = (
        "            try:\n"
        "                emailDB.must_change_password = False\n"
        "            except Exception:\n"
        "                pass\n"
        "            emailDB.save()\n"
    )
    new = (
        "            try:\n"
        "                if bool(data.get('mustChangePassword', False)):\n"
        "                    emailDB.must_change_password = True\n"
        "                else:\n"
        "                    emailDB.must_change_password = False\n"
        "            except Exception:\n"
        "                pass\n"
        "            emailDB.save()\n"
    )
    if old not in text:
        print('WARN: submitPasswordChange flag: bloque no encontrado')
        return
    path.write_text(text.replace(old, new, 1))
    print('submitPasswordChange flag: parcheado OK')


def patch_mailserver_js_create(path: Path) -> None:
    text = path.read_text()
    needle = 'mustChangePassword: !!$scope.mustChangePassword,'
    if needle in text:
        print(f'{path}: createEmailAccount JS ya parcheado')
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
    print(f'{path}: createEmailAccount JS parcheado OK')


def patch_mailserver_js_change_password(path: Path) -> None:
    text = path.read_text()
    changed = False

    replacements = [
        (
            "        var data = {\n"
            "            domain: domain,\n"
            "            email: email,\n"
            "            passwordByPass: password,\n"
            "        };\n",
            "        var data = {\n"
            "            domain: domain,\n"
            "            email: email,\n"
            "            passwordByPass: password,\n"
            "            mustChangePassword: !!$scope.mustChangePasswordOnReset,\n"
            "        };\n",
        ),
        (
            "        var data = {\n"
            "            domain: $scope.selectedDomain,\n"
            "            email: $scope.email,\n"
            "            passwordByPass: $scope.password,\n"
            "        };\n",
            "        var data = {\n"
            "            domain: $scope.selectedDomain,\n"
            "            email: $scope.email,\n"
            "            passwordByPass: $scope.password,\n"
            "            mustChangePassword: !!$scope.mustChangePasswordOnReset,\n"
            "        };\n",
        ),
    ]

    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)
            changed = True

    old_init = (
        "    $scope.changePasswordInitial = function (email) {\n"
        "        $scope.email = email;\n"
        "    };\n"
    )
    new_init = (
        "    $scope.changePasswordInitial = function (email) {\n"
        "        $scope.email = email;\n"
        "        $scope.mustChangePasswordOnReset = false;\n"
        "    };\n"
    )
    if old_init in text:
        text = text.replace(old_init, new_init, 1)
        changed = True

    if not changed:
        print(f'{path}: changePassword JS ya parcheado')
        return
    path.write_text(text)
    print(f'{path}: changePassword JS parcheado OK')


def patch_listemails_modal_js(path: Path) -> None:
    text = path.read_text()
    if 'generatePasswordReset' in text:
        print(f'{path}: listEmails modal JS ya parcheado')
        return

    old = (
        "    $scope.changePasswordInitial = function (email) {\n"
        "        $scope.email = email;\n"
        "        $scope.mustChangePasswordOnReset = false;\n"
        "    };\n"
        "\n"
        "    $scope.changePassword = function () {\n"
        "\n"
        "        $scope.cyberpanelLoading = false;\n"
        "\n"
        "\n"
        "        var url = \"/email/submitPasswordChange\";\n"
        "\n"
        "        var data = {\n"
        "            domain: $scope.selectedDomain,\n"
        "            email: $scope.email,\n"
        "            passwordByPass: $scope.password,\n"
        "            mustChangePassword: !!$scope.mustChangePasswordOnReset,\n"
        "        };\n"
        "\n"
        "        var config = {\n"
        "            headers: {\n"
        "                'X-CSRFToken': getCookie('csrftoken')\n"
        "            }\n"
        "        };\n"
        "\n"
        "        $http.post(url, data, config).then(ListInitialDatas, cantLoadInitialDatas);\n"
        "\n"
        "\n"
        "        function ListInitialDatas(response) {\n"
        "            $scope.cyberpanelLoading = true;\n"
        "            if (response.data.status === 1) {\n"
        "                new PNotify({\n"
        "                    title: 'Success!',\n"
        "                    text: 'Password Successfully changed.',\n"
        "                    type: 'success'\n"
        "                });\n"
        "\n"
        "            } else {\n"
        "                new PNotify({\n"
        "                    title: 'Error!',\n"
        "                    text: response.data.error_message,\n"
        "                    type: 'error'\n"
        "                });\n"
        "\n"
        "            }\n"
        "\n"
        "        }\n"
        "\n"
        "        function cantLoadInitialDatas(response) {\n"
        "            $scope.cyberpanelLoading = true;\n"
        "            new PNotify({\n"
        "                title: 'Error!',\n"
        "                text: 'Could not connect to server, please refresh this page.',\n"
        "                type: 'error'\n"
        "            });\n"
        "        }\n"
        "\n"
        "\n"
        "    };\n"
    )
    new = (
        "    $scope.generatedPasswordViewReset = true;\n"
        "\n"
        "    $scope.changePasswordInitial = function (email) {\n"
        "        $scope.email = email;\n"
        "        $scope.password = '';\n"
        "        $scope.mustChangePasswordOnReset = false;\n"
        "        $scope.generatedPasswordViewReset = true;\n"
        "    };\n"
        "\n"
        "    $scope.generatePasswordReset = function () {\n"
        "        $scope.generatedPasswordViewReset = false;\n"
        "        $scope.password = randomPassword(16);\n"
        "    };\n"
        "\n"
        "    $scope.usePasswordReset = function () {\n"
        "        $scope.generatedPasswordViewReset = true;\n"
        "    };\n"
        "\n"
        "    $scope.changePassword = function () {\n"
        "        if (!$scope.password) {\n"
        "            new PNotify({\n"
        "                title: 'Error!',\n"
        "                text: 'Password is required.',\n"
        "                type: 'error'\n"
        "            });\n"
        "            return;\n"
        "        }\n"
        "\n"
        "        $scope.cyberpanelLoading = false;\n"
        "\n"
        "        var url = \"/email/submitPasswordChange\";\n"
        "        var data = {\n"
        "            domain: $scope.selectedDomain,\n"
        "            email: $scope.email,\n"
        "            passwordByPass: $scope.password,\n"
        "            mustChangePassword: !!$scope.mustChangePasswordOnReset,\n"
        "        };\n"
        "        var config = {\n"
        "            headers: {\n"
        "                'X-CSRFToken': getCookie('csrftoken')\n"
        "            }\n"
        "        };\n"
        "\n"
        "        $http.post(url, data, config).then(ListInitialDatas, cantLoadInitialDatas);\n"
        "\n"
        "        function ListInitialDatas(response) {\n"
        "            $scope.cyberpanelLoading = true;\n"
        "            if (response.data.status === 1) {\n"
        "                new PNotify({\n"
        "                    title: 'Success!',\n"
        "                    text: 'Password Successfully changed.',\n"
        "                    type: 'success'\n"
        "                });\n"
        "                $scope.populateCurrentRecords();\n"
        "                $('#changePasswordModal').modal('hide');\n"
        "            } else {\n"
        "                new PNotify({\n"
        "                    title: 'Error!',\n"
        "                    text: response.data.error_message,\n"
        "                    type: 'error'\n"
        "                });\n"
        "            }\n"
        "        }\n"
        "\n"
        "        function cantLoadInitialDatas(response) {\n"
        "            $scope.cyberpanelLoading = true;\n"
        "            new PNotify({\n"
        "                title: 'Error!',\n"
        "                text: 'Could not connect to server, please refresh this page.',\n"
        "                type: 'error'\n"
        "            });\n"
        "        }\n"
        "    };\n"
    )
    if old not in text:
        print(f'WARN: {path}: listEmails modal JS bloque no encontrado')
        return
    path.write_text(text.replace(old, new, 1))
    print(f'{path}: listEmails modal JS parcheado OK')


def patch_mailserver_js(path: Path) -> None:
    patch_mailserver_js_create(path)
    patch_mailserver_js_change_password(path)
    patch_listemails_modal_js(path)


def patch_fetch_emails(path: Path) -> None:
    text = path.read_text()
    needle = "'mustChangePassword': bool(getattr(items, 'must_change_password', False))"
    if needle in text:
        print('fetchEmails: ya parcheado')
        return

    old = (
        "                dic = {'email': items.email,\n"
        "                       'DiskUsage': '%sMB' % items.DiskUsage.rstrip('MB')\n"
        "                       }\n"
    )
    new = (
        "                dic = {'email': items.email,\n"
        "                       'DiskUsage': '%sMB' % items.DiskUsage.rstrip('MB'),\n"
        "                       'mustChangePassword': bool(getattr(items, 'must_change_password', False))\n"
        "                       }\n"
    )
    if old not in text:
        raise SystemExit('fetchEmails: bloque dic no encontrado')
    path.write_text(text.replace(old, new, 1))
    print('fetchEmails: parcheado OK')


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
        patch_submit_password_change(msm)
        patch_fetch_emails(msm)
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
