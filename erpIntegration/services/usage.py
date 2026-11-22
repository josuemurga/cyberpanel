"""Consumo por servicio Softihost (externalRef = ServicioRecurso.id)."""

from .external_refs import all_refs


def _int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def servicio_usage(external_ref: str, domains_csv: str = '') -> dict:
    from websiteFunctions.models import Websites
    from plogical.virtualHostUtilities import virtualHostUtilities

    ref = (external_ref or '').strip().lower()
    if not ref:
        return {'status': 0, 'error_message': 'externalRef requerido'}

    dominios = {d for d, r in all_refs().items() if (r or '').strip().lower() == ref}
    # El ERP también manda los dominios del servicio: sirve aunque falte el externalRef.
    dominios |= {d.strip().lower() for d in (domains_csv or '').split(',') if d.strip()}
    sites = list(Websites.objects.filter(domain__in=sorted(dominios))) if dominios else []
    if not sites:
        return {'status': 0, 'error_message': 'Servicio sin sitios en el panel', 'notFound': True}

    disco_mb = 0
    transferencia_mb = 0
    for site in sites:
        disk, _pct, bw, _bw_pct = virtualHostUtilities.FindStats(site)
        disco_mb += _int(disk)
        transferencia_mb += _int(bw)

    pkg = getattr(sites[0], 'package', None)

    correos = 0
    try:
        from mailServer.models import EUsers

        correos = EUsers.objects.filter(emailOwner__domainOwner__in=sites).count()
    except Exception:
        pass

    bases = 0
    try:
        from databases.models import Databases

        bases = Databases.objects.filter(website__in=sites).count()
    except Exception:
        pass

    return {
        'status': 1,
        'externalRef': ref,
        'dominios': [s.domain for s in sites],
        'suspendido': any(getattr(s, 'state', 1) != 1 for s in sites),
        'disco': {'usadoMB': disco_mb, 'limiteMB': _int(getattr(pkg, 'diskSpace', 0))},
        'transferencia': {
            'usadoMB': transferencia_mb,
            'limiteMB': _int(getattr(pkg, 'bandwidth', 0)),
        },
        'correos': {'usados': correos, 'limite': _int(getattr(pkg, 'emailAccounts', 0))},
        'basesDatos': {'usadas': bases, 'limite': _int(getattr(pkg, 'dataBases', 0))},
        # CyberPanel recalcula disco/ancho de banda con su cron, no en vivo.
        'nota': 'Disco y transferencia se actualizan periódicamente.',
    }
