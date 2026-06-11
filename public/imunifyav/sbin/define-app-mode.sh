#!/bin/bash
# We check if the file /var/imunify360/.i360 exists and if the status of the agent is OK.
# If both conditions are met, we change the IMUNIFY_PACKAGE variable in the config.js file to '360' to show the Imunify360 UI.
# Otherwise, we change the IMUNIFY_PACKAGE variable to 'AV' to show the ImunifyAV UI.

agent_bin="/usr/bin/imunify360-agent"
i360_installed_marker="/var/imunify360/.i360"
config_js_file="/usr/local/psa/admin/htdocs/modules/imunify360/assets/js/config.js"

output=$(ps ax)
is_i360_running=$(echo "$output" | grep -q "i360deploy.sh"; echo $?)
is_imav_running=$(echo "$output" | grep -q "imav-deploy.sh"; echo $?)

if [[ ! -f $agent_bin ]]; then
    echo "The imunify360-agent binary does not exist. Skipping."
    exit 0
fi

if [[ ! -f $config_js_file ]]; then
    echo "The config.js file does not exist. Skipping."
    exit 0
fi

if [[ "$is_i360_running" -eq 0 ]] || [[ "$is_imav_running" -eq 0 ]]; then
    echo "Imunify360 or ImunifyAV is already running. Skipping."
    exit 0
fi

status=$(/usr/bin/imunify360-agent rstatus)

if [[ -f $i360_installed_marker && "$status" == "OK" ]]; then
    if ! grep -q "IMUNIFY_PACKAGE = '360'" $config_js_file; then
        echo "Imunify360 is installed and the agent status is OK. Changing the UI to Imunify360."
        sed -i -E "s/IMUNIFY_PACKAGE = 'AV'/IMUNIFY_PACKAGE = '360'/" $config_js_file
    else
        echo "IMUNIFY_PACKAGE is already set to '360'. No changes made."
    fi
else
    if ! grep -q "IMUNIFY_PACKAGE = 'AV'" $config_js_file; then
        echo "Imunify360 is not installed or the agent status is not OK. Changing the UI to ImunifyAV."
        sed -i -E "s/IMUNIFY_PACKAGE = '360'/IMUNIFY_PACKAGE = 'AV'/" $config_js_file
    else
        echo "IMUNIFY_PACKAGE is already set to 'AV'. No changes made."
    fi
fi