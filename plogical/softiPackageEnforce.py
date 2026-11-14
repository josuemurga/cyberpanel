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


def _match_home(path: str, homes_sorted: list) -> str | None:
    if not path:
        return None
    for h in homes_sorted:
        if path == h or path.startswith(h + "/"):
            return h
    return None


def _parse_docker_mem_to_kb(text: str) -> int:
    """Parse docker stats MemUsage left side: '336.5MiB' / '1.2GiB' / '512KiB'."""
    try:
        left = (text or "").split("/", 1)[0].strip()
        num = ""
        unit = ""
        for ch in left:
            if ch.isdigit() or ch == ".":
                num += ch
            elif ch.isalpha():
                unit += ch
        if not num:
            return 0
        val = float(num)
        u = unit.lower()
        if u in ("gib", "gb"):
            return int(val * 1024 * 1024)
        if u in ("mib", "mb"):
            return int(val * 1024)
        if u in ("kib", "kb"):
            return int(val)
        if u in ("b",):
            return int(val / 1024)
        return int(val * 1024)  # assume MiB
    except Exception:
        return 0


def snapshot_process_usage_by_home(homes: dict) -> dict:
    """
    Live RAM/CPU per site home (approx).

    cgroup user slices are usually inactive; Softi Node often runs as root/PM2.
    Sources (merged, no double-count by pid when possible):
      1) ps: site Linux user, or cmdline contains /home/domain
      2) /proc cwd under /home/domain (next-server renames argv)
      3) pm2 jlist monit by pm_cwd
      4) docker stats by compose working_dir under /home/domain
    """
    result = {
        h: {"memoryUsedKB": 0, "cpuPct": 0.0, "procCount": 0, "note": "idle"}
        for h in homes.values()
        if h
    }
    user_to_home = {u: h for u, h in homes.items() if u and h}
    homes_sorted = sorted(result.keys(), key=len, reverse=True)
    counted_pids: set[int] = set()
    pid_pcpu: dict[int, float] = {}

    # --- ps ---
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,user=,rss=,pcpu=,args="],
            capture_output=True,
            text=True,
            timeout=25,
        )
        ps_lines = out.stdout.splitlines() if out.returncode == 0 else []
    except Exception:
        ps_lines = []

    for line in ps_lines:
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid_s, user, rss_s, pcpu_s, args = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            pid = int(pid_s)
            rss_kb = int(rss_s)
            pcpu = float(pcpu_s)
        except ValueError:
            continue
        pid_pcpu[pid] = pcpu
        home = user_to_home.get(user) or _match_home(args, homes_sorted)
        if not home or home not in result:
            continue
        counted_pids.add(pid)
        acc = result[home]
        acc["memoryUsedKB"] += rss_kb
        acc["cpuPct"] += pcpu
        acc["procCount"] += 1
        acc["note"] = "ps+root" if user == "root" else "ps"

    # --- cwd (next-server) ---
    try:
        for pid_name in os.listdir("/proc"):
            if not pid_name.isdigit():
                continue
            pid = int(pid_name)
            if pid in counted_pids:
                continue
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except Exception:
                continue
            home = _match_home(cwd, homes_sorted)
            if not home:
                continue
            rss_kb = 0
            try:
                with open(f"/proc/{pid}/status", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            rss_kb = int(line.split()[1])
                            break
            except Exception:
                continue
            if rss_kb <= 0:
                continue
            acc = result[home]
            acc["memoryUsedKB"] += rss_kb
            acc["cpuPct"] += float(pid_pcpu.get(pid) or 0.0)
            acc["procCount"] += 1
            acc["note"] = "ps+cwd"
            counted_pids.add(pid)
    except Exception:
        pass

    # --- PM2 monit (authoritative for Softi Node) ---
    try:
        env = os.environ.copy()
        nvm_bin = "/root/.nvm/versions/node/v20.19.6/bin"
        env["PATH"] = f"{nvm_bin}:{env.get('PATH', '')}"
        env["PM2_HOME"] = "/root/.pm2"
        pm2_bin = f"{nvm_bin}/pm2"
        if not os.path.exists(pm2_bin):
            pm2_bin = "pm2"
        out = subprocess.run(
            [pm2_bin, "jlist"],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
        if out.returncode == 0 and out.stdout.strip().startswith("["):
            import json as _json

            apps = _json.loads(out.stdout)
            for app in apps:
                pm_env = app.get("pm2_env") or {}
                cwd = pm_env.get("pm_cwd") or ""
                home = _match_home(cwd, homes_sorted)
                if not home:
                    continue
                monit = app.get("monit") or {}
                mem_b = int(monit.get("memory") or 0)
                cpu = float(monit.get("cpu") or 0)
                if mem_b <= 0 and cpu <= 0:
                    continue
                mem_kb = int(mem_b / 1024)
                acc = result[home]
                # Prefer PM2 figures when larger / replace weak ps for that app
                if mem_kb > acc["memoryUsedKB"]:
                    acc["memoryUsedKB"] = mem_kb
                    acc["cpuPct"] = cpu
                    acc["procCount"] = max(1, acc["procCount"])
                    acc["note"] = "pm2"
                else:
                    # still add cpu if we only had cwd rss without cpu
                    if acc["cpuPct"] <= 0 and cpu > 0:
                        acc["cpuPct"] = cpu
                        acc["note"] = (acc.get("note") or "ps") + "+pm2cpu"
    except Exception as exc:
        logging.writeToFile(f"SOFTI plan usage pm2 snapshot: {exc}")

    # --- Docker (compose working_dir under /home/domain) ---
    try:
        ids = subprocess.run(
            ["docker", "ps", "-q"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        cids = [x for x in (ids.stdout or "").split() if x]
        if cids:
            stats_out = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.ID}}\t{{.MemUsage}}\t{{.CPUPerc}}",
                    *cids,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            stats_map = {}
            for line in (stats_out.stdout or "").splitlines():
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                cid, mem_usage, cpu_s = parts[0].strip(), parts[1].strip(), parts[2].strip()
                try:
                    cpu = float(cpu_s.rstrip("%"))
                except ValueError:
                    cpu = 0.0
                stats_map[cid[:12]] = (_parse_docker_mem_to_kb(mem_usage), cpu)

            for cid in cids:
                insp = subprocess.run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        '{{index .Config.Labels "com.docker.compose.project.working_dir"}}',
                        cid,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                wd = (insp.stdout or "").strip()
                home = _match_home(wd, homes_sorted)
                if not home:
                    continue
                mem_kb, cpu = stats_map.get(cid[:12], (0, 0.0))
                if mem_kb <= 0 and cpu <= 0:
                    continue
                acc = result[home]
                acc["memoryUsedKB"] += mem_kb
                acc["cpuPct"] += cpu
                acc["procCount"] += 1
                acc["note"] = "docker"
    except Exception as exc:
        logging.writeToFile(f"SOFTI plan usage docker snapshot: {exc}")

    return {
        h: {
            "memoryUsedMB": int(round(acc["memoryUsedKB"] / 1024.0)),
            "cpuPct": round(float(acc["cpuPct"]), 1),
            "procCount": int(acc["procCount"]),
            "note": acc.get("note") or "idle",
        }
        for h, acc in result.items()
    }


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
