#!/bin/bash
# Manage imunify360 services on Plesk extension enable/disable.
# Called from post-change-status.php via pm_ApiCli::callSbin().

set -o pipefail

ACTION="$1"
STATE_FILE="/var/imunify360/plesk-enabled-services.state"

if [ "$ACTION" = "enable" ]; then
    if [ ! -f "$STATE_FILE" ]; then
        echo "No saved service state found, starting core services"
        systemctl enable --now imunify360.service imunify360-agent.socket 2>&1
    else
        units=$(cat "$STATE_FILE")
        if [ -n "$units" ]; then
            echo "Restoring services: $units"
            # shellcheck disable=SC2086
            systemctl enable --now $units 2>&1
        fi
        rm -f "$STATE_FILE"
    fi
elif [ "$ACTION" = "disable" ]; then
    # Collect currently enabled imunify units, excluding imunify-antivirus (ImunifyAV)
    units=$(systemctl list-unit-files --state=enabled --no-legend --no-pager 'imunify*' 2>/dev/null \
        | awk '{print $1}' \
        | grep -v 'imunify-antivirus')

    if [ -n "$units" ]; then
        echo "Saving state and disabling: $units"
        echo "$units" > "$STATE_FILE"
        # shellcheck disable=SC2086
        systemctl disable --now $units 2>&1
    fi
else
    echo "Usage: manage-services.sh {enable|disable}" >&2
    exit 1
fi
