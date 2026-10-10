import json
from django.shortcuts import HttpResponse
from django.db import connection
from plogical.httpProc import httpProc
from plogical.acl import ACLManager
from . import mailGuardManager


def _require_admin(request):
    userID = request.session.get('userID')
    currentACL = ACLManager.loadedACL(userID)
    if currentACL['admin'] != 1:
        return None, ACLManager.loadErrorJson()
    return currentACL, None


def _json(payload):
    return HttpResponse(json.dumps(payload))


def _hosted_sites():
    """Sitios CyberPanel: domain + linux user (externalApp)."""
    sites = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT domain, externalApp, adminEmail, state '
                'FROM websiteFunctions_websites ORDER BY domain'
            )
            for domain, external_app, admin_email, state in cursor.fetchall():
                sites.append({
                    'domain': domain,
                    'user': external_app or '',
                    'adminEmail': admin_email or '',
                    'state': state,
                })
    except Exception:
        pass
    return sites


def _forwardings():
    rows = []
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT source, destination FROM e_forwardings ORDER BY source')
            for source, destination in cursor.fetchall():
                rows.append({
                    'source': source,
                    'destination': destination or '',
                    'external': '@' in (destination or '') and not (destination or '').endswith(source.split('@')[-1] if '@' in source else ''),
                })
    except Exception:
        pass
    hosted = {s['domain'].lower() for s in _hosted_sites()}
    for row in rows:
        dest = (row['destination'] or '').lower()
        dest_domain = dest.split('@')[-1] if '@' in dest else ''
        row['external'] = bool(dest_domain) and dest_domain not in hosted and dest != (row['source'] or '').lower()
    return rows


def homePage(request):
    proc = httpProc(request, 'mailGuard/home.html', {'status': 1}, 'admin')
    return proc.render()


def stats(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        hours = 168
        if request.GET.get('hours'):
            try:
                hours = int(request.GET.get('hours'))
            except ValueError:
                hours = 168
        data, error = mailGuardManager.get_stats(hours)
        if data is None:
            return _json({'status': 0, 'error_message': error})

        sites = _hosted_sites()
        user_to_site = {s['user']: s for s in sites if s.get('user')}
        blocked = set(data.get('blocked_users') or [])
        linux_users = data.get('linux_users') or {}

        by_site = []
        seen_users = set()
        for row in data.get('by_linux_user') or []:
            user = row.get('user')
            site = user_to_site.get(user) or {}
            info = linux_users.get(user) or {}
            by_site.append({
                'user': user,
                'uid': row.get('uid') or info.get('uid'),
                'domain': site.get('domain') or info.get('domain_guess') or '',
                'adminEmail': site.get('adminEmail') or '',
                'pickup': row.get('pickup', 0),
                'blocked': user in blocked,
            })
            seen_users.add(user)

        for site in sites:
            user = site.get('user')
            if user and user not in seen_users:
                by_site.append({
                    'user': user,
                    'uid': (linux_users.get(user) or {}).get('uid'),
                    'domain': site['domain'],
                    'adminEmail': site.get('adminEmail') or '',
                    'pickup': 0,
                    'blocked': user in blocked,
                })

        hosted_domains = {s['domain'].lower() for s in sites}
        from_rows = []
        for row in data.get('by_from_domain') or []:
            domain = (row.get('domain') or '').lower()
            from_rows.append({
                **row,
                'hosted': domain in hosted_domains,
            })

        return _json({
            'status': 1,
            'summary': data.get('summary') or {},
            'period_hours': data.get('period_hours'),
            'files': data.get('files') or [],
            'by_site': by_site,
            'by_sasl': data.get('by_sasl') or [],
            'by_from_domain': from_rows,
            'by_to_domain': data.get('by_to_domain') or [],
            'daily': data.get('daily') or [],
            'recent_pickup': data.get('recent_pickup') or [],
            'recent_outbound': data.get('recent_outbound') or [],
            'forwardings': _forwardings(),
            'postfix': data.get('postfix') or {},
            'blocked_users': list(blocked),
        })
    except Exception as e:
        return _json({'status': 0, 'error_message': str(e)})


def queue(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        data, error = mailGuardManager.get_queue()
        if data is None:
            return _json({'status': 0, 'error_message': error})
        return _json({'status': 1, **data})
    except Exception as e:
        return _json({'status': 0, 'error_message': str(e)})


def blockUser(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != 'POST':
            return _json({'status': 0, 'error_message': 'Método no permitido'})
        data = json.loads(request.body)
        user = (data.get('user') or '').strip()
        if not user:
            return _json({'status': 0, 'error_message': 'Falta el usuario'})
        ok, message = mailGuardManager.block_user(user)
        return _json({'status': 1 if ok else 0, 'error_message': message})
    except Exception as e:
        return _json({'status': 0, 'error_message': str(e)})


def unblockUser(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != 'POST':
            return _json({'status': 0, 'error_message': 'Método no permitido'})
        data = json.loads(request.body)
        user = (data.get('user') or '').strip()
        if not user:
            return _json({'status': 0, 'error_message': 'Falta el usuario'})
        ok, message = mailGuardManager.unblock_user(user)
        return _json({'status': 1 if ok else 0, 'error_message': message})
    except Exception as e:
        return _json({'status': 0, 'error_message': str(e)})


def deleteQueue(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != 'POST':
            return _json({'status': 0, 'error_message': 'Método no permitido'})
        data = json.loads(request.body)
        ids = data.get('ids') or []
        ok, message = mailGuardManager.delete_queue(ids)
        return _json({'status': 1 if ok else 0, 'error_message': message})
    except Exception as e:
        return _json({'status': 0, 'error_message': str(e)})


def flushBounces(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != 'POST':
            return _json({'status': 0, 'error_message': 'Método no permitido'})
        ok, message = mailGuardManager.flush_bounces()
        return _json({'status': 1 if ok else 0, 'error_message': message})
    except Exception as e:
        return _json({'status': 0, 'error_message': str(e)})


def forceIpv4(request):
    try:
        _, err = _require_admin(request)
        if err:
            return err
        if request.method != 'POST':
            return _json({'status': 0, 'error_message': 'Método no permitido'})
        ok, message = mailGuardManager.force_ipv4()
        return _json({'status': 1 if ok else 0, 'error_message': message})
    except Exception as e:
        return _json({'status': 0, 'error_message': str(e)})
