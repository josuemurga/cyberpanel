"""
mailguard_agent.py — Agente root para monitoreo y bloqueo de correo saliente.
Corre como root via systemd, escucha en Unix socket /run/mailguard-agent.sock.

Protocolo JSON por línea:
  {"cmd": "stats", "hours": 168}
  {"cmd": "queue"}
  {"cmd": "block", "user": "oxaco8026"}
  {"cmd": "unblock", "user": "oxaco8026"}
  {"cmd": "delete_queue", "ids": ["9B2AC52A1B"]}
  {"cmd": "flush_bounces"}
  {"cmd": "force_ipv4"}
"""

import asyncio
import gzip
import json
import os
import pwd
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta

SOCKET_PATH = '/run/mailguard-agent.sock'
BLOCKED_FILE = '/etc/cyberpanel/mailguard-blocked-users'
MAIL_LOGS = [
    '/var/log/mail.log',
    '/var/log/mail.log.1',
    '/var/log/mail.log.2.gz',
    '/var/log/mail.log.3.gz',
    '/var/log/mail.log.4.gz',
]

ALLOWED_CMDS = {
    'stats', 'queue', 'block', 'unblock',
    'delete_queue', 'flush_bounces', 'force_ipv4',
}

PROTECTED_USERS = {
    'root', 'cyberpanel', 'vmail', 'lscpd', 'docker',
    'ftpuser', 'nobody', 'www-data', 'syslog', 'messagebus',
}

USER_RE = re.compile(r'^[a-z][a-z0-9]{2,31}$')
QUEUE_ID_RE = re.compile(r'^[A-F0-9]{6,16}$')
PICKUP_RE = re.compile(
    r'^(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+\S+\s+postfix/pickup\[\d+\]:\s+'
    r'([A-F0-9]+):\s+uid=(\d+)\s+from=<([^>]+)>'
)
SASL_RE = re.compile(r'sasl_username=([^\s,]+)')
SMTP_RE = re.compile(
    r'^(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+\S+\s+postfix/smtp\[\d+\]:\s+'
    r'([A-F0-9]+):\s+to=<([^>]+)>(?:,\s+orig_to=<([^>]+)>)?,\s+relay=([^,]+),.*'
    r'status=(sent|deferred|bounced)'
)
QMGR_FROM_RE = re.compile(
    r'^(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+\S+\s+postfix/qmgr\[\d+\]:\s+'
    r'([A-F0-9]+):\s+from=<([^>]*)>'
)
SYSLOG_RE = re.compile(r'^(\w{3})\s+(\d+)\s+(\d{2}):(\d{2}):(\d{2})')

MONTHS = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}


def run(cmd, timeout=20):
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def parse_syslog_ts(line, now):
    m = SYSLOG_RE.match(line)
    if not m:
        return None
    mon, day, hh, mm, ss = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
    month = MONTHS.get(mon)
    if not month:
        return None
    year = now.year
    try:
        ts = datetime(year, month, day, hh, mm, ss)
    except ValueError:
        return None
    if ts > now + timedelta(days=1):
        ts = datetime(year - 1, month, day, hh, mm, ss)
    return ts


def open_log(path):
    if not os.path.exists(path):
        return None
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'rt', encoding='utf-8', errors='replace')


def read_blocked():
    if not os.path.isfile(BLOCKED_FILE):
        return []
    users = []
    with open(BLOCKED_FILE, 'r', encoding='utf-8') as fh:
        for line in fh:
            name = line.strip()
            if name and not name.startswith('#') and USER_RE.match(name):
                users.append(name)
    return sorted(set(users))


def write_blocked(users):
    os.makedirs(os.path.dirname(BLOCKED_FILE), exist_ok=True)
    with open(BLOCKED_FILE, 'w', encoding='utf-8') as fh:
        fh.write('# Mail Guard — Linux users blocked from local mail submit (PHP mail / sendmail)\n')
        for u in sorted(set(users)):
            fh.write(u + '\n')


def apply_submit_policy(users):
    if users:
        value = ', '.join('!' + u for u in users) + ', static:anyone'
    else:
        value = 'static:anyone'
    stdout, stderr, rc = run(['postconf', '-e', 'authorized_submit_users=' + value])
    if rc != 0:
        return False, stderr or stdout or 'postconf failed'
    _, stderr, rc = run(['postfix', 'reload'])
    if rc != 0:
        return False, stderr or 'postfix reload failed'
    return True, value


def linux_users():
    users = {}
    for entry in pwd.getpwall():
        if 1000 <= entry.pw_uid < 65534:
            home = entry.pw_dir or ''
            domain = ''
            if home.startswith('/home/') and home.count('/') == 2:
                domain = home.split('/')[2]
            users[entry.pw_name] = {
                'uid': entry.pw_uid,
                'home': home,
                'domain_guess': domain,
            }
    return users


def postfix_info():
    keys = [
        'authorized_submit_users',
        'smtp_address_preference',
        'smtp_bind_address',
        'smtp_bind_address6',
        'inet_protocols',
    ]
    info = {}
    stdout, _, rc = run(['postconf'] + keys)
    if rc == 0:
        for line in stdout.splitlines():
            if '=' in line and not line.startswith('postconf:'):
                k, v = line.split('=', 1)
                info[k.strip()] = v.strip()
    return info


def handle_stats(hours):
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        hours = 168
    hours = max(1, min(hours, 24 * 40))
    now = datetime.now()
    cutoff = now - timedelta(hours=hours)

    pickup_by_user = defaultdict(int)
    pickup_by_uid = {}
    sasl_by_user = defaultdict(int)
    from_domain = defaultdict(int)
    smtp_status_qids = {'sent': set(), 'deferred': set(), 'bounced': set()}
    smtp_to_domain = defaultdict(int)
    daily = defaultdict(lambda: {'pickup': 0, 'sasl': 0, 'sent': 0, 'deferred': 0, 'bounced': 0})
    recent_pickup = []
    recent_outbound = []
    files_used = []

    for path in MAIL_LOGS:
        fh = open_log(path)
        if fh is None:
            continue
        used = False
        try:
            for line in fh:
                ts = parse_syslog_ts(line, now)
                if ts is None or ts < cutoff:
                    continue
                used = True
                day = ts.strftime('%Y-%m-%d')

                if 'postfix/pickup[' in line and 'uid=' in line:
                    m = PICKUP_RE.search(line)
                    if not m:
                        continue
                    user = m.group(4)
                    uid = int(m.group(3))
                    pickup_by_user[user] += 1
                    pickup_by_uid[user] = uid
                    daily[day]['pickup'] += 1
                    recent_pickup.append({
                        'time': ts.strftime('%Y-%m-%d %H:%M:%S'),
                        'user': user,
                        'uid': uid,
                        'qid': m.group(2),
                    })
                    continue

                if 'sasl_username=' in line:
                    m = SASL_RE.search(line)
                    if m:
                        sasl_by_user[m.group(1)] += 1
                        daily[day]['sasl'] += 1
                    continue

                if 'postfix/qmgr[' in line and 'from=<' in line:
                    m = QMGR_FROM_RE.search(line)
                    if m:
                        envelope = m.group(3)
                        if not envelope:
                            from_domain['(MAILER-DAEMON)'] += 1
                        elif '@' in envelope:
                            from_domain[envelope.split('@', 1)[1].lower()] += 1
                        else:
                            from_domain[envelope] += 1
                    continue

                if 'postfix/smtp[' in line and 'status=' in line:
                    if 'relay=dovecot' in line:
                        continue
                    m = SMTP_RE.search(line)
                    if not m:
                        continue
                    qid, to_addr, orig_to, relay, status = m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
                    smtp_status_qids[status].add(qid)
                    daily[day][status] += 1
                    if '@' in to_addr:
                        smtp_to_domain[to_addr.split('@', 1)[1].lower()] += 1
                    recent_outbound.append({
                        'time': ts.strftime('%Y-%m-%d %H:%M:%S'),
                        'qid': qid,
                        'to': to_addr,
                        'orig_to': orig_to or '',
                        'relay': relay,
                        'status': status,
                    })
        finally:
            fh.close()
        if used:
            files_used.append(os.path.basename(path))

    recent_pickup = recent_pickup[-40:]
    recent_pickup.reverse()
    recent_outbound = recent_outbound[-40:]
    recent_outbound.reverse()

    by_linux_user = [
        {'user': u, 'uid': pickup_by_uid.get(u), 'pickup': c}
        for u, c in sorted(pickup_by_user.items(), key=lambda x: -x[1])
    ]
    by_sasl = [
        {'username': u, 'count': c}
        for u, c in sorted(sasl_by_user.items(), key=lambda x: -x[1])
    ]
    by_from = [
        {'domain': d, 'count': c}
        for d, c in sorted(from_domain.items(), key=lambda x: -x[1])[:40]
    ]
    by_to = [
        {'domain': d, 'count': c}
        for d, c in sorted(smtp_to_domain.items(), key=lambda x: -x[1])[:40]
    ]
    daily_rows = [
        {'day': d, **daily[d]}
        for d in sorted(daily.keys())
    ]

    return {
        'status': 1,
        'data': {
            'period_hours': hours,
            'files': files_used,
            'summary': {
                'pickup': sum(pickup_by_user.values()),
                'sasl': sum(sasl_by_user.values()),
                'smtp_sent': len(smtp_status_qids['sent']),
                'smtp_deferred': len(smtp_status_qids['deferred']),
                'smtp_bounced': len(smtp_status_qids['bounced']),
                'smtp_deferred_events': sum(v['deferred'] for v in daily.values()),
            },
            'by_linux_user': by_linux_user,
            'by_sasl': by_sasl,
            'by_from_domain': by_from,
            'by_to_domain': by_to,
            'daily': daily_rows,
            'recent_pickup': recent_pickup,
            'recent_outbound': recent_outbound,
            'blocked_users': read_blocked(),
            'linux_users': linux_users(),
            'postfix': postfix_info(),
        },
    }


def handle_queue():
    stdout, stderr, rc = run(['postqueue', '-j'])
    if rc != 0:
        return {'status': 0, 'error': stderr or 'postqueue failed'}
    items = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {'status': 1, 'data': {'items': items, 'count': len(items)}}


def _safe_user(name):
    name = (name or '').strip()
    if not USER_RE.match(name):
        return None
    if name in PROTECTED_USERS:
        return None
    known = {e.pw_name for e in pwd.getpwall()}
    if name not in known:
        return None
    return name


def handle_block(name):
    user = _safe_user(name)
    if not user:
        return {'status': 0, 'error': 'Usuario inválido o protegido'}
    users = read_blocked()
    if user not in users:
        users.append(user)
    write_blocked(users)
    ok, msg = apply_submit_policy(users)
    if not ok:
        return {'status': 0, 'error': msg}
    return {'status': 1, 'data': f'PHP/sendmail bloqueado para {user}'}


def handle_unblock(name):
    user = _safe_user(name)
    if not user:
        return {'status': 0, 'error': 'Usuario inválido o protegido'}
    users = [u for u in read_blocked() if u != user]
    write_blocked(users)
    ok, msg = apply_submit_policy(users)
    if not ok:
        return {'status': 0, 'error': msg}
    return {'status': 1, 'data': f'PHP/sendmail habilitado para {user}'}


def handle_delete_queue(ids):
    if not isinstance(ids, list) or not ids:
        return {'status': 0, 'error': 'Faltan IDs de cola'}
    deleted = []
    errors = []
    for qid in ids[:50]:
        qid = str(qid).strip().upper()
        if not QUEUE_ID_RE.match(qid):
            errors.append(qid)
            continue
        _, stderr, rc = run(['postsuper', '-d', qid])
        if rc == 0:
            deleted.append(qid)
        else:
            errors.append(qid + ': ' + (stderr or 'error'))
    return {
        'status': 1 if deleted else 0,
        'data': f'Eliminados: {len(deleted)}',
        'deleted': deleted,
        'error': '; '.join(errors) if errors else None,
    }


def handle_flush_bounces():
    q = handle_queue()
    if not q.get('status'):
        return q
    ids = []
    for item in q['data']['items']:
        sender = (item.get('sender') or '').upper()
        if sender in ('MAILER-DAEMON', ''):
            ids.append(item.get('queue_id'))
    if not ids:
        return {'status': 1, 'data': 'No hay bounces en cola'}
    return handle_delete_queue(ids)


def handle_force_ipv4():
    _, stderr, rc = run(['postconf', '-e', 'smtp_address_preference=ipv4'])
    if rc != 0:
        return {'status': 0, 'error': stderr or 'postconf failed'}
    _, stderr, rc = run(['postfix', 'reload'])
    if rc != 0:
        return {'status': 0, 'error': stderr or 'postfix reload failed'}
    return {'status': 1, 'data': 'smtp_address_preference=ipv4 aplicado. El correo saliente usará IPv4 (SPF ip4).'}


async def handle_client(reader, writer):
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=15)
        request = json.loads(line.decode())
        cmd = request.get('cmd')
        if cmd not in ALLOWED_CMDS:
            response = {'status': 0, 'error': f"Comando '{cmd}' no permitido"}
        elif cmd == 'stats':
            response = handle_stats(request.get('hours', 168))
        elif cmd == 'queue':
            response = handle_queue()
        elif cmd == 'block':
            response = handle_block(request.get('user', ''))
        elif cmd == 'unblock':
            response = handle_unblock(request.get('user', ''))
        elif cmd == 'delete_queue':
            response = handle_delete_queue(request.get('ids', []))
        elif cmd == 'flush_bounces':
            response = handle_flush_bounces()
        elif cmd == 'force_ipv4':
            response = handle_force_ipv4()
        else:
            response = {'status': 0, 'error': 'Comando desconocido'}
    except (json.JSONDecodeError, asyncio.TimeoutError) as e:
        response = {'status': 0, 'error': str(e)}
    except Exception as e:
        response = {'status': 0, 'error': str(e)}
    writer.write(json.dumps(response).encode() + b'\n')
    await writer.drain()
    writer.close()


async def main():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = await asyncio.start_unix_server(handle_client, path=SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o660)

    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
