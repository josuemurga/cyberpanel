# Softi Package limits (shared hosting)

Configurable in CyberPanel **Packages** (`memoryLimitMB`, `cpuCores`, `procHardLimit`, `diskSpace`, `enforceDiskLimits=1`).

Enforcement (`plogical/softiPackageEnforce.py`):

- systemd `user-{uid}.slice` → `MemoryMax` / `CPUQuota` / `TasksMax` (covers SSH Node/Playwright)
- OLS vhost mem/proc on site create; `lscgctl` best-effort
- Softi: no CyberPanel addons paywall
- Polkit: deny `set-self-linger`

CPU: each `cpuCores` unit = **25%** of one vCPU (cap 100%).

Packages: `admin_SoftiEsencial|Profesional|Comercial|Corporativo`.
