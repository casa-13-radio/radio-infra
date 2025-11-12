#!/bin/bash
set -e

source .env

sed -e "s|__ICECAST_SOURCE_PASSWORD__|$ICECAST_SOURCE_PASSWORD|g" \
    -e "s|__ICECAST_RELAY_PASSWORD__|$ICECAST_RELAY_PASSWORD|g" \
    -e "s|__ICECAST_ADMIN_USER__|$ICECAST_ADMIN_USER|g" \
    -e "s|__ICECAST_ADMIN_PASSWORD__|$ICECAST_ADMIN_PASSWORD|g" \
    icecast.xml.template > icecast.xml

echo "✅ icecast.xml gerado!"