#!/bin/bash

scriptname="i360deploy-plesk"
log=/var/log/$scriptname.log
sign='/var/imunify360/plesk-ext-marketplace'
# set -x
# exec >> $log 2>&1


if_not_locked() {
    # this lock is acquired during installation of imunify360-firewall-plesk rpm-package
    # check it to prevent running "yum install/update" the second time,
    # but do not acquire it here to allow updating the extension via yum along with related rpm-packages
    if flock -n /var/lock/imunify360-plesk-installation.lock true; then
        $@
    else
        echo 'Imunify360-firewall (un)installation is done in another process' | tee -a $log;
        exit 0
    fi
}

print_help ()
{
    cat << EOF >&2
Usage:

  -h, --help                    Print this message
  -i, --install <360|AV|CORE>   Install Imunify360/AV. Accept 360|AV|CORE. Default value is AV
  -u, --uninstall               Uninstall Imunify360 Agent
  -k, --key                     Register with key
  -c, --check                   Check requirements
  -d, --downgrade               Downgrade from Imunify360 to ImunifyAV
EOF
}

background_run()
{
    $@ &>/dev/null &
}

wait_for_file()
{
  file_path=$1
  max_iterations=30

  # Loop with a counter
  iteration=1
  while [ $iteration -le $max_iterations ]; do
     if [ -s "$file_path" ]; then
         break
     fi

     ((iteration++))
     sleep 1 # Adjust the interval as needed (in seconds)
  done

  # Check if the file was found or timeout occurred
  if [ ! -s "$file_path" ]; then
      echo "Timeout: $file_path not filled within $max_iterations seconds."
      exit 1
  fi
}

run_i360deploy()
{
    # see https://docs.imunify360.com/installation/
    I360_FROM_PLESK_EXTENSION=1 flock /var/lock/imunify360-plesk-i360deploy.lock \
        bash -x /usr/local/psa/admin/sbin/modules/imunify360/i360deploy.sh -y $@ | tee -a $log;
}

uninstall()
{
    background_run run_i360deploy --uninstall --skip-version-check
    wait_for_file $log
}

downgrade()
{
    background_run run_i360deploy --downgrade --skip-version-check
    wait_for_file $log
}

add_from_marketplace_sign()
{
    if [ ! -f /usr/bin/imunify360-agent ]; then  # fresh installation
        # mark as installed via extension
        mkdir -p -m 0755 /var/imunify360
        touch $sign
    fi
}
remove_from_marketplace_sign()
{
    rm -f $sign
}

add_ui_static()
{
    local supported_plugins=("360" "AV" "CORE")
    local plugin="$1"
    local is_supported=false

    for p in "${supported_plugins[@]}"; do
        if [[ "$p" == "$plugin" ]]; then
            is_supported=true
            break
        fi
    done

    if [[ "$is_supported" == false ]]; then
        echo "Error: Unsupported plugin '$plugin'"
        exit 1
    fi

    cd /usr/local/psa/admin/htdocs/modules/imunify360
    chmod +x i360deploy-ui.sh
    ./i360deploy-ui.sh --module core

    if [[ "$plugin" == "AV" && -f "$sign" ]]; then
      sed -i -E "s/IMUNIFY_PACKAGE = '360'/IMUNIFY_PACKAGE = 'AV'/" \
      /usr/local/psa/admin/htdocs/modules/imunify360/assets/js/config.js
    fi

    if [[ "$plugin" == "360" && -f "$sign" ]]; then
      sed -i -E "s/IMUNIFY_PACKAGE = 'AV'/IMUNIFY_PACKAGE = '360'/" \
      /usr/local/psa/admin/htdocs/modules/imunify360/assets/js/config.js
    fi
    cd -
}

options=`getopt -o i:urdschb: -l install,uninstall,downgrade,background,help,check: -- "$@"`

if [ $? != 0 ] ; then print_help ; exit 1 ; fi

eval set -- "$options"

# Default value for install parameter
plugin="AV"
while [[ "$#" -gt 0 ]]; do
    case "$1" in
    -h|--help)
    print_help
    shift
    ;;
    -u|--uninstall)
    remove_from_marketplace_sign
    if_not_locked uninstall
    shift
    ;;
    -d|--downgrade)
    remove_from_marketplace_sign
    if_not_locked downgrade
    shift
    ;;
    -i|--install)
    if [[ -n "$2" && "$2" != -* ]]; then
        plugin="$2"
        shift
    fi
    add_from_marketplace_sign
    add_ui_static "$plugin"
    shift
    ;;
    --)
    shift
    break
    ;;
    -*)
    echo "$0: error - unrecognized option $1" 1>&2
    exit 1
    ;;
     *) echo "Internal error!"; exit 1;;
    esac
done
