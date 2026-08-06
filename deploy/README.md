# Deploying RFHound (unattended sensor node)

RFHound is receive-first — none of these deployments can transmit. For a network
deployment, always require a dashboard token.

## Docker

```bash
docker build -t rfhound .

# Dashboard, simulate mode (no hardware), anywhere:
docker run --rm -p 8000:8000 rfhound

# With a real HackRF and a required token:
docker run --rm -p 8000:8000 --device=/dev/bus/usb \
    rfhound web --host 0.0.0.0 --token my-secret

# Dashboard + hub together:
docker compose up -d
```

The image bundles `hackrf` and `rtl-433`; derive from it to add more decoders
(`dump1090`, `AIS-catcher`, …).

## systemd (bare-metal sensor)

```bash
# One-time: a service user, the tool, and an env file with the token.
sudo useradd --create-home --shell /usr/sbin/nologin --groups plugdev rfhound
sudo pip install rfhound            # or: pip install . from a checkout
sudo mkdir -p /etc/rfhound
sudo cp deploy/rfhound.env.example /etc/rfhound/rfhound.env   # then edit the token

sudo cp deploy/rfhound-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rfhound-web       # dashboard + REST API
sudo systemctl enable --now rfhound-hub       # multi-node aggregator (optional)
sudo systemctl enable --now rfhound-automate  # scheduled tasks + alerts (optional)
```

Define the scheduled tasks the automation scheduler runs, first:

```bash
sudo -u rfhound rfhound automate add survey recon --interval 300 --alert-on change
sudo -u rfhound rfhound automate add gpsmon gnss --param file=/var/lib/rfhound/gnss.json \
    --interval 60 --email soc@example.com
```

The units are hardened (`NoNewPrivileges`, `ProtectSystem=strict`,
`ProtectHome`, `PrivateTmp`) and restart on failure.
