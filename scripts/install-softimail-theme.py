#!/usr/bin/env python3
"""
SOFTI — Instala tema SnappyMail SoftiMail@custom (producto correo / Morales Tech).

Uso:
  python3 /usr/local/CyberCP/scripts/install-softimail-theme.py
  python3 /usr/local/CyberCP/scripts/install-softimail-theme.py --allow-themes
"""
from __future__ import annotations

import argparse
import re
import shutil
import struct
import zlib
from pathlib import Path

CYBER = Path('/usr/local/CyberCP')
SOURCE = CYBER / 'install' / 'snappymail-themes' / 'SoftiMail'
TARGET = CYBER / 'public' / 'snappymail' / 'themes' / 'SoftiMail'
LEGACY = CYBER / 'public' / 'snappymail' / 'themes' / 'MoralesTech'
APP_INI = Path(
    '/usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/configs/application.ini'
)
CACHE_DIR = Path('/usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/cache')


def write_preview_png(path: Path) -> None:
    """Miniatura neutra (gris claro + franja azul suave)."""
    width, height = 320, 180
    rows = []
    for y in range(height):
        row = b'\x00'
        for x in range(width):
            if y < 28:
                r, g, b = 26, 115, 232
            else:
                r, g, b = 246, 248, 252
            row += bytes((r, g, b))
        rows.append(row)
    raw = b''.join(rows)
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack('>I', len(data))
            + tag
            + data
            + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    path.write_bytes(png)


def patch_application_ini(allow_themes: bool) -> None:
    if not APP_INI.exists():
        raise SystemExit(f'No existe {APP_INI}')

    text = APP_INI.read_text()
    replacements = {
        r'^title\s*=.*$': 'title = "SoftiMail"',
        r'^loading_description\s*=.*$': 'loading_description = "SoftiMail"',
        r'^theme\s*=.*$': 'theme = "SoftiMail@custom"',
        r'^allow_themes\s*=.*$': f'allow_themes = {"On" if allow_themes else "Off"}',
    }
    for pattern, value in replacements.items():
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, value, text, count=1, flags=re.MULTILINE)
        else:
            text += f'\n{value.split(" = ")[0]} = {value.split(" = ", 1)[1]}\n'

    APP_INI.write_text(text)
    print('application.ini: SoftiMail@custom OK')


def clear_cache() -> None:
    if not CACHE_DIR.exists():
        return
    for item in CACHE_DIR.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
    print('cache SnappyMail: limpiada')


def install_theme() -> None:
    if not SOURCE.exists():
        raise SystemExit(f'Falta fuente del tema: {SOURCE}')

    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET)
    write_preview_png(TARGET / 'preview.png')

    if LEGACY.exists():
        shutil.rmtree(LEGACY)
        print('tema legacy MoralesTech: eliminado')

    print(f'tema instalado en {TARGET}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--allow-themes',
        action='store_true',
        help='Permitir cambiar tema en ajustes (default: Off)',
    )
    args = parser.parse_args()

    install_theme()
    patch_application_ini(allow_themes=args.allow_themes)
    clear_cache()
    print('SoftiMail@custom listo. Recarga SnappyMail (Ctrl+F5).')


if __name__ == '__main__':
    main()
