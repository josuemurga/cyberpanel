#!/bin/bash
source /etc/os-release
if [ "$ID" == "ubuntu" ] || [ "$ID" == "debian" ]; then
	wget -qO- https://repo.imunify360.cloudlinux.com/defense360/RPM-GPG-KEY-CloudLinux | gpg --dearmor > /etc/apt/trusted.gpg.d/RPM-GPG-KEY-CloudLinux.gpg
fi
if [ "$ID" != "ubuntu" ] || [ "$VERSION_ID" != "24.04" ]; then
    echo "This script is intended for Ubuntu 24.04 only."
    exit 0
fi
mkdir -p /etc/apt/apt.conf.d
echo 'APT::Key::Assert-Pubkey-Algo ">=rsa2048,ed25519,ed448,dsa1024";' > /etc/apt/apt.conf.d/99-imunify-repo-warning
