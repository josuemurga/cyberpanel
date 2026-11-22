"""Borra un website y lo que CyberPanel suele dejar: correo, DKIM, DNS, SSL y archivos.

Solo toca el dominio pedido. No borra la zona padre ni claves de otro dominio.
"""

import json
import os

from websiteFunctions.models import Websites
from websiteFunctions.website import WebsiteManager

from .external_refs import clear_ref

_PROTECTED_USERS = {
    'root',
    'admin',
    'cyberpanel',
    'lscpd',
    'nobody',
    'mysql',
    'vmail',
    'postfix',
    'dovecot',
    'www-data',
    'ubuntu',
    'debian',
}


def delete_website(domain: str) -> dict:
    domain = (domain or '').strip().lower().rstrip('.')
    if not _domain_ok(domain):
        return {'status': 0, 'error_message': 'Dominio inválido para borrar'}

    site = Websites.objects.filter(domain=domain).first()
    external_app = getattr(site, 'externalApp', None) if site else _owner_of_home(domain)
    db_names = _database_names(site)

    if site is None:
        clear_ref(domain)
        swept = _sweep(domain, external_app, db_names)
        return {
            'status': 1,
            'websiteDeleteStatus': 1,
            'domainName': domain,
            'alreadyDeleted': True,
            'swept': swept,
            'message': 'El sitio ya no estaba en CyberPanel',
        }

    admin_user = os.environ.get('SOFTI_CP_ADMIN_USER', 'admin')
    try:
        from loginSystem.models import Administrator

        admin = Administrator.objects.filter(userName=admin_user).first()
    except Exception as exc:
        return {'status': 0, 'error_message': str(exc)}

    if admin is None:
        return {
            'status': 0,
            'error_message': f'No existe el administrador {admin_user}',
        }

    response = WebsiteManager().submitWebsiteDeletion(
        admin.pk,
        {'websiteName': domain},
    )
    content = response.content.decode() if hasattr(response, 'content') else str(response)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {'status': 0, 'error_message': content or 'Error al borrar el sitio'}

    if data.get('websiteDeleteStatus') == 1 or data.get('status') == 1:
        clear_ref(domain)
        swept = _sweep(domain, external_app, db_names)
        data['status'] = 1
        data['websiteDeleteStatus'] = 1
        data['domainName'] = domain
        data['alreadyDeleted'] = False
        data['swept'] = swept
        data['message'] = 'Sitio eliminado de CyberPanel'
        return data

    data['status'] = 0
    if not data.get('error_message') or data.get('error_message') == 'None':
        data['error_message'] = 'websiteDeleteStatus distinto de 1'
    return data


def _domain_ok(domain: str) -> bool:
    if not domain or len(domain) < 4 or '.' not in domain:
        return False
    if any(token in domain for token in ('/', '\\', ' ', '..', '*')):
        return False
    return True


def _database_names(site):
    if site is None:
        return []
    try:
        from databases.models import Databases

        return list(
            Databases.objects.filter(website=site).values_list('dbName', 'dbUser')
        )
    except Exception:
        return []


def _sweep(domain, external_app, db_names):
    swept = []
    swept.extend(_sweep_mail(domain))
    swept.extend(_sweep_dns(domain))
    swept.extend(_sweep_mysql(db_names))
    swept.extend(_sweep_dkim_files(domain))
    swept.extend(_sweep_paths(domain))
    swept.extend(_sweep_user(external_app))
    swept.extend(_sweep_website_row(domain))
    return swept


def _sweep_website_row(domain):
    vhost = f'/usr/local/lsws/conf/vhosts/{domain}'
    if os.path.isdir(vhost):
        return []
    try:
        from databases.models import Databases
        from websiteFunctions.models import ChildDomains, Websites

        site = Websites.objects.filter(domain=domain).first()
        if site is None:
            return []
        ChildDomains.objects.filter(master=site)._raw_delete(ChildDomains.objects.db)
        Databases.objects.filter(website=site)._raw_delete(Databases.objects.db)
        Websites.objects.filter(pk=site.pk)._raw_delete(Websites.objects.db)
        return ['website-row']
    except Exception as exc:
        return [f'website-row-error:{exc}']


def _sweep_mail(domain):
    removed = []
    try:
        from mailServer.models import Domains, EUsers, Forwardings

        suffix = '@' + domain
        forwards = [
            row
            for row in Forwardings.objects.all().only('id', 'source')
            if (row.source or '').strip().lower().endswith(suffix)
            and (row.source or '').strip().lower().rsplit('@', 1)[-1] == domain
        ]
        if forwards:
            Forwardings.objects.filter(id__in=[row.id for row in forwards]).delete()
            removed.append(f'mail-forwardings:{len(forwards)}')

        for mail_domain in Domains.objects.filter(domain=domain):
            users = EUsers.objects.filter(emailOwner=mail_domain)
            count = users.count()
            users._raw_delete(users.db)
            try:
                from emailPremium.models import DomainLimits

                limits = DomainLimits.objects.filter(domain=mail_domain)
                limits._raw_delete(limits.db)
            except Exception:
                pass
            Domains.objects.filter(pk=mail_domain.pk)._raw_delete(Domains.objects.db)
            removed.append(f'mail-domain:{domain}:{count}')
    except Exception as exc:
        removed.append(f'mail-error:{exc}')

    try:
        from emailDelivery.models import CyberMailDomain

        deleted, _ = CyberMailDomain.objects.filter(domain=domain).delete()
        if deleted:
            removed.append(f'cybermail-domain:{deleted}')
    except Exception:
        pass
    return removed


def _sweep_dns(domain):
    removed = []
    try:
        from django.db.models import Q
        from dns.models import Domains, Records

        records = Records.objects.filter(Q(name=domain) | Q(name__endswith='.' + domain))
        count = records.count()
        if count:
            records.delete()
            removed.append(f'dns-records:{count}')
        zones = Domains.objects.filter(name=domain)
        zone_count = zones.count()
        if zone_count:
            zones.delete()
            removed.append(f'dns-zone:{domain}')
    except Exception as exc:
        removed.append(f'dns-error:{exc}')
    return removed


def _sweep_mysql(db_names):
    removed = []
    if not db_names:
        return removed
    try:
        from plogical.mysqlUtilities import mysqlUtilities
    except Exception as exc:
        return [f'mysql-error:{exc}']

    for db_name, db_user in db_names:
        if not db_name or not db_user:
            continue
        try:
            mysqlUtilities.deleteDatabase(db_name, db_user)
            removed.append(f'mysql:{db_name}')
        except Exception as exc:
            removed.append(f'mysql-error:{db_name}:{exc}')
    return removed


def _owner_of_home(domain):
    home = f'/home/{domain}'
    if not os.path.isdir(home):
        return None
    try:
        import pwd

        return pwd.getpwuid(os.stat(home).st_uid).pw_name
    except Exception:
        return None


def _remove_path(path):
    import shlex
    from plogical.processUtilities import ProcessUtilities

    ProcessUtilities.executioner('rm -rf ' + shlex.quote(path))


def _dkim_names(domain):
    names = [domain]
    mail_host = f'mail.{domain}'
    try:
        from websiteFunctions.models import Websites

        if not Websites.objects.filter(domain=mail_host).exists():
            names.append(mail_host)
    except Exception:
        names.append(mail_host)
    return names


def _sweep_dkim_files(domain):
    removed = []
    names = _dkim_names(domain)

    def key_line(line):
        return any(line.startswith(f'default._domainkey.{name} ') for name in names)

    def signing_line(line):
        return any(line.startswith(f'*@{name} ') for name in names)

    def trusted_line(line):
        return line.strip() in names

    if _drop_lines('/etc/opendkim/KeyTable', key_line):
        removed.append('opendkim-keytable')
    if _drop_lines('/etc/opendkim/SigningTable', signing_line):
        removed.append('opendkim-signing')
    if _drop_lines('/etc/opendkim/TrustedHosts', trusted_line):
        removed.append('opendkim-trusted')

    key_dir = f'/etc/opendkim/keys/{domain}'
    if os.path.basename(key_dir) == domain:
        _remove_path(key_dir)
        removed.append('opendkim-keys')
    return removed


def _sweep_paths(domain):
    removed = []
    directories = [
        f'/home/{domain}',
        f'/home/vmail/{domain}',
        f'/home/docker/{domain}',
        f'/home/cyberpanel/git/{domain}',
        f'/root/.acme.sh/{domain}',
        f'/etc/letsencrypt/live/{domain}',
        f'/etc/letsencrypt/archive/{domain}',
        f'/usr/local/lsws/conf/vhosts/{domain}',
    ]
    for path in directories:
        # lscpd no puede ver /home/vmail; el borrado corre como root.
        if os.path.basename(path) != domain or '..' in path:
            continue
        _remove_path(path)
        removed.append(path)

    renewal = f'/etc/letsencrypt/renewal/{domain}.conf'
    if os.path.isfile(renewal) and os.path.basename(renewal) == f'{domain}.conf':
        _remove_path(renewal)
        removed.append(renewal)
    return removed


def _sweep_user(external_app):
    if not external_app:
        return []
    user = str(external_app).strip()
    if user in _PROTECTED_USERS or not user.replace('-', '').replace('_', '').isalnum():
        return []
    try:
        import pwd

        pwd.getpwnam(user)
    except KeyError:
        return []
    except Exception as exc:
        return [f'user-error:{exc}']

    from plogical.processUtilities import ProcessUtilities

    ProcessUtilities.executioner(f'deluser {user}')
    ProcessUtilities.executioner(f'groupdel {user}')
    return [f'user:{user}']


def _drop_lines(path, predicate):
    if not os.path.isfile(path):
        return False
    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
        lines = handle.readlines()
    kept = [line for line in lines if not predicate(line.rstrip('\n'))]
    if kept == lines:
        return False
    temporary = f'/tmp/softi-{os.path.basename(path)}'
    with open(temporary, 'w', encoding='utf-8') as handle:
        handle.writelines(kept)
    from plogical.processUtilities import ProcessUtilities

    ProcessUtilities.executioner(f'cp {temporary} {path}')
    try:
        os.remove(temporary)
    except OSError:
        pass
    return True
