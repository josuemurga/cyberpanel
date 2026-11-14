"""Serialización de websites para Softi API (sync ERP)."""

from typing import Dict, List, Optional

from .external_refs import all_refs, get_ref


def _package_name(site) -> Optional[str]:
    pkg = getattr(site, 'package', None)
    if pkg is None:
        return None
    if hasattr(pkg, 'packageName'):
        return pkg.packageName
    return str(pkg)


def serialize_website(site, external_ref=None):
    # type: (object, Optional[str]) -> Dict
    domain = (site.domain or '').strip().lower()
    ref = external_ref if external_ref is not None else get_ref(domain)
    return {
        'domain': domain,
        'adminEmail': getattr(site, 'adminEmail', None),
        'state': getattr(site, 'state', None),
        'phpSelection': getattr(site, 'phpSelection', None),
        'package': _package_name(site),
        'externalRef': ref,
    }


def list_websites(limit=500):
    # type: (int) -> List[Dict]
    from websiteFunctions.models import Websites

    refs = all_refs()
    rows = []
    for site in Websites.objects.all()[:limit]:
        domain = (site.domain or '').strip().lower()
        rows.append(serialize_website(site, refs.get(domain)))
    return rows
