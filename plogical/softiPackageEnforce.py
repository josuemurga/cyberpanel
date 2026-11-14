#!/usr/local/CyberCP/bin/python
"""
Softi: apply CyberPanel Package resource limits to Linux website users.

OLS lscgctl only covers LiteSpeed workers. Clients with SSH + systemd --user
(Node/Playwright) bypass OLS. Softi therefore enforces UID-wide limits via
systemd user-{uid}.slice drop-ins, driven by Package fields in the panel.

Convention (shared hosting on small VPS):
  cpuCores = share units; each unit = 25% of one vCPU (cap 100% per user by default).
  memoryLimitMB / procHardLimit / enforceDiskLimits come from Package as usual.
"""

from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path

from plogical.CyberCPLogFileWriter import CyberCPLogFileWriter as logging

# Softi shared: 1 cpuCores unit → 25% of one vCPU (not full cores).
SOFTI_CPU_SHARE_PERCENT = 25
SOFTI_CPU_PERCENT_CAP = 100
SOFTI_DROPIN_NAME = "90-softi-package.conf"


def softi_cpu_quota_percent(package) -> int:
    cores = int(getattr(package, "cpuCores", 1) or 1)
    return max(10, min(SOFTI_CPU_PERCENT_CAP, cores * SOFTI_CPU_SHARE_PERCENT))


def softi_memory_max(package) -> str:
    mb = int(getattr(package, "memoryLimitMB", 512) or 512)
    mb = max(256, mb)
    return f"{mb}M"


def softi_tasks_max(package) -> int:
    return max(20, int(getattr(package, "procHardLimit", 100) or 100))


def _write_user_slice_dropin(uid: int, package) -> bool:
    drop_dir = Path(f"/etc/systemd/system/user-{uid}.slice.d")
    drop_dir.mkdir(parents=True, exist_ok=True)
    path = drop_dir / SOFTI_DROPIN_NAME
    mem = softi_memory_max(package)
    cpu = softi_cpu_quota_percent(package)
    tasks = softi_tasks_max(package)
    body = (
        "# Managed by Softi — do not edit by hand.\n"
        "# Source: CyberPanel Package resource limits.\n"
        "[Slice]\n"
        f"MemoryMax={mem}\n"
        f"MemoryHigh={mem}\n"
        f"CPUQuota={cpu}%\n"
        f"TasksMax={tasks}\n"
    )
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o644)
    logging.writeToFile(
        f"SOFTI package enforce: wrote {path} MemoryMax={mem} CPUQuota={cpu}% TasksMax={tasks}"
    )
    return True


def _remove_user_slice_dropin(uid: int) -> None:
    path = Path(f"/etc/systemd/system/user-{uid}.slice.d/{SOFTI_DROPIN_NAME}")
    if path.exists():
        path.unlink()
        logging.writeToFile(f"SOFTI package enforce: removed {path}")


def _daemon_reload_and_refresh_user(uid: int) -> None:
    subprocess.run(["systemctl", "daemon-reload"], check=False, timeout=60)
    # Refresh slice if user session exists; ignore failures when user idle.
    subprocess.run(
        ["systemctl", "restart", f"user-{uid}.slice"],
        check=False,
        timeout=30,
        capture_output=True,
    )


def apply_linux_user_limits(username: str, package) -> bool:
    """Apply Softi systemd limits for a website Linux user from Package."""
    try:
        if not getattr(package, "enforceDiskLimits", 0):
            try:
                uid = pwd.getpwnam(username).pw_uid
                _remove_user_slice_dropin(uid)
                _daemon_reload_and_refresh_user(uid)
            except KeyError:
                pass
            logging.writeToFile(
                f"SOFTI package enforce: enforceDiskLimits=0 for {username}, drop-in cleared"
            )
            return True

        try:
            uid = pwd.getpwnam(username).pw_uid
        except KeyError:
            logging.writeToFile(
                f"SOFTI package enforce: user {username} not found, skip systemd limits"
            )
            return False

        _write_user_slice_dropin(uid, package)
        _daemon_reload_and_refresh_user(uid)
        return True
    except Exception as exc:
        logging.writeToFile(f"SOFTI package enforce error for {username}: {exc}")
        return False


def apply_package_to_all_websites(package) -> int:
    """Re-apply limits to every website using this package. Returns count."""
    from websiteFunctions.models import Websites

    count = 0
    for site in Websites.objects.filter(package=package):
        user = site.externalApp
        if user:
            if apply_linux_user_limits(user, package):
                count += 1
    logging.writeToFile(
        f"SOFTI package enforce: reapplied package={package.packageName} to {count} site user(s)"
    )
    return count


def disable_self_linger(username: str) -> None:
    """Best-effort: turn off linger so user services die without SSH session."""
    try:
        subprocess.run(
            ["loginctl", "disable-linger", username],
            check=False,
            timeout=15,
            capture_output=True,
        )
        linger = Path(f"/var/lib/systemd/linger/{username}")
        if linger.exists():
            linger.unlink()
    except Exception as exc:
        logging.writeToFile(f"SOFTI disable-linger {username}: {exc}")
