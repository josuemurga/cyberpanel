#!/bin/bash


# Short Description :Deploy imunify360/ImunifyAV
# Description       :Installs imunify360/ImunifyAV repository
# Copyright         :Cloud Linux Zug GmbH
# License           :Cloud Linux Commercial License

# Do not edit/move/reformat this line except for actual version bump
# it is used by old versions of deploy scripts to check for update
version="2.152"

readonly package="imunify360-firewall"
readonly imunify360="imunify360-firewall"
readonly imunify_av="imunify-antivirus"


if [[ "$package" != "$imunify360" ]] && [[ "$package" != "$imunify_av" ]]; then
  exit 1
fi


if [[ "$package" = "$imunify360" ]]; then
    PRODUCT="Imunify360"
    UI_PACKAGE="imunify-ui-firewall"
    COMMAND="imunify360-agent"
    STAND_ALONE_URL="https://docs.imunify360.com/control_panel_integration/#introduction"
    LOG_FILE="/var/log/i360deploy.log"
    LOCK="/var/lock/i360deploy.lck"
    # packages mentioned in the update command in the daily cron job + PD packages
    readonly additional_packages_to_remove="cloudlinux-backup-utils\
    imunify360-ossec\
    imunify360-pam\
    imunify360-php-i360\
    imunify360-webshield-bundle\
    imunify360-unified-access-logger"
    readonly additional_packages_to_remove_av="ai-bolit\
    alt-common-release\
    alt-php-hyperscan\
    imunify-release\
    imunify-common\
    imunify-notifier\
    imunify-core\
    imunify-realtime-av\
    imunify-realtime-av-imrt2\
    rustbolit\
    imunify-ui\
    imunify-wp-security\
    imunify360-venv\
    imunify-antivirus\
    imunify-patchman"
    readonly additional_packages_to_remove_cl="alt-php-internal\
    app-version-detector"
    readonly additional_packages_to_remove_centos="imunify-auditd-log-reader\
    minidaemon"
    readonly additional_packages_to_remove_debian=""
fi


readonly YUM_DISABLED_PHP_REPOS_OPTION="--disablerepo=imunify360-ea-php-hardened*"
OS_RELEASE_INFO=/etc/os-release
set -o pipefail
# fail if any error: will not
#set -e
# error for unbound variable: not for now
#set -eu

# $1 = Message prompt
# Returns ans=0 for yes, ans=1 for no
yesno() {
    local YES=0
    local NO=1
    local PENDING=2

    if [ $dry_run -eq 1 ]; then
        echo "Would be asked here if you wanted to"
        echo "$1 (y/n - y is assumed)"
        local ans=$YES
    elif [ "$assumeyes" = "true" ]; then
        local ans=$YES
    else
        local ans=$PENDING
    fi

    while [ $ans -eq $PENDING ]; do
        echo "Do you want to $1 (y/n) ?" ; read -r reply
        case "$reply" in
            Y*|y*) ans=$YES ;;
            N*|n*) ans=$NO ;;
            *) echo "Please answer y or n" ;;
        esac
    done

    return "$ans"
}

prepend_timestamp() {
    # Prepend current time to each line
    #
    # Usage: source-program | prepend_timestamp
    #
    # Note: it may fail if the input contains \0 bytes
    while IFS= read -r line
    do
        printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$line"
    done
}

log()
{
    # Run given command and append its duplicated stdout/stderr to
    # $LOG_FILE.
    #
    # Usage: log <command> [<args>...]
    #
    "$@" |& prepend_timestamp | tee -a "$LOG_FILE"
    return "${PIPESTATUS[0]}"
}

exit_with_error()
{
    log echo -e "$@"
    rm -rf "$lock"
    exit 1
}

print_debug_info()
{
    if [ "$DEBUG" == "true" ]; then
        echo "$@"
    fi
}

# Only for imunify360-firewall
set_low_resource_usage_mode_if_necessary()
{
  local _package=$1
  local _package_version=$2
  imunify360_low_mem_limit=2147483648
  imunify360_python38_datadir=$venv_path/share/imunify360
  # total usable memory in bytes
  mem_total=$(</proc/meminfo awk '$1 == "MemTotal:" { printf "%.0f", $2 * 1024 }')
  if (( mem_total < imunify360_low_mem_limit )); then
    # enable "Low Resource Usage" mode
    local low_mem_config="$imunify360_python38_datadir/20-low-mem-settings.config"
    if [ -f "$low_mem_config" ]; then
        log echo "Installing $low_mem_config from $_package $_package_version"
        ln -s "$low_mem_config" /etc/sysconfig/imunify360/imunify360.config.d/ && log echo "Done."
    fi
  fi
}

populate_os_release_vars()
{
    # shellcheck source=/etc/os-release
    [ -f "$OS_RELEASE_INFO" ] && source "$OS_RELEASE_INFO"
}


is_debian_like()
{
    populate_os_release_vars
    [[ "$ID" == "debian" || "$ID" == "ubuntu" ]]
}

check_exit_code() { if [ $? -ne "$1" ]; then exit_with_error "$2"; fi; }

disable_3rd_party_ids()
{
    if [ -d "$venv_path" ]; then
        echo "imunify360-venv detected"
        imunify360_python38_datadir=$venv_path/share/imunify360
    fi
    if [ -d "$imunify360_python38_datadir" ]; then
        datadir="$imunify360_python38_datadir"
    else
        datadir="$imunify360_python35_datadir"
    fi

    $datadir/scripts/disable_3rd_party_ids
}

install_first_install_default_overrides()
{
    local first_install_package=$1
    local package_version=$2
    if [ -d "$venv_path" ]; then
        echo "imunify360-venv detected"
        imunify360_python38_datadir=$venv_path/share/imunify360
    fi
    local first_install_config_deprecated="$imunify360_python38_datadir/10_on_first_install.config"
    local first_install_config_core="$imunify360_python38_datadir/10_on_first_install_core.config"
    local first_install_config_av="$imunify360_python38_datadir/10_on_first_install_av.config"
    local first_install_config_ids="$imunify360_python38_datadir/10_on_first_install_ids.config"
    if [ -f "$first_install_config_deprecated" ]; then
        log echo "Installing $first_install_config_deprecated from $first_install_package $package_version"
        cp -v "$first_install_config_deprecated" /etc/sysconfig/imunify360/imunify360.config.d/ && log echo "Done."
    else
        log echo "Installing $first_install_config_core from $first_install_package $package_version"
        cp -v "$first_install_config_core" /etc/sysconfig/imunify360/imunify360.config.d/ && log echo "Done."

        log echo "Installing $first_install_config_av from $first_install_package $package_version"
        cp -v "$first_install_config_av" /etc/sysconfig/imunify360/imunify360.config.d/ && log echo "Done."
        # touch flag file to indicate that the first install config has been applied
        touch /etc/sysconfig/imunify360/imunify360.config.d/.11_on_first_install_wp_av.flag

        if [[ "$package" = "$imunify360" ]]; then
            log echo "Installing $first_install_config_ids from $first_install_package $package_version"
            cp -v "$first_install_config_ids" /etc/sysconfig/imunify360/imunify360.config.d/ && log echo "Done."
        fi
    fi
}

remove_first_install_default_overrides()
{
    unlink /etc/sysconfig/imunify360/imunify360.config.d/10_on_first_install.config 2>/dev/null || true
    unlink /etc/sysconfig/imunify360/imunify360.config.d/10_on_first_install_core.config 2>/dev/null || true
    unlink /etc/sysconfig/imunify360/imunify360.config.d/10_on_first_install_av.config 2>/dev/null || true
    unlink /etc/sysconfig/imunify360/imunify360.config.d/10_on_first_install_ids.config 2>/dev/null || true
}

init_vars()
{
    wget="/usr/bin/wget"
    wget_options="-q --retry-connrefused --waitretry=15 --read-timeout=20 --timeout=15 -t 15"
    uninstall=false
    purge=false
    conversion=false
    beta=false
    if [ -f /var/imunify360/force_install_from_beta.flag ]; then
        beta=true
    fi
    install_vendors=false
    freemium=false
    downgrade=false
    post_os_upgrade=false
    compatibility_check_script="compatibility-check.sh"

    # get full path to the current script
    script="$1"
    case "$script" in
        ./*) script="$(pwd)/${script#*/}" ;;
        /*) script="$script" ;;
        *) script="$(pwd)/$script" ;;
    esac
    scriptname=$(basename "$script")
    script_run_args="$2"

    # Update checker URL
    checksite="https://repo.imunify360.cloudlinux.com/defense360/"
    upgradeurl="$checksite$scriptname"
    dry_run="0"

    assumeyes=false
    modifying_call=false
    yum_beta_option=""
    yum_beta_repo_enable=0
    apt_force=""

    apt_allow_unauthenticated=""
    if [[ "$package" = "$imunify360" ]]; then
        # Virtuozzo 7 with kernel 3.10.0 or later has support for ipset in Container
        VZ_VERSION_LONG=3.10.0-327.10.1.vz7.12.8
        # Inside VZ version is provided without release
        VZ_VERSION_BRIEF=3.10.0
        readonly imunify360_python35_datadir=/opt/alt/python35/share/imunify360
    fi
    imunify360_python38_datadir=/opt/alt/python38/share/imunify360
    venv_path=/opt/imunify360/venv
}

version()
{
    local lhs=$1
    local op=$2
    local rhs=$3

    case $op in
        -lt) test "$(echo -e "$lhs\\n$rhs" | sort --version-sort | head -1)" = "$lhs" && \
            test "$lhs" != "$rhs"
            return $?
        ;;
        *) echo "function version(): operator $op is not supported."
            return 2
        ;;
    esac
}

check_package_version()
{
    version="$1"
    if [ -z "$version" ]; then
        echo "No available package detected"
        return 1
    else
        echo "$version"
    fi
}

get_available_debian_package_version()
{
    version=$(apt-cache policy "$1" 2>/dev/null | sed -n '3p' | awk '{split($0, candidate); print candidate[2]}')
    check_package_version "$version"
    return $?
}

get_available_centos_package_version()
{
    version=$(yum $yum_beta_option $YUM_DISABLED_PHP_REPOS_OPTION list available "$1" 2>/dev/null | grep -E "$1.x86_64|$1.noarch" | awk '{split($0, candidate); print candidate[2]}' | sort --version-sort | tail -n 1)
    check_package_version "$version"
    return $?
}

install_plugin() {
    local plugin_package=$1
    local panel=$2

    echo "Installing $PRODUCT $panel plugin..."
    install_${ostype}_pkgs "$plugin_package-$panel"
    check_exit_code 0 "Failed to install $PRODUCT $panel plugin."
}

install_ui_part() {
    local ui_package=$1
    local panel=$2

    echo "Installing UI part of $PRODUCT $panel plugin..."
    install_${ostype}_pkgs "$ui_package-$panel"
    check_exit_code 0 "Failed to install UI part of $PRODUCT $panel plugin."
}

check_and_install() {
    local package_to_install=$1
    local package_version=$2
    local ui_package=$3
    local panel=$4

    if version "$package_version" -lt "7.3"; then
        install_plugin "$package_to_install" "$panel"
    else
        if [[ "$package_to_install" = "$imunify360" ]]; then
            install_plugin $package_to_install $panel
        fi
        install_ui_part "$ui_package" "$panel"
    fi
}

check_hardened_php_status()
{
    local agent_bin='/usr/bin/imunify360-agent'
    local python_bin='/opt/imunify360/venv/bin/python'
    local status=$(\
        ${agent_bin} features status hardened-php --json |\
        ${python_bin} -c 'import json; print(json.loads(input()).get("items", {}).get("status"))'\
    )
    echo ${status}
}

remove_hardened_php_feature()
{
    local agent_bin='/usr/bin/imunify360-agent'
    local python_bin='/opt/imunify360/venv/bin/python'
    # sometimes it takes a long time to remove hardened-php
    # especially in the Plesk environment
    local timeout=1500

    if [ ! -f ${agent_bin} ] || [ ! -f ${python_bin} ]; then
        return
    fi

    if [ "$(check_hardened_php_status)" != "installed" ]; then
        return
    fi

    echo "Warning: Hardened PHP packages will be removed"\
         "and replaced with the default ones if possible."\
         "Some sites may stop working"

    echo -n "Starting removal, this may take a couple of minutes"
    local logfile="$(${agent_bin} features remove hardened-php)"
    local start_ts=$(date +%s)

    while true; do
        removal_status="$(check_hardened_php_status)"
        [ "${removal_status}" = "not_installed" ] && echo OK && break

        local current_ts=$(date +%s)
        if [ $((current_ts - start_ts)) -gt ${timeout} ]; then
            echo TIMEOUT
            exit_with_error "Error occured while trying to remove Hardened PHP packages."\
                            "See log: ${logfile}"
        fi
        echo -n "."
        sleep 5
    done
}

install_vendors_in_cw_environment()
{
    # log output but hide it from stdout
    log echo "Run vendor installation in background for Cloudways"
    file_path="/var/imunify360/files/modsec/v2/description.json"
    while [ ! -f "$file_path" ]; do
        log echo "Waiting for $file_path to appear"
        sleep 5
    done
    log echo "Installing vendors"
    log /usr/bin/imunify360-agent --console-log-level=WARNING install-vendors
}

do_migrate_patchman()
{
    log echo "Run patchman migration..."
    log imunify-antivirus patchman migrate
    check_exit_code 0 "Failed to migrate patchman service."
}

refresh_debian_repos() {
    if ! log run_with_retries "apt-get update" ""; then
        test "$dev_install" = true
        if [ $? -ne 0 ]; then
            log echo "apt-get update error."
            exit 1
        fi
    fi
}

enable_debian_beta_repo() {
    if test -f /etc/apt/sources.list.d/imunify360-testing.list.example ; then
        log cp /etc/apt/sources.list.d/imunify360-testing.list.example /etc/apt/sources.list.d/imunify360-testing.list
    fi
    if test -f /usr/share/imunify360/apt/imunify360-testing.list.disabled ; then
        log cp /usr/share/imunify360/apt/imunify360-testing.list.disabled /etc/apt/sources.list.d/imunify360-testing.list
    fi
}

enable_centos_beta_repo() {
    log yum-config-manager --enable imunify360-testing
}

install_imunify_release() {
    if [[ $ostype = debian ]]; then
        suffix="$ID.$VERSION_ID.deb"
        if test -f /etc/apt/sources.list.d/imunify360.list ; then
            if [ "$beta" = "true" ]; then
                enable_debian_beta_repo
                refresh_debian_repos
            fi
            log echo "repo is already present, skip installation of imunify-release"
            return 0
        fi
    else
        if test -f /etc/yum.repos.d/imunify360.repo ; then
            if [ "$beta" = "true" ]; then
                enable_centos_beta_repo
            fi
            log echo "repo is already present, skip installation of imunify-release"
            return 0
        fi
        suffix="el${VERSION_ID%%.*}.rpm"
    fi

    local pkg_name="imunify-release-latest.$suffix"

    log echo "Downloading imunify-release package: $pkg_name"
    log wget "https://repo.imunify360.cloudlinux.com/defence360/$pkg_name" -O $pkg_name


    if [[ $ostype = debian ]]; then
        # since for debian/ubuntu gpg key is added to common location (/etc/apt/trusted.gpg.d/) -
        # allow overwriting config files to avoid conflicts if gpg key was added manually
        log dpkg -i --force-confmiss --force-confnew ./$pkg_name
    else
        log yum install -y ./$pkg_name
    fi

    if [[ $ostype = debian ]]; then
        if [ "$beta" = "true" ]; then
            enable_debian_beta_repo
        fi

        refresh_debian_repos
    else
        log rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-CloudLinux-Imunify
        if [ "$beta" = "true" ]; then
            enable_centos_beta_repo
        fi
    fi
}

post_os_upgrade_repos()
{
    if [[ "$ostype" != "debian" ]]; then
        log echo "OS upgrade repo refresh is only needed for Debian/Ubuntu systems."
        log echo "RPM-based systems use \$releasever which resolves dynamically."
        exit 0
    fi

    if ! check_debian_pkg_presence "$package"; then
        exit_with_error "$package is not installed. Nothing to upgrade."
    fi

    log echo "Refreshing $PRODUCT repositories after OS upgrade..."
    log echo "Detected OS: $ID $VERSION_ID"

    # Download and install imunify-release for the current OS
    # --force-confnew ensures all repo .list files are overwritten with new OS URLs
    local suffix="$ID.$VERSION_ID.deb"
    local pkg_name="imunify-release-latest.$suffix"
    log echo "Downloading imunify-release package: $pkg_name"
    log $wget $wget_options -O "$pkg_name" \
        "https://repo.imunify360.cloudlinux.com/defence360/$pkg_name"
    if [ ! -s "$pkg_name" ]; then
        exit_with_error "Failed to download $pkg_name. Is $ID $VERSION_ID supported?"
    fi
    log dpkg -i --force-confmiss --force-confnew "./$pkg_name"
    check_exit_code 0 "Failed to install imunify-release package."
    rm -f "./$pkg_name"

    # Handle GPG key delivered as .dpkg-dist (can happen despite --force-confnew)
    local gpg_key_path="/etc/apt/trusted.gpg.d/RPM-GPG-KEY-CloudLinux.gpg"
    if [ -f "${gpg_key_path}.dpkg-dist" ]; then
        log echo "Replacing GPG key with version from package (.dpkg-dist)..."
        mv -f "${gpg_key_path}.dpkg-dist" "$gpg_key_path"
    fi

    # The testing repo .list is a runtime copy (not a dpkg conffile),
    # so --force-confnew does not update it. Use its presence as a marker
    # that beta was enabled, then recreate with correct URLs.
    if [ -f /etc/apt/sources.list.d/imunify360-testing.list ] || [ "$beta" = "true" ]; then
        log echo "Re-enabling beta repository..."
        rm -f /etc/apt/sources.list.d/imunify360-testing.list
        enable_debian_beta_repo
    fi

    # Refresh package lists with the new repos
    log echo "Refreshing package lists..."
    refresh_debian_repos

    # Reinstall the package to get the version built for the new OS
    log echo "Reinstalling $package for $ID $VERSION_ID..."
    export DEBIAN_FRONTEND=noninteractive
    run_with_retries "apt-get install --reinstall -y \
        -o Dpkg::Options::=--force-confdef \
        -o Dpkg::Options::=--force-confold \
        $package" "Could not get lock"
    check_exit_code 0 "Failed to reinstall $package."

    # Restart the service to pick up the new OS info
    if is_systemctl_avail; then
        log echo "Restarting $PRODUCT service..."
        if [[ "$package" = "$imunify360" ]]; then
            log systemctl restart imunify360 imunify360-agent
        else
            log systemctl restart "$package"
        fi
    fi

    log echo "OS upgrade repository refresh complete."
    log echo "$PRODUCT is now configured for $ID $VERSION_ID."
}

remove_imunify_release() {
    log remove_${ostype}_pkgs imunify-release

    if [[ $ostype = debian && $beta = true ]]; then
        # imunify360-testing repo is added by imunify-release as imunify360-testing.list.[example|disabled].
        # then in case of `$beta = true` it is enabled by copying it to imunify360-testing.list.
        # so, in case of $beta imunify360-testing.list must be removed manually.
        log rm /etc/apt/sources.list.d/imunify360-testing.list
    fi
}

run_compatibility_check() {
    local script_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
    local script_path="$script_dir/$compatibility_check_script"

    if [[ -f "$script_path" ]]; then
        bash $script_path --$package
    else
        $wget -qO- "$checksite$compatibility_check_script" | bash -s -- --$package
    fi
}

# Compile and load the product's SELinux policy module so services like
# imunify-notifier work on SELinux-enforcing hosts without manual steps
# (DEF-36450, https://docs.imunify360.com/installation/#selinux-support).
# Silent no-op on non-CentOS, SELinux-disabled hosts, or when the policy
# source is not on disk yet.
apply_selinux_policy()
{
    if [[ "$ostype" != "centos" ]]; then
        log echo "apply_selinux_policy: ostype=$ostype is not centos; skipping"
        return 0
    fi

    if ! command -v getenforce >/dev/null 2>&1; then
        log echo "apply_selinux_policy: getenforce not found; skipping"
        return 0
    fi

    local selinux_state
    selinux_state="$(getenforce 2>/dev/null || true)"
    if [ "$selinux_state" = "Disabled" ] || [ -z "$selinux_state" ]; then
        log echo "apply_selinux_policy: SELinux is disabled; skipping"
        return 0
    fi

    local policy_name
    if [[ "$package" = "$imunify360" ]]; then
        policy_name="imunify360"
    else
        policy_name="imunify-antivirus"
    fi

    # Policy source search paths (venv path is canonical per upstream docs;
    # the RPM %{_datadir} location is kept as a fallback). The env overrides
    # exist so Bats tests can redirect the probe into BATS_TMPDIR.
    local te_primary_dir="${SELINUX_TE_PRIMARY_DIR:-/opt/imunify360/venv/share/imunify360}"
    local te_fallback_dir="${SELINUX_TE_FALLBACK_DIR:-/usr/share/imunify360}"
    local te_path=""
    local candidate
    for candidate in \
        "${te_primary_dir}/${policy_name}.te" \
        "${te_fallback_dir}/${policy_name}.te"; do
        if [ -f "$candidate" ]; then
            te_path="$candidate"
            break
        fi
    done

    if [ -z "$te_path" ]; then
        log echo "apply_selinux_policy: ${policy_name}.te not found; skipping"
        return 0
    fi

    if ! command -v checkmodule >/dev/null 2>&1; then
        # `/usr/bin/checkmodule` is owned by `checkpolicy` on every EL
        # release (6 through 9); upstream docs mention
        # policycoreutils-python-utils but that only "works" on EL8+ via a
        # transitive dep and pulls in far more than we need.
        log echo "apply_selinux_policy: installing checkpolicy for checkmodule"
        log install_centos_pkgs checkpolicy
        if ! command -v checkmodule >/dev/null 2>&1; then
            log echo "apply_selinux_policy: checkmodule still missing after install; skipping"
            return 0
        fi
    fi

    local workdir
    workdir="$(mktemp -d -t imunify-selinux-XXXXXX)"
    if [ ! -d "$workdir" ]; then
        log echo "apply_selinux_policy: failed to create temp directory; skipping"
        return 0
    fi
    # Clean up on any exit path (success, failure, or error).
    trap 'rm -rf "$workdir"' RETURN

    local mod_path="$workdir/${policy_name}.mod"
    local pp_path="$workdir/${policy_name}.pp"

    if ! log checkmodule -M -m -o "$mod_path" "$te_path"; then
        log echo "apply_selinux_policy: checkmodule failed for $te_path"
        return 0
    fi
    if ! log semodule_package -o "$pp_path" -m "$mod_path"; then
        log echo "apply_selinux_policy: semodule_package failed"
        return 0
    fi
    # semodule -i is idempotent; on re-runs it upgrades the module in place.
    if ! log semodule -i "$pp_path"; then
        log echo "apply_selinux_policy: semodule -i failed"
        return 0
    fi
    log echo "apply_selinux_policy: ${policy_name} SELinux policy loaded"
}


run_with_retries()
{
    cmd=$1
    expected_error_text=$2
    ignore_res=$3

    min_timeout=2
    max_timeout=30

    nattempts=10

    for ((i=1;i<=nattempts;i++)); do
        output=$( { $cmd ; } 2>&1 )
        res=$?
        if [ $res -eq 0 ] && [[ "$ignore_res" != "true" ]]; then
            echo "$output"
            break
        else
            if echo "$output" | grep -q "$expected_error_text"; then
                echo "$output"
                echo "Attempt #$i/$nattempts: to run $cmd."
                timeout=$(($RANDOM%($max_timeout-$min_timeout+1)+$min_timeout))
                [ $i -ne $nattempts ] && echo "Retrying in $timeout seconds.."
                sleep $timeout
            else
                echo "$output"
                break
            fi
        fi
    done
    return $res
}

reopen_log()
{
    echo "-- $(date -R): $script $script_run_args --" >> "$LOG_FILE"
    chmod 0600 "$LOG_FILE"
}

check_debian_pkg_presence()
{
    test "$(dpkg-query --show --showformat='${db:Status-Status}\n' "$1" 2>/dev/null)" = "installed"
}

check_centos_pkg_presence()
{
    rpm --query "$1" >/dev/null
}

should_perform_downgrade() {
    if [[ "$package" = "$imunify_av" ]]; then
        downgrade=false
      return 1
    # https://cloudlinux.atlassian.net/browse/DEF-33180 Decided to postpone having this as default action for  plesk/cpanel
    # elif [ "$downgrade" = "true" ] || [ "$PANEL" = "plesk" ] || [ "$PANEL" = "cpanel" ]; then
    elif [ "$downgrade" = "true" ]; then
    #    downgrade=true
        return 0
    else
        return 1
    fi
}

verify_imunify_av() {
    log echo "Verifying ImunifyAV installation..."

    # Get the list of packages to verify from additional_packages_to_remove_av
    # and remove imunify-realtime-av from the list
    local packages_to_verify=""
    for _package in $additional_packages_to_remove_av; do
        if [ "$_package" != "imunify-realtime-av" ] && [ "$_package" != "imunify-patchman" ]; then
            packages_to_verify="$packages_to_verify $_package"
        fi
    done
    packages_to_verify="$packages_to_verify imunify-antivirus-$PANEL"
    packages_to_verify="$packages_to_verify imunify-antivirus-$PANEL"

    # UI package if panel is detected
    if [ "$PANEL" = generic ]; then
        packages_to_verify="$packages_to_verify imunify-ui-$PANEL"
    else
        packages_to_verify="$packages_to_verify imunify-ui-antivirus-$PANEL"
    fi
    # Flag to track if any package is missing
    local missing_packages=0

    # Check each package
    for _package in $packages_to_verify; do
        if ! check_${ostype}_pkg_presence "$_package"; then
            log echo "WARNING: Package $_package is missing."
            missing_packages=1
        fi
    done

    # Return status based on missing packages
    if [ $missing_packages -eq 0 ]; then
        log echo "All ImunifyAV packages are properly installed."
        return 0
    else
        log echo "ERROR: Some ImunifyAV packages are missing. Manual intervention may be required."
        exit 1
    fi
}

# Function to mark ImunifyAV packages as manually installed for Debian
mark_debian_av_manual() {
    echo "Marking ImunifyAV as manually installed to preserve it and its dependencies..."
    # Check if ImunifyAV is installed before marking
    if check_debian_pkg_presence "imunify-antivirus"; then
        apt-mark manual imunify-antivirus-$PANEL
        if [ "$PANEL" = "generic" ]; then
          apt-mark manual imunify-ui-generic
        else
          apt-mark manual imunify-ui-antivirus-$PANEL
        fi
    fi
}


# Function to mark ImunifyAV packages as user-installed for CentOS
mark_centos_av_manual() {
    echo "Marking ImunifyAV as user-installed to preserve it and its dependencies..."

    # Check if ImunifyAV is installed before marking
    if ! rpm -q imunify-antivirus &>/dev/null; then
        return
    fi

    local ui_package="imunify-ui-${PANEL}"
    [[ "$PANEL" != "generic" ]] && ui_package="imunify-ui-antivirus-${PANEL}"

    if [[ "$VERSION_ID" == 7* ]]; then
        yumdb set reason user "imunify-antivirus-${PANEL}"
        yumdb set reason user "${ui_package}"
    else
        yum mark install "imunify-antivirus-${PANEL}"
        yum mark install "${ui_package}"
    fi
}

remove_debian_imunify()
{
    local pkgs_to_remove="$package $additional_packages_to_remove $additional_packages_to_remove_debian"
    if [ "$downgrade" = "false" ]; then
      pkgs_to_remove="$pkgs_to_remove $additional_packages_to_remove_av"
    fi
    if [ "$purge" = "true" ]; then
        local purge_flag="--purge"
    else
        local purge_flag=""
    fi
    apt-mark unhold $pkgs_to_remove
    # --ignore-missing doesn't work if apt doesn't know about package, so
    # resolve the list to packages that dpkg actually has records for.
    # Also caches the result into a variable so run_with_retries' word-
    # splitting doesn't re-invoke the substitution on every retry.
    # shellcheck disable=SC2086
    local installed_pkgs
    installed_pkgs=$(dpkg-query -W -f='${binary:Package}\n' $pkgs_to_remove 2>/dev/null)
    # Idempotency: re-running --uninstall on a clean Debian system must not
    # fail. apt-get remove with an empty package list errors out, so short-
    # circuit here before the dry-run and yesno prompt.
    if [ -z "$installed_pkgs" ]; then
        echo "No imunify packages installed; nothing to remove."
        return 0
    fi
    # shellcheck disable=SC2086
    apt-get remove $purge_flag --autoremove --ignore-missing --dry-run $installed_pkgs
    yesno "apt-get $purge_flag --AUTOREMOVE to remove $installed_pkgs plus \
    aforementioned packages [y] or just $installed_pkgs [n]"
    local res=$?
    if [ $res = 0 ]; then
        local autoremove="--autoremove"
    else
        local autoremove=""
    fi
    run_with_retries "apt-get remove $purge_flag $autoremove -y --ignore-missing $installed_pkgs" "Could not get lock"
    local remove_res=$?
    if [ $remove_res -ne 0 ]; then
        return $remove_res
    fi
    # dpkg-query exits non-zero for any unknown package, so ignore exit code
    # and filter on Status-Status=='installed' instead.
    # shellcheck disable=SC2086
    local still_installed
    still_installed=$(dpkg-query -W -f='${binary:Package} ${db:Status-Status}\n' $pkgs_to_remove 2>/dev/null \
        | awk '$2=="installed"{print $1}')
    if [ -n "$still_installed" ]; then
        echo "ERROR: imunify packages still installed after remove:"
        echo "$still_installed"
        return 1
    fi
}

remove_centos_imunify()
{
    local pkgs_to_remove="$package $additional_packages_to_remove $additional_packages_to_remove_centos"

    if [ "$downgrade" = "false" ]; then
      if rpm -q cloudlinux-release &>/dev/null; then
          # if it is CLOS leave "alt-php-internal" and "app-version-detector" as is
          local pkgs_to_remove="$pkgs_to_remove $additional_packages_to_remove_av"
      else
          # Otherwise the also could be removed
          local pkgs_to_remove="$pkgs_to_remove $additional_packages_to_remove_av $additional_packages_to_remove_cl"
      fi
    fi
    yum remove -y $yum_beta_option $YUM_DISABLED_PHP_REPOS_OPTION                       \
        $pkgs_to_remove --setopt=clean_requirements_on_remove=1
}

remove_freemium_flag()
{
    if [ ! -f "/var/imunify360/myimunify-freemium.flag" ]; then
        return
    fi

    rm -f "/var/imunify360/myimunify-freemium.flag"
}

get_debian_pkgs_manager() {
    pkgs_manager="apt-get"
}

get_centos_pkgs_manager() {
    pkgs_manager="yum"
}

remove_debian_pkgs()
{
    if [ "$purge" = "true" ]; then
        local purge_flag="--purge"
    else
        local purge_flag=""
    fi

    run_with_retries "apt-get remove -y $purge_flag $*" "Could not get lock"
}

remove_centos_pkgs()
{
    yum remove -y "$@"
}

install_debian_pkgs()
{
    local pkgs=$*
    run_with_retries "apt-get $apt_opts install -y $apt_allow_unauthenticated $apt_force $pkgs" ""
}

install_centos_pkgs()
{
    local pkgs=$*
    yum install -y $yum_beta_option $YUM_DISABLED_PHP_REPOS_OPTION $pkgs
}

install_debian_ipset()
{
    install_debian_pkgs ipset
}

install_centos_ipset()
{
    yum install -y ipset
}

detect_first_install()
{
    if check_${ostype}_pkg_presence "$package" >/dev/null
    then
        first_install=false
    else
        first_install=true
    fi
}

is_systemctl_avail()
{
    command -v systemctl >/dev/null 2>&1
}


# $1 = Full URL to download
# $2 = Optional basename to save to (if omitted, then = basename $1)
#      Also allow download to fail without exit if $2 is set
download_file() {
    if [ "$2" = "" ]; then
        dlbase="$(basename "$1")"
    else
        dlbase="$2"
    fi

    if [ $dry_run -eq 1 ]; then
        echo "Would download this URL to $dlbase :"
        echo "$1" ; echo
        return
    fi

    old_dlbase="$dlbase.old"
    if [ -f "$dlbase" ]; then
        rm -f "$old_dlbase"
        mv -f "$dlbase" "$old_dlbase"
    fi

    echo "Downloading $dlbase (please wait)"
    $wget $wget_options -O "$dlbase" "$1"

    if [ ! -s "$dlbase" ]; then
        if [ -f "$old_dlbase" ]; then
            mv -f "$old_dlbase" "$dlbase"
        fi
        if [ "$2" = "" ]; then
            echo "Failed to download $dlbase"
            exit 1
        fi
    fi
}

# Make sure that we are running the latest version
# $* = Params passed to script
check_version() {
    echo "Checking for an update to $scriptname"
    script_from_repo="$scriptname.repo_version"
    download_file "$upgradeurl" "$script_from_repo"
    newversion=$(grep  "^version=" "$script_from_repo" | sed 's/[^0-9.]*//g')
    if [ -z "$newversion" ]; then
        newversion=$version
    fi

    if [ $dry_run -eq 1 ]; then
        echo -e "Would check if this running script (version $version) is out of date. \n" \
            "If it's been superseded, the new version would be downloaded and you'd be asked \n" \
            "if you want to upgrade to it and run the new version. \n"
        return
    fi

    local latest_version
    latest_version=$(echo -e "$version\\n$newversion" | sort --reverse --version-sort | head -1)
    if [ "$latest_version" = "$version" ]; then
        echo "$scriptname is already the latest version ($version) - continuing"
        rm -f "$script_from_repo"
    else
        echo "New version ($newversion) of $scriptname detected"
        if yesno "run $scriptname $newversion now"
        then
            echo "OK, executing $script_from_repo $*"
            # replace the current script with a new one
            mv -f "$script_from_repo" "$script"
            chmod u+x "$script"
            echo "Download of $scriptname $newversion successful"
            rm "$LOCK"
            echo "Run $script $script_run_args"
            # use $script_run_args without quotes to avoid error
            # `getopt: unrecognized option` if there are more than 1 arguments
            # shellcheck disable=SC2086
            exec "$script" --skip-version-check $script_run_args
            error "Failed to run $script $script_run_args"
        else
            echo -e "New version of script is available: $upgradeurl \n" \
                "It was downloaded to $script_from_repo \n" \
                "If you prefer to use current version, run it with \"--skip-version-check\" key. \n"
            exit 1
        fi
    fi
}

remove_debian_repo()
{
    rm /etc/apt/sources.list.d/imunify360-alt-php.list 2>/dev/null
}

remove_centos_repo()
{
    rm /etc/yum.repos.d/imunify360-ea-php-hardened \
    /etc/yum.repos.d/imunify360-alt-php 2>/dev/null
}

remove_acronis_agent()
{
    [ ! -e /usr/bin/restore_infected ] && return

    if /usr/bin/restore_infected acronis extra is_installed 2> /dev/null; then
        # If Acronis installation logs are present in restore_infected folder,
        #   then remove Acronis and the logs
        if ls /var/restore_infected/acronis_installation*.log; then
            /usr/bin/restore_infected acronis extra uninstall > /dev/null || :
            rm -f /var/restore_infected/acronis_installation*.log
        fi
    fi
}

terminate_detached_scans ()
{
    for file in /var/imunify360/aibolit/run/*/pid; do
        test -e "$file" && kill -9 "$(cat "$file")"
    done
    rm -rf /var/imunify360/aibolit/run/
    rm -rf /var/imunify360/aibolit/scans.pickle
}

# Only for imunify360-firewall
remove_hardened_php_repos()
{
    if [[ $ostype = centos ]]; then
        ALT_PHP=imunify360-alt-php.repo
        EA_PHP=imunify360-ea-php-hardened.repo
        REPOS_DIR=/etc/yum.repos.d

        # fix permissions
        for REPO in $ALT_PHP $EA_PHP; do
            test -f $REPOS_DIR/$REPO || continue
            chattr -i $REPOS_DIR/$REPO
            chmod 644 $REPOS_DIR/$REPO
        done

        # remove unconditionally
        rm -f $REPOS_DIR/$ALT_PHP
        rm -f $REPOS_DIR/$EA_PHP
    fi
}

print_help ()
{
    cat << EOF >&2
Usage:

  -h, --help            Print this message
  --version             Print script's version and exit
  -k, --key <key>       Deploy $PRODUCT with activation key
  -c, --uninstall       Uninstall $PRODUCT
  --skip-version-check  Do not check for script updates
  --skip-registration   Do not register, just install (the default)
  --dev-install         Turn off software defect reporting
  --beta                Install packages from 'testing' repo
  --check               Check if imunify360 Agent can be installed and exit
  --downgrade           Preserve ImunifyAV when uninstalling Imunify360
  --purge               Purge configuration and state files when uninstalling
  --post-os-upgrade     Run after dist-upgrade on Debian/Ubuntu systems
  -y, --yes             Assume "yes" as answer to all prompts and run non-interactively
EOF
}

print_version()
{
    echo "$scriptname $version"
}

check_centos_iptables_compatibility() {
    # dummy function that does nothing
    :
}


check_debian_iptables_compatibility() {
    if [ "$ID" == "debian" ] && [ "$VERSION_ID" == "10" ]
    then
        local apt_opts="-t buster-backports"
        log install_debian_pkgs iptables
        check_exit_code 0 "iptables >= 1.8.5 required on Debian 10. \n\
    Please, turn on buster-backports repository and run the script/installation again. \n\
    Buster-backports repository may be turned on by following command: \n\
        echo "deb http://ftp.debian.org/debian buster-backports main" > /etc/apt/sources.list.d/buster-backports.list \n\
    Then run: \n\
        apt-get update \n"
    fi
}

setup_imunify360_dir() {
  if [ ! -d "/var/imunify360/" ]; then
    mkdir -m 2755 -p /var/imunify360
  fi
}

install_revisium_premium_marker ()
{
    local key_directory="/etc/sw/keys/keys"
    local imunify_keytype="ImunifyAV+"
    if [ -d "$key_directory" ]; then
        # Search for the specified keytype in the keys
        if grep -q "<core:keytype>$imunify_keytype</core:keytype>" "$key_directory"/*; then
            # Create the flag
            setup_imunify360_dir
            touch "$PREMIUM_REVISIUM_EXTENSION"
            echo "AV+ license is detected in Revisium extension, creating marker file $PREMIUM_REVISIUM_EXTENSION"
        fi
    fi
}

remove_revisium_premium_marker ()
{
if [ -f "$PREMIUM_REVISIUM_EXTENSION" ]; then
    rm -f "$PREMIUM_REVISIUM_EXTENSION"
fi
}


disable_firewall() {
    setup_imunify360_dir
    touch /var/imunify360/firewall_disabled
}

special_config_cloudways()
{
    log echo "Installing cloudways configuration"
    imunify360_python38_datadir=$venv_path/share/imunify360
    local first_install_cloudways="$imunify360_python38_datadir/11_on_first_install_cloudways.config"
    cp -v "$first_install_cloudways" /etc/sysconfig/imunify360/imunify360.config.d/ && log echo "Done."
}

create_upgrade_process_marker()
{
    touch /var/imunify360/upgrade_process_started
    trap "rm -f /var/imunify360/upgrade_process_started" SIGTERM SIGINT SIGHUP EXIT
}

webshield_module_supported()
{
    which apachectl &>/dev/null && [ -x /usr/local/cpanel/cpanel ] && [ ! -d /usr/local/lsws ]
}

install_apache_config()
{
    local pkg=$1
    local ver=$2
    if [ -d "$venv_path" ]; then
        echo "imunify360-venv detected"
        imunify360_python38_datadir=$venv_path/share/imunify360
    fi
    local cfg="$imunify360_python38_datadir"/10_on_first_install_ids.apache.config
    log echo "Installing $cfg from $pkg $ver"
    cp -v "$cfg" /etc/sysconfig/imunify360/imunify360.config.d/ && log echo "Done."
}

remove_apache_config()
{
    unlink /etc/sysconfig/imunify360/imunify360.config.d/10_on_first_install_ids.apache.config 2>/dev/null || true
}

cleanup()
{
    rm -f "$LOCK"
}

rapid_scan_basedir_override() {
    touch /var/imunify360/rapid_scan_basedir_override
}

uninstall_plesk_extension() {
   if [ "$PANEL" = "plesk" ] && [ "$I360_FROM_PLESK_EXTENSION" != "1" ]; then
      if [ -x /usr/local/psa/bin/extension ]; then
          log echo "Uninstalling Plesk extension for $PRODUCT..."
          SKIP_PREUNINSTALL_CHECK=true log /usr/local/psa/bin/extension --uninstall imunify360 || true
      fi
   fi
}

# Lets start

# if environment has umask=0000 (if called from plesk extension), all created files have -rw-rw-rw- permission
umask 0022

init_vars "$0" "$*"
reopen_log

if [ -f "$LOCK" ] ; then
    if [ -d "/proc/$(cat "$LOCK")" ] ; then
        exit_with_error "$scriptname is already running"
    fi
fi

echo $$ > "$LOCK"
check_exit_code 0 "Please run $scriptname as root"

trap cleanup SIGTERM SIGINT SIGHUP EXIT

options=$(getopt -o ychk: -l yes,uninstall,purge,help,version,check,skip-version-check,skip-registration,beta,dev-install,force,apt-force,freemium,migrate-patchman,downgrade,post-os-upgrade,key: -- "$@")
res=$?

if [ "$res" != 0 ]; then
    print_help
    exit 1
fi

eval set -- "$options"

while true; do
    case "$1" in
        -h|--help)
            print_help
            exit 0
        ;;
        --version)
            print_version
            exit 0
        ;;
        -y|--yes)
            assumeyes=true
            export DEBIAN_FRONTEND=noninteractive
            if [ -z "$apt_force" ]; then
                apt_force='-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold'
            fi
            shift
        ;;
        -c|--uninstall)
            uninstall=true
            shift
        ;;
        -k|--key)
            conversion=true
            activationkey="$2"
            shift 2
        ;;
        --skip-version-check)
            skipversioncheck=true
            shift
        ;;
        --skip-registration)
            registration=false
            shift
        ;;
        --beta)
            beta=true
            yum_beta_option="--enablerepo=imunify360-testing"
            yum_beta_repo_enable=1
            shift
        ;;
        --freemium)
            freemium=true
            shift
        ;;
        --dev-install)
            dev_install=true
            apt_allow_unauthenticated=--allow-unauthenticated
            shift
        ;;
        --force|--apt-force)  # used for Plesk extension installation
            export DEBIAN_FRONTEND=noninteractive
            apt_force='-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confnew'
            shift
        ;;
        --check)
            run_compatibility_check
            EXIT_CODE=$?
            exit $EXIT_CODE
        ;;
        --migrate-patchman)
            migrate_patchman=true
            shift
        ;;

          --downgrade)
            downgrade=true
            uninstall=true
            shift
        ;;

        --purge)
            uninstall=true
            purge=true
            shift
        ;;
        --post-os-upgrade)
            post_os_upgrade=true
            shift
        ;;
        --)
            shift
            break
        ;;
        -*)
            echo "$0: error - unrecognized option $1" 1>&2
            print_help
            exit 1
        ;;
        *) exit_with_error "Internal error!" ;;
    esac
done

# --post-os-upgrade runs before the compatibility check because the
# broken repo state after a dist-upgrade may cause the check to fail.
if [ "$post_os_upgrade" = "true" ]; then
    if [ "$uninstall" = "true" ]; then
        exit_with_error "invalid combination: --post-os-upgrade and --uninstall"
    fi
    # Detect OS type without full compatibility check
    populate_os_release_vars
    if echo "$ID" "$ID_LIKE" | grep -q debian; then
        ostype=debian
    else
        ostype=centos
    fi
    post_os_upgrade_repos
    exit 0
fi

RESULT=$(run_compatibility_check)
check_exit_code 0 "Compatibility check failed with exit code\nCompatiblity check output:\n$RESULT"
log echo -e "Compatiblity check output:\n$RESULT"

# Parse and set the variables from the output
eval $(echo "$RESULT" | grep -E "^(ostype|is_cloudways|INTEGRATION_CONF_PATH|PANEL)=")

populate_os_release_vars

if [ "$skipversioncheck" = "true" ]; then
    log echo "Skipping check version"
else
    log check_version "$*"
fi

detect_first_install

if [[ "$package" = "$imunify360" ]]; then
    remove_hardened_php_repos
    # install vendors only for imunify360
    install_vendors="true"

    if [ "$is_cloudways" = "true" ]; then
        setup_imunify360_dir
        touch /etc/sysconfig/imunify360/.cloudways_environment
    fi
fi


if [ "$conversion" = "true" ] && [ "$uninstall" = "true" ] ; then
    exit_with_error "invalid combination";
fi

if [ "$conversion" = "false" ] && [ "$registration" != "false" ] ; then
    # Register by IP is the default now
    conversion=true
    activationkey=false
fi


if [ "$uninstall" = "true" ]; then
    remove_acronis_agent
    remove_hardened_php_feature
    remove_freemium_flag

    # Check if we need to downgrade
    if should_perform_downgrade; then
        log echo "Starting downgrade from Imunify360 to ImunifyAV..."
        # Mark ImunifyAV packages as manually installed
        log mark_${ostype}_av_manual
    fi

    # yum returns non-zero on already-missing packages, so only Debian can
    # reliably distinguish real failures from benign ones.
    if [ "$ostype" = "debian" ]; then
        if ! log remove_${ostype}_imunify; then
            exit_with_error "Failed to remove imunify packages (see log above for details)"
        fi
    else
        log remove_${ostype}_imunify
    fi



    log remove_apache_config



    if should_perform_downgrade; then
        # Don't remove the repository as ImunifyAV uses the same one
        # Verify ImunifyAV is still installed
        verify_imunify_av
        log echo "Downgrade to ImunifyAV complete."
    else
        remove_${ostype}_repo
        log remove_${ostype}_pkgs alt-common-release
        remove_imunify_release
        terminate_detached_scans
        log remove_first_install_default_overrides
        uninstall_plesk_extension
        log echo "Uninstall complete."
    fi
    exit 0
fi



if [[ "$package" = "$imunify360" ]]; then
    if ! check_${ostype}_pkg_presence ipset
    then
        log install_${ostype}_ipset
        check_exit_code 0 "Package ipset was not installed."
    fi

    if ! ipset list -n -t >/dev/null
    then
        exit_with_error "Your OS virtualization technology $(systemd-detect-virt 2>/dev/null || virt-what >/dev/null || echo of unknown type) has limited support for ipset in containers. Please, contact Imunify360 Support Team."
    fi

    check_${ostype}_iptables_compatibility

    # Do not remove AV explicitly after moving 6.10 version into stable repo
    if check_${ostype}_pkg_presence imunify-antivirus \
      && ! (check_${ostype}_pkg_presence imunify360-firewall);
    then
        # remove imunify-antivirus package for old imunify360 (due to conflict)
        # for new imunify360 versions AV is a dependency of imunify360
        package_version=$(get_available_${ostype}_package_version "$package")
        check_exit_code 0 "Failed to get package version"
        log echo "$package $package_version is available"

        if [[ "$is_cloudways" != "true" && "$PANEL" != "plesk" ]]; then
            # Marker file for UI for tracking the upgrade process
            create_upgrade_process_marker
        fi

        if version "$package_version" -lt "6.10" ; then
            get_${ostype}_pkgs_manager
            log echo "You are about to uninstall ImunifyAV and install Imunify360 that includes Malware Scanner. To get ImunifyAV back run the following commands:
            # $pkgs_manager remove 'imunify360-firewall*'
            # wget https://repo.imunify360.cloudlinux.com/defence360/imav-deploy.sh -O imav-deploy.sh
            # bash imav-deploy.sh"

            if yesno "Do you agree to proceed with uninstalling ImunifyAV?"; then
                log remove_${ostype}_pkgs 'imunify-antivirus'
            else
                exit 1
            fi
        fi
    fi

fi


if [[ "$package" = "$imunify360" ]]; then
    log echo "Checking prerequisites..."
    case "$PANEL" in
        cpanel)
            if [ -f '/etc/cpanel/ea4/is_ea4' ] ; then
                # modsec3 conflicts with mod_security2. Do not try to install
                # mod_security2 if modsec3 exists
                if ! check_${ostype}_pkg_presence ea-modsec30
                then
                    log echo "Installing mod_security2"
                    if [[ "$ostype" = "debian" ]]; then
                      # '-' (hyphen)
                      modsec_package=ea-apache24-mod-security2
                    else
                      # '_' (underscore)
                      modsec_package=ea-apache24-mod_security2
                    fi
                    log "install_${ostype}_pkgs" "$modsec_package"
                fi
            fi
            # "activate" Freemium license: just feature flag for now
            if [[ "${freemium}" = "true" ]]; then
                log echo "Creating Imunify Freemium feature flag"
                setup_imunify360_dir
                touch "/var/imunify360/myimunify-freemium.flag"
            fi

        ;;
        directadmin)
            pushd /usr/local/directadmin/custombuild/
            da_webserver="$(grep ^webserver= options.conf | sed s/webserver=//)"
            da_modsecurity="$(grep ^modsecurity= options.conf | sed s/modsecurity=//)"
            if [ "$da_webserver" != apache -a "$da_webserver" != litespeed ]
            then
                log echo "Imunify modsecurity ruleset is not supported for $da_webserver webserver."
            else
                if [ "$da_modsecurity" != yes ]; then
                    log echo "Installing DirectAdmin modsecurity..."
                    # create options.conf backup file before edit
                    # with name e.g. options.conf.bak_2018-03-29.1522323911
                    sed -i.bak_"$(date +%F.%s)" \
                    -e "s/^modsecurity=.*/modsecurity=yes/" \
                    -e "s/^modsecurity_ruleset=.*/modsecurity_ruleset=no/" options.conf
                    ./build modsecurity
                else
                    log echo "Installing DirectAdmin modsecurity... already installed!"
                fi
                modifying_call=true
            fi
            popd
        ;;
        generic)
        ;;
        plesk)
            if ! /usr/local/psa/bin/server_pref --show-web-app-firewall >/dev/null 2>&1 \
                || ! ls /usr/local/psa/admin/sbin/modsecurity_ctl >/dev/null 2>&1
            then
                # There appears to be a bug in Plesk - when installation is triggered via UI, using Plesk extension,
                # i360deploy process somehow receives a SIGTERM from `plesk installer` process.
                # See comments in https://cloudlinux.atlassian.net/browse/DEF-7450 for details.
                # TODO: re-check this bug after installation is re-worked in https://cloudlinux.atlassian.net/browse/DEF-9061
                if [ "$I360_FROM_PLESK_EXTENSION" != 1 ]; then
                    log echo "Installing mod_security"
                    log run_with_retries "plesk installer --select-release-current --install-component modsecurity" "BUSY: Update operation was locked by another update process" "true"
                fi
            fi
        ;;
    esac
fi


if [ "$first_install" = "true" ]; then
    log echo "In a few moments the script will install latest $package" \
        "package (w/dependencies)... (Ctrl-C to cancel)"
    sleep 4

    install_imunify_release

    if [[ $ostype = debian ]]; then
        # do apt update to be able to install new version of alt-common-release
        if ! log run_with_retries "apt-get update" ""; then
            test "$dev_install" = true
            check_exit_code 0 "apt-get update error."
        fi
    fi

    log install_${ostype}_pkgs alt-common-release
    if [[ $ostype = debian ]]; then
        if ! log run_with_retries "apt-get update" ""; then
            test "$dev_install" = true
            check_exit_code 0 "apt-get update error."
        fi
    fi


    if [ "$is_cloudways" = "true" ]; then
        disable_firewall
    fi


    package_version=$(get_available_${ostype}_package_version "$package")
    check_exit_code 0 "Failed to get package version"

    log install_${ostype}_pkgs $package
    rc=$?
    # try installing the config overrides regardless of the installation success
    log install_first_install_default_overrides "$package" "$package_version"

    webshield_module_supported && log install_apache_config "$package" "$package_version" || true
    if [[ "$package" = "$imunify360" ]]; then
        log set_low_resource_usage_mode_if_necessary "$package" "$package_version"
    fi

    # fail
    if [ $rc -ne 0 ]; then
        exit_with_error "Package $package $package_version was not installed."
    fi

    if [ "$is_cloudways" = "true" ]; then

        special_config_cloudways

        rapid_scan_basedir_override
    fi

    # Load the product's SELinux policy so imunify-notifier & friends work
    # on SELinux-enforcing hosts without manual semodule steps (DEF-36450).
    log apply_selinux_policy

    modifying_call=true
fi

log echo "Installing ui packages..."
case "$PANEL" in
    cpanel)
        log check_and_install "$package" "$package_version" "$UI_PACKAGE" "$PANEL"
        check_exit_code 0 "Failed to install $PRODUCT $PANEL plugin."
        modifying_call=true
        ;;
    directadmin)
        log check_and_install "$package" "$package_version" "$UI_PACKAGE" "$PANEL"
        check_exit_code 0 "Failed to install $PRODUCT $PANEL plugin."
        modifying_call=true
        ;;
    generic)
        log check_and_install "$package" "$package_version" "imunify-ui" "$PANEL"
        check_exit_code 0 "Failed to install $PRODUCT $PANEL plugin."
        modifying_call=true
        ;;
    plesk)
        log check_and_install "$package" "$package_version" "$UI_PACKAGE" "$PANEL"
        check_exit_code 0 "Failed to install $PRODUCT $PANEL plugin."

        if is_debian_like; then
            plugin_path="/var/imunify360/plesk/imunify-plugin.zip"
        else
            SYS_CONF_DIR="$(rpm --eval '%{_sysconfdir}')"
            plugin_path="$SYS_CONF_DIR/sysconfig/imunify360/plesk/imunify-plugin.zip"
        fi

        if [ -f "$plugin_path" ] && [ "$I360_FROM_PLESK_EXTENSION" != "1" ]; then
            log echo "Trying to install/upgrade Imunify360 Plesk extension..."
            SKIP_PREINSTALL_HOOK=true log /usr/local/psa/bin/extension --upgrade "$plugin_path" || true
        fi

        modifying_call=true
        ;;
    *)
        log echo "UI plugin is not installed."
        log echo "No supported hosted panel detected and $INTEGRATION_CONF_PATH file is missing."
        install_vendors=false
        ;;
esac

if [ "$conversion" = "true" ] ; then


    if [[ "$package" = "$imunify360" ]]; then

        # try to migrate the old patchman agent
        if [[ "$migrate_patchman" = "true" ]] ; then
            do_migrate_patchman
        fi

        if [ "$is_cloudways" != "true" ]; then
            log echo "Checking if has already been registered... "
            log imunify360-agent --console-log-level ERROR rstatus
            rstatus=$?
            if [ "$rstatus" = 11 ] ; then
                exit_with_error "Registration server general error."
            fi
            if [ "$rstatus" = 0 -a "$activationkey" != false ] ; then
                log echo "Unregister the previous registration key... "
                log imunify360-agent --console-log-level WARNING unregister
            fi
            if [ "$activationkey" != false ] ; then
                log echo "Register by key... "
                log imunify360-agent --console-log-level WARNING register "$activationkey"
                check_exit_code 0 "Registration was not successful. Exiting."
            elif [ "$rstatus" != 0 ] ; then
                # "$rstatus" != 0 check because it is no sense to re-register
                # by IP (in comparison with re-register by activation key)
                log echo "Register by IP... "
                log imunify360-agent --console-log-level WARNING register IPL
            fi
            if [[ $? != 0 ]]; then
                log echo "Registration was not successful."
            else
                log echo "Successfully registered"
            fi

            disable_3rd_party_ids
        fi

        if is_systemctl_avail; then
            log systemctl enable imunify360.service
            log systemctl start imunify360
        else
            log /sbin/chkconfig --add imunify360
            log /sbin/service imunify360 start
        fi
    fi


    check_exit_code 0 "Failed to start $package service."

    agent_start_success=false

    if [ "$is_cloudways" != "true" ]; then
        log echo "Waiting for $PRODUCT to start..."

        for i in {1..10}; do
            if log $COMMAND version
            then
                log echo "$PRODUCT is started"
                agent_start_success=true
                break
            else
                sleep 60
            fi
        done

        if ! $agent_start_success; then
            log echo "Something went wrong during $PRODUCT start up"
            exit_with_error "See /var/log/imunify360/error.log for details"
        fi

        if [[ "$package" = "$imunify360" ]]; then
            # agent is started
            #force-disable WebShield
            if [ "$PANEL" = "generic" ] ; then
                imunify360-agent config update '{"WEBSHIELD": {"enable": false}}'
            fi
            # turn on MyImunify
            if [[ "${freemium}" = "true" && "$PANEL" = "cpanel" ]]; then
                log echo "Turning on MyImunify"
                imunify360-agent config update '{"MY_IMUNIFY": {"enable": true}}'
            fi
        fi
        if [ "$install_vendors" = "true" ]; then
            /usr/bin/imunify360-agent --console-log-level=WARNING install-vendors
        fi
    else
        install_vendors_in_cw_environment >/dev/null &
        disown

    fi
elif ! $COMMAND rstatus >/dev/null 2>&1
then
    log echo "You have to register this software with registration key:"
    log echo "  $script --key <key>"
fi

if $modifying_call; then
    log echo "Success"
    log echo "You can find complete log in $LOG_FILE"
fi
exit 0
