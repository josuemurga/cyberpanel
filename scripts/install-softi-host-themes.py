#!/usr/bin/env python3
"""
SOFTI — Instala temas SoftiMail por Host + plugin softi-host-theme.

Temas:
  SoftiMail@custom   — default (producto Softi)
  MoralesTech@custom — webmail.moralestechs.com
  Astromike@custom   — webmail.astromike.design (wordmark + acentos magenta)

Uso:
  python3 /usr/local/CyberCP/scripts/install-softi-host-themes.py
"""
from __future__ import annotations

import re
import shutil
import struct
import zlib
from pathlib import Path

CYBER = Path("/usr/local/CyberCP")
THEMES_SRC = CYBER / "install" / "snappymail-themes"
THEMES_DST = CYBER / "public" / "snappymail" / "themes"
PLUGIN_SRC = CYBER / "install" / "snappymail-plugins" / "softi-host-theme"
PLUGIN_DST = Path(
    "/usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/plugins/softi-host-theme"
)
APP_INI = Path(
    "/usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/configs/application.ini"
)
CACHE_DIR = Path("/usr/local/lscp/cyberpanel/rainloop/data/_data_/_default_/cache")

THEMES = ("SoftiMail", "MoralesTech", "Astromike")


def write_preview_png(path: Path, top_rgb: tuple[int, int, int]) -> None:
    width, height = 320, 180
    rows = []
    for y in range(height):
        row = b"\x00"
        for x in range(width):
            if y < 28:
                r, g, b = top_rgb
            else:
                r, g, b = 246, 248, 252
            row += bytes((r, g, b))
        rows.append(row)
    raw = b"".join(rows)
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def install_theme(name: str, preview_rgb: tuple[int, int, int]) -> None:
    src = THEMES_SRC / name
    dst = THEMES_DST / name
    if not src.is_dir():
        raise SystemExit(f"Falta tema fuente: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    write_preview_png(dst / "images" / "preview.png", preview_rgb)
    print(f"tema OK: {name}@custom → {dst}")


def install_plugin() -> None:
    if not PLUGIN_SRC.is_dir():
        raise SystemExit(f"Falta plugin: {PLUGIN_SRC}")
    if PLUGIN_DST.exists():
        shutil.rmtree(PLUGIN_DST)
    shutil.copytree(PLUGIN_SRC, PLUGIN_DST)
    for p in PLUGIN_DST.rglob("*"):
        if p.is_file():
            p.chmod(0o644)
        else:
            p.chmod(0o755)
    print(f"plugin OK: {PLUGIN_DST}")


def patch_application_ini() -> None:
    if not APP_INI.exists():
        raise SystemExit(f"No existe {APP_INI}")
    text = APP_INI.read_text()
    replacements = {
        r"^title\s*=.*$": 'title = "SoftiMail"',
        r"^loading_description\s*=.*$": 'loading_description = "SoftiMail"',
        r"^theme\s*=.*$": 'theme = "SoftiMail@custom"',
        r"^allow_themes\s*=.*$": "allow_themes = Off",
    }
    for pat, rep in replacements.items():
        if re.search(pat, text, flags=re.M):
            text = re.sub(pat, rep, text, count=1, flags=re.M)
        else:
            print(f"aviso: no match {pat}")

    # enabled_list
    m = re.search(r"^enabled_list\s*=\s*\"([^\"]*)\"", text, flags=re.M)
    if not m:
        raise SystemExit("No hay enabled_list en application.ini")
    parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
    # drop temp probe if present
    parts = [p for p in parts if p != "softi-host-probe"]
    if "softi-host-theme" not in parts:
        parts.append("softi-host-theme")
    # keep first-login + mailbox-detect
    for required in ("mailbox-detect", "first-login-password", "softi-host-theme"):
        if required not in parts:
            parts.append(required)
    text = re.sub(
        r"^enabled_list\s*=\s*\".*\"",
        f'enabled_list = "{",".join(parts)}"',
        text,
        count=1,
        flags=re.M,
    )
    APP_INI.write_text(text)
    print(f"application.ini: SoftiMail default + plugins {parts}")


def clear_cache() -> None:
    if CACHE_DIR.is_dir():
        for child in CACHE_DIR.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        print("cache SnappyMail limpiada")


def main() -> None:
    install_theme("SoftiMail", (26, 115, 232))
    install_theme("MoralesTech", (23, 70, 234))
    install_theme("Astromike", (217, 70, 239))
    install_plugin()
    patch_application_ini()
    clear_cache()
    print("Listo. Probar:")
    print("  webmail.moralestechs.com → Morales Tech")
    print("  webmail.astromike.design → Astromike")
    print("  cyberpanel…/snappymail → SoftiMail")


if __name__ == "__main__":
    main()
