#!/bin/bash
# SOFTI-MEJORA: publicar assets JS/CSS tras editar */static/*
# LiteSpeed (lscpd) sirve desde public/static/, NO desde dns/static/ ni static/ directo.
set -e
cd /usr/local/CyberCP
/usr/local/CyberCP/bin/python manage.py collectstatic --noinput
cp -R /usr/local/CyberCP/static/* /usr/local/CyberCP/public/static/
echo "OK: static synced to public/static"
