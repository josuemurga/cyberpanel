#!/usr/bin/env bash
# softi-upgrade.sh — SOFTI-MEJORA
#
# Actualiza CyberPanel SIN perder las mejoras Softi.
#
# El upgrade oficial (preUpgrade.sh → cyberpanel_upgrade.sh → upgrade.py) borra
# /usr/local/CyberCP y clona github.com/usmannasir/cyberpanel. Este script corre
# ese mismo upgrade, pero apuntando al fork y a la rama con las mejoras.
#
# Flujo:
#   1. Fuera de producción: merge del tag oficial en mis-mejoras, probar y push.
#        git fetch upstream --tags && git merge v2.4.4   (resolver conflictos)
#        git push origin mis-mejoras
#   2. En producción:
#        bash /usr/local/CyberCP/softi-upgrade.sh --dry-run   # solo verifica
#        bash /usr/local/CyberCP/softi-upgrade.sh             # actualiza
#
# Variables: SOFTI_GIT_USER (josuemurga), SOFTI_BRANCH (mis-mejoras),
#            SOFTI_REQUIRE_TAG (opcional: tag oficial que mis-mejoras debe contener).

set -euo pipefail

GIT_USER="${SOFTI_GIT_USER:-josuemurga}"
BRANCH="${SOFTI_BRANCH:-mis-mejoras}"
REQUIRE_TAG="${SOFTI_REQUIRE_TAG:-}"
CYBERCP=/usr/local/CyberCP
BACKUP_DIR=/root/softi-upgrade-backups
FORK_RAW="https://raw.githubusercontent.com/${GIT_USER}/cyberpanel/${BRANCH}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

paso() { echo -e "\n\e[1;36m==> $*\e[0m"; }
falla() { echo -e "\n\e[1;31mABORTADO: $*\e[0m" >&2; exit 1; }
PROBLEMAS=()
# Problema que impide actualizar; en --dry-run se acumulan para mostrarlos todos.
problema() { PROBLEMAS+=("$*"); echo -e "\e[1;33m✗ $*\e[0m" >&2; }

[[ $EUID -eq 0 ]] || falla "ejecutar como root"
cd "$CYBERCP"

# ---------------------------------------------------------------- verificaciones
paso "Verificando que no se pierda nada al re-clonar"

actual=$(git rev-parse --abbrev-ref HEAD)
[[ "$actual" == "$BRANCH" ]] || falla "rama actual '$actual', se esperaba '$BRANCH'"

# Lectura por HTTPS (fork público): el servidor no necesita llave de GitHub.
git fetch -q "https://github.com/${GIT_USER}/cyberpanel.git" "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" \
  || falla "no se pudo leer $GIT_USER/cyberpanel:$BRANCH (¿red?)"

# Cambios en archivos versionados (public/imunifyav se regenera solo: se ignora).
sucios=$(git status --porcelain --untracked-files=no -- . ':(exclude)public/imunifyav' || true)
[[ -z "$sucios" ]] || problema "hay cambios sin commit (se perderían):
$sucios
→ commit + push a origin/$BRANCH antes de actualizar."

sin_push=$(git rev-list --count "origin/$BRANCH..HEAD")
[[ "$sin_push" == "0" ]] || problema "$sin_push commit(s) sin push a origin/$BRANCH: se perderían al re-clonar."

if [[ -n "$REQUIRE_TAG" ]]; then
  git fetch -q https://github.com/usmannasir/cyberpanel.git "refs/tags/$REQUIRE_TAG:refs/tags/$REQUIRE_TAG" \
    || falla "no existe el tag oficial $REQUIRE_TAG"
  git merge-base --is-ancestor "$REQUIRE_TAG" "origin/$BRANCH" \
    || problema "origin/$BRANCH no contiene $REQUIRE_TAG: primero merge del tag y push."
fi

# Mejoras que deben seguir existiendo después del upgrade.
for f in erpIntegration/views.py erpIntegration/urls.py; do
  git cat-file -e "origin/$BRANCH:$f" 2>/dev/null || problema "origin/$BRANCH no tiene $f"
done
git show "origin/$BRANCH:CyberCP/settings.py" | grep -q "'erpIntegration'" \
  || problema "settings.py de origin/$BRANCH no registra erpIntegration"

curl -fsSL -o /tmp/softi-cyberpanel_upgrade.sh "$FORK_RAW/cyberpanel_upgrade.sh" \
  || falla "no se pudo descargar cyberpanel_upgrade.sh del fork"

# ------------------------------------------------- upgrade oficial redirigido al fork
paso "Preparando cyberpanel_upgrade.sh del fork ($GIT_USER/$BRANCH)"

UPG=/tmp/softi-cyberpanel_upgrade.sh
# Rama fija (sin consultar cyberpanel.net) y descargas desde el fork.
sed -i \
  -e "s|^Branch_Name=.*|Branch_Name=\"${BRANCH}\"|" \
  -e "s|Git_User=\"usmannasir\"|Git_User=\"${GIT_USER}\"|g" \
  -e "s|https://github.com/usmannasir/cyberpanel|https://github.com/${GIT_USER}/cyberpanel|g" \
  -e "s|raw.githubusercontent.com/usmannasir/cyberpanel/stable|raw.githubusercontent.com/${GIT_USER}/cyberpanel/${BRANCH}|g" \
  "$UPG"
# upgrade.py se descarga dentro del script: redirigir también su clone y descargas.
sed -i "s|^wget \"\${Git_Content_URL}/\${Branch_Name}/plogical/upgrade.py\"|&\nsed -i -e 's#github.com/usmannasir/cyberpanel#github.com/${GIT_USER}/cyberpanel#g' -e 's#raw.githubusercontent.com/usmannasir/cyberpanel/stable#raw.githubusercontent.com/${GIT_USER}/cyberpanel/${BRANCH}#g' upgrade.py|" "$UPG"

grep -q "^Branch_Name=\"${BRANCH}\"" "$UPG" || falla "no se pudo fijar la rama en el script"
grep -q "github.com/${GIT_USER}/cyberpanel#g" "$UPG" || falla "no se pudo redirigir upgrade.py"
quedan=$(grep -c "usmannasir/cyberpanel" "$UPG" || true)
echo "Referencias al repo oficial que quedan en el script: $quedan (deben ser solo del bloque CN/gitee)"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "Script preparado en $UPG"
  if [[ ${#PROBLEMAS[@]} -gt 0 ]]; then
    paso "Dry-run: ${#PROBLEMAS[@]} problema(s) a resolver antes de actualizar. Nada fue modificado."
    exit 1
  fi
  paso "Dry-run OK: todo listo. Nada fue modificado."
  exit 0
fi
[[ ${#PROBLEMAS[@]} -eq 0 ]] || falla "${#PROBLEMAS[@]} problema(s); corre --dry-run para verlos."

# ------------------------------------------------------------------- respaldo
paso "Respaldando panel y base de datos"
mkdir -p "$BACKUP_DIR"
ts=$(date +%Y%m%d-%H%M%S)
tar czf "$BACKUP_DIR/CyberCP-$ts.tgz" -C /usr/local \
  --exclude=CyberCP/bin --exclude=CyberCP/lib --exclude=CyberCP/lib64 CyberCP
if [[ -f /etc/cyberpanel/mysqlPassword ]]; then
  mysqldump -uroot -p"$(cat /etc/cyberpanel/mysqlPassword)" cyberpanel > "$BACKUP_DIR/cyberpanel-db-$ts.sql"
fi
ls -lh "$BACKUP_DIR" | tail -3

# ---------------------------------------------------------------------- upgrade
paso "Ejecutando upgrade desde $GIT_USER/$BRANCH"
chmod 700 "$UPG"
"$UPG" </dev/null

# ------------------------------------------------------------- verificación
paso "Verificando que las mejoras siguen ahí"
cd "$CYBERCP"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "$BRANCH" ]] || echo "ATENCIÓN: rama tras upgrade: $(git rev-parse --abbrev-ref HEAD)"
# upgrade.py clona por HTTPS: volver a SSH para que `cybergit push` siga funcionando.
git remote set-url origin "git@github.com:${GIT_USER}/cyberpanel.git"
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream https://github.com/usmannasir/cyberpanel.git
key=$(cat /etc/cyberpanel/softi-erp.key 2>/dev/null || true)
if [[ -n "$key" ]]; then
  curl -sk -H "X-Softi-Api-Key: $key" https://127.0.0.1:8090/api/softi/v1/health; echo
fi
echo "Marcas SOFTI-MEJORA en el código: $(grep -rl 'SOFTI-MEJORA' --include='*.py' --include='*.html' --include='*.css' . 2>/dev/null | wc -l) archivo(s)"
paso "Listo. Respaldo en $BACKUP_DIR"
