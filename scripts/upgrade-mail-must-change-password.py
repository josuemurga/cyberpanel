#!/usr/bin/env python3
"""
Migración idempotente: columna must_change_password en e_users.
Ejecutar en el servidor CyberPanel (root o usuario con acceso MariaDB).

  python3 /usr/local/CyberCP/scripts/upgrade-mail-must-change-password.py
"""
from __future__ import annotations

import sys

try:
    import MySQLdb
except ImportError:
    print('Instala python3-mysqldb o ejecuta desde el venv de CyberPanel', file=sys.stderr)
    sys.exit(1)


def read_mysql_password() -> str:
    path = '/etc/cyberpanel/mysqlPassword'
    with open(path, encoding='utf-8') as fh:
        return fh.read().strip()


def main() -> int:
    password = read_mysql_password()
    try:
        import MySQLdb
    except ImportError:
        # Fallback: mysql CLI (CyberPanel system python may lack MySQLdb)
        import subprocess
        sql = (
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA='cyberpanel' AND TABLE_NAME='e_users' "
            "AND COLUMN_NAME='must_change_password';"
        )
        out = subprocess.check_output(
            ['mysql', '-uroot', f'-p{password}', '-N', '-e', sql],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out != '0':
            print('OK: e_users.must_change_password ya existe')
            return 0
        subprocess.check_call(
            [
                'mysql', '-uroot', f'-p{password}', 'cyberpanel', '-e',
                'ALTER TABLE e_users ADD must_change_password TINYINT(1) NOT NULL DEFAULT 0',
            ],
            stderr=subprocess.DEVNULL,
        )
        print('OK: columna must_change_password creada en e_users')
        return 0

    conn = MySQLdb.connect(
        host='localhost', user='root', passwd=password, db='cyberpanel', charset='utf8mb4'
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA='cyberpanel' AND TABLE_NAME='e_users' "
        "AND COLUMN_NAME='must_change_password'"
    )
    exists = cur.fetchone()[0]
    if exists:
        print('OK: e_users.must_change_password ya existe')
    else:
        cur.execute(
            'ALTER TABLE e_users ADD must_change_password TINYINT(1) NOT NULL DEFAULT 0'
        )
        conn.commit()
        print('OK: columna must_change_password creada en e_users')
    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
