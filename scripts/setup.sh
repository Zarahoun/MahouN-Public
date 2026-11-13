#!/bin/bash

# Variables
XRAY_URL="https://tools.haiocloud.com/xray"
XRAY_DIR="/usr/local/xray"
CONFIG_DIR="/etc/haio"
SERVICE_FILE="/etc/systemd/system/haiogateway.service"
CONFIG_FILE="$CONFIG_DIR/config.json"
DOMAINS_FILE="$CONFIG_DIR/domains.txt"
REMOTE_DOMAINS_URL="https://tools.haiocloud.com/domains.txt"

# Prompt for password
read -sp "Enter the password for the Trojan protocol: " TROJAN_PASSWORD
echo

# Create xray and config directories
mkdir -p $XRAY_DIR
mkdir -p $CONFIG_DIR

# Download Xray executable if it doesn't exist or is outdated
if [ -f "$XRAY_DIR/xray" ]; then
    LOCAL_XRAY_HASH=$(sha256sum $XRAY_DIR/xray | awk '{ print $1 }')
    REMOTE_XRAY_HASH=$(curl -L $XRAY_URL | sha256sum | awk '{ print $1 }')

    if [ "$LOCAL_XRAY_HASH" != "$REMOTE_XRAY_HASH" ]; then
        echo "Updating Xray binary..."
        curl -L $XRAY_URL -o $XRAY_DIR/xray
        chmod +x $XRAY_DIR/xray
    else
        echo "Xray binary is up to date."
    fi
else
    echo "Downloading Xray binary..."
    curl -L $XRAY_URL -o $XRAY_DIR/xray
    chmod +x $XRAY_DIR/xray
fi

# Download domains.txt from tools.haiocloud.com and save locally
curl -L $REMOTE_DOMAINS_URL -o $DOMAINS_FILE

# Read domains from the downloaded file and format them as a plain list with each domain in double quotes
DOMAINS_LIST=$(awk 'NR > 1 { print line "," } { line = "\"" $0 "\"" } END { print line }' $DOMAINS_FILE)

# Create configuration file with initial settings and include the domains list
cat << EOF > $CONFIG_FILE
{
    "log": {
        "loglevel": "warning"
    },
    "inbounds": [
        {
            "port": 10800,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {
                "udp": true
            }
        },
        {
            "listen": "0.0.0.0",
            "port": 8889,
            "protocol": "http",
            "settings": {
                "allowTransparent": true,
                "timeout": 300
            },
            "sniffing": {
            },
            "tag": "http_IN"
        }
    ],
    "outbounds": [
        {
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": "tahrim.haiocloud.com",
                        "port": 443,
                        "password": "$TROJAN_PASSWORD"
                    }
                ]
            },
            "tag" : "proxy",
            "streamSettings": {
                "network": "tcp",
                "security": "tls"
            }
        },
        {
          "protocol": "freedom",
          "settings": {},
          "tag": "direct"
        }

    ],
    "routing": {
        "domainMatcher": "mph",
        "domainStrategy": "AsIs",
        "rules": [
            {
                "domain": [
                    $(echo -e $DOMAINS_LIST)
                ],
                "outboundTag": "proxy",
                "type": "field"
            },
            {
                "domain": [
                    "."
                ],
                "outboundTag": "direct",
                "type": "field"
            },
            {
                "ip": [
                         "0.0.0.0/0",
                         "::/0"
                ],
                "outboundTag": "direct",
                "type": "field"
            }

        ]
    }
    
}

EOF

# Create systemd service file
cat << EOF > $SERVICE_FILE
[Unit]
Description=HaioGateWay Service
After=network.target

[Service]
Type=simple
ExecStart=$XRAY_DIR/xray -config $CONFIG_FILE
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable xray service
systemctl daemon-reload
systemctl enable haiogateway
systemctl start haiogateway

echo "Haio GateWay installation and configuration complete. The service is named haiogateway."
