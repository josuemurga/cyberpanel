#!/bin/bash

## i360deploy/av-deploy INFO
# Short Description :Deploy imunify360/ImunifyAV UI
# Description       :Installs imunify360/ImunifyAV UI
# Copyright         :Cloud Linux Zug GmbH
# License           :Cloud Linux Commercial License

set -e # exit on error

readonly CPANEL_ADMIN_PATH="/usr/local/cpanel/whostmgr/docroot/cgi/imunify"
readonly CPANEL_CLIENT_PATH="/usr/local/cpanel/base/frontend"
readonly DA_PATH="/usr/local/directadmin/plugins/Imunify/images"
readonly GENERIC_PATH="$PWD"
readonly PLESK_PATH="/usr/local/psa/admin/htdocs/modules/imunify360"

exit_with_error()
{
    echo "$@"
    exit 1
}

log()
{
    echo "$@"
}

detect_panel ()
{
    readonly CPANEL_BIN="/usr/local/cpanel/cpanel"
    readonly DA_BIN="/usr/local/directadmin/directadmin"
    readonly PLESK_BIN="/usr/sbin/plesk"
    readonly INTEGRATION_CONF_PATH="/etc/sysconfig/imunify360/integration.conf"

    PANEL=""
    if [ -f "$INTEGRATION_CONF_PATH" ] ; then
        PANEL="generic"
    elif [ -f "$PLESK_BIN" ]; then
        PANEL="plesk"
    elif [ -f "$CPANEL_BIN" ]; then
        PANEL="cpanel"
    elif [ -f "$DA_BIN" ]; then
        PANEL="directadmin"
    else
        exit_with_error "No panel was detected."
    fi
    log "$PANEL panel was detected."
}

detect_path()
{
    PANEL_PATH=""
    if [[ $PANEL = "generic" ]] ; then
        PANEL_PATH=$GENERIC_PATH
    elif [[ $PANEL = "plesk" ]]; then
        PANEL_PATH=$PLESK_PATH
    elif [[ $PANEL = "cpanel" ]]; then
        PANEL_PATH=$CPANEL_ADMIN_PATH
    elif [[ $PANEL = "directadmin" ]]; then
        PANEL_PATH=$DA_PATH
    fi
}

print_help ()
{
    cat << EOF >&2
Usage:

  -h, --help            Print this message
  -c, --uninstall       Uninstall Imunify UI
  -i, --install         Install Imunify UI (the default)
  -b, --build <mode>    Build module: [dev|prod|e2e-test]
  -m, --module <module> Module name: [shared|nav-root|email-root|other-root]
  -s, --skip-npm        Don't install and remove node_modules
EOF
}

build_module()
{

    log 'build_module';
    if [ -z $NODE_PATH ]; then
        log "NODE_PATH is not set using system node"
    else
        ls -l $NODE_PATH
        export PATH=$NODE_PATH:$PATH
    fi
    if [[ "$SKIP_NPM" != "true" ]]; then
        log "npm install attempt";
        set -x
        which npm
        which node
        npm config ls -l
        npm install --omit=dev --omit=optional --no-progress 2>&1
        set +x
    fi

    set_ui_version

    log "building '${spa_to_build}' for module ${module}"
    for spa in $spa_to_build; do
        log "building spa ${spa}"
        log "npm build";
        npm run "build:${mode}:${spa}" 2>&1
    done

    set +x
    if [[ "$module" == "core" ]]; then
        node ./ci-utils/collect-shared-deps.js "${mode}"
        npm run convert-vendors

        copy_spa_root ../../ui/agent/plugins/common/assets/static
        node ./ci-utils/create-importmap-hashes.js "../../ui/agent/plugins/common/assets/static"
    fi

    if [[ "$SKIP_NPM" != "true" ]]; then
        rm -rf node_modules
    fi
}

set_ui_version()
{
    local SPEC_FILE_PATH="../../../../imunify-ui.spec"

    local version
    # Extract the version number from spec file
    version=$(grep "^Version:" "$SPEC_FILE_PATH" | awk '{print $2}')
    release=$(grep "^Release:" "$SPEC_FILE_PATH" | awk '{print $2}')

    export VERSION="$version"
    export RELEASE="$release"
    node -e "console.log(process.env.VERSION)"
    node -e "console.log(process.env.RELEASE)"
}

copy_files()
{
    for spa in $spa_to_build; do
        rm -rf "${1:?}/${spa}"
        mkdir -p "${1}/${spa}"
        FROM="${PANEL_PATH}/brought_by_package_manager"
        log "copying module ${spa} from ${FROM} to ${1}"
        cp -a "$FROM/${spa}" "${1}"
    done

    if [[ "$module" == "core" ]]; then
        copy_spa_root "${1}"
    fi
}

copy_spa_root()
{
    if [[ -d "../../ui/agent/plugins/common/assets/static/" ]]; then
        # when we build packages
        FROM="single-spa-root"
    else
        # when we install packages
        FROM="brought_by_package_manager"
        cp "$FROM/importmap.json" "${1}/"
        copy_dir "$FROM/fonts" "${1}/fonts"
    fi
    log "copying spa root from ${FROM}/ to ${1}/"
    cp "$FROM/index.js" "${1}/"
    cp "$FROM/systemjs-conflict-patch-pre.js" "${1}/"
    cp "$FROM/systemjs-conflict-patch-post.js" "${1}/"
    cp "$FROM/load-scripts-after-zone.js" "${1}/"
    cp "$FROM/container.css" "${1}/"

    copy_dir "$FROM/shared-dependencies" "${1}/shared-dependencies"
}

copy_dir() {
    local FROM_DIR=$1
    local TO_DIR=$2

    if [ -d "$TO_DIR" ]; then
        rm -rf "$TO_DIR"
    fi

    mkdir -p "$TO_DIR"
    log "copying files from $FROM_DIR to $TO_DIR"
    cp -r "$FROM_DIR/"* "$TO_DIR/"
}

cpanel_theme_loop()
{
    for theme in $(find ${CPANEL_CLIENT_PATH} -maxdepth 1 -type d | sed "s|${CPANEL_CLIENT_PATH}||g" | sed 's/^\///')
    do
        log "theme $theme"
        if [[ "$action" = "install" ]]; then
            mkdir -p "${CPANEL_CLIENT_PATH}${theme}/imunify"
            if [[ "$module" == "core" ]]; then
                copy_files "${CPANEL_CLIENT_PATH}/${theme}/imunify/assets/static"
            fi
        fi

        if [ "$action" = "uninstall" ]; then
            for spa in $spa_to_build; do
                rm -rf "${CPANEL_CLIENT_PATH}/${theme}/imunify/assets/static/${spa}"
            done
        fi
    done
}

### Lets start

# if environment has umask=0000 (if called from plesk extension), all created files have -rw-rw-rw- permission
umask 0022

options=$(getopt -o chidb:m:s -l "uninstall,help,install,build:,module:,skip-npm" -- "$@")
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
        -c|--uninstall)
            action="uninstall"
            shift
        ;;
        -b|--build)
            action="build"
            mode="$2"
            shift 2
        ;;
        -s|--skip-npm)
            SKIP_NPM="true"
            shift
        ;;
        -i|--install)
            action="install"
            shift
        ;;
        -m|--module)
            module="$2"
            shift 2
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

### logic

if [ "$action" != "uninstall" ] && [ "$action" != "build" ]; then
    action="install"
fi

if [[ "$module" != "nav-root" ]] && [[ "$module" != "other-root" ]] && [[ "$module" != "email-root" ]] && [[ "$module" != "core" ]]; then
    echo "$module - wrong module"
    exit 1
fi


if [[ "$module" == "core" ]]; then
    spa_to_build="nav-root other-root"
else
    spa_to_build="$module"
fi

if [[ "$action" = "build" ]]; then
    build_module
    exit 0
fi

detect_panel
detect_path

if [[ "$action" = "uninstall" ]]; then
    for spa in $spa_to_build; do
        rm -rf "${PANEL_PATH}/assets/static/${spa}"
    done
    exit 0
fi

if [[ "$action" = "install" ]]; then
    if [[ $PANEL = "plesk" ]] && [[ -d "/usr/share/imunify360/ui-plugin/" ]]; then
        # Update plugin index files
        mv "/usr/share/imunify360/ui-plugin/plib/views/scripts/index/index.phtml" "/usr/local/psa/admin/plib/modules/imunify360/views/scripts/index/"
        mv "/usr/share/imunify360/ui-plugin/plib/views/scripts/client/index.phtml" "/usr/local/psa/admin/plib/modules/imunify360/views/scripts/client/"

        # Update brought_by_package_manager files
        if [[ -d "/usr/local/psa/admin/htdocs/modules/imunify360/brought_by_package_manager" ]]; then
            rm -rf "/usr/local/psa/admin/htdocs/modules/imunify360/brought_by_package_manager"
        fi
        mv "/usr/share/imunify360/ui-plugin/htdocs/brought_by_package_manager/" "/usr/local/psa/admin/htdocs/modules/imunify360/brought_by_package_manager"
    fi
    copy_files ${PANEL_PATH}/assets/static
    if [[ $PANEL = "cpanel" ]]; then
        cpanel_theme_loop
    fi
    if [[ $PANEL = "directadmin" ]]; then
        chown -R diradmin:diradmin ${PANEL_PATH}/assets
    fi
    if [[ $PANEL = "generic" ]]; then
        if grep -q 'ui_path_owner = imav:imav' "$INTEGRATION_CONF_PATH" ; then
            chown -R imav:imav ${PANEL_PATH}/assets
        fi
    fi
    # set firewall disabled in config
    is_firewall_disabled=$( [ -f "/var/imunify360/firewall_disabled" ] && echo 'true' || echo 'false' )
    if [ "${is_firewall_disabled}" = "true" ]; then
        echo "var IMUNIFY_FIREWALL_DISABLED=${is_firewall_disabled};" >> "${PANEL_PATH}/assets/js/config.js"
    fi
    exit 0
fi

exit 0
