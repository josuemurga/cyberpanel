"""
Persistencia ligera domain → externalRef (UUID Softihost ServicioRecurso.id; N websites → 1 servicio).

Archivo: /etc/cyberpanel/softi-external-refs.json
Evita migraciones Django en el fork; el ERP es la fuente de verdad de billing.

N websites del mismo plan comercial comparten el mismo externalRef
(= ServicioRecurso.id). Plan usage puede sumar por ese UUID.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict, Optional

REFS_PATH = os.environ.get(
    'SOFTI_EXTERNAL_REFS_PATH',
    '/etc/cyberpanel/softi-external-refs.json',
)

_lock = threading.Lock()


def _read() -> Dict[str, str]:
    if not os.path.isfile(REFS_PATH):
        return {}
    try:
        with open(REFS_PATH, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k).lower(): str(v) for k, v in data.items() if k and v}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write(data: Dict[str, str]) -> None:
    directory = os.path.dirname(REFS_PATH) or '.'
    os.makedirs(directory, exist_ok=True)
    tmp = f'{REFS_PATH}.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write('\n')
    os.replace(tmp, REFS_PATH)
    try:
        os.chmod(REFS_PATH, 0o640)
    except OSError:
        pass


def get_ref(domain: str) -> Optional[str]:
    key = (domain or '').strip().lower()
    if not key:
        return None
    with _lock:
        return _read().get(key)


def set_ref(domain: str, external_ref: str) -> str:
    key = (domain or '').strip().lower()
    ref = (external_ref or '').strip()
    if not key:
        raise ValueError('domain requerido')
    if not ref:
        raise ValueError('externalRef requerido')
    with _lock:
        data = _read()
        data[key] = ref
        _write(data)
    return ref


def clear_ref(domain: str) -> bool:
    key = (domain or '').strip().lower()
    if not key:
        return False
    with _lock:
        data = _read()
        if key not in data:
            return False
        del data[key]
        _write(data)
    return True


def all_refs() -> Dict[str, str]:
    with _lock:
        return dict(_read())
