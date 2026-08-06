# RFHound — container image.
#
# Receive-first RF situational-awareness console. By default this runs the web
# dashboard in SIMULATE mode (no hardware) so `docker run` works anywhere.
#
# For real hardware, pass the HackRF through and drop simulate:
#   docker build -t rfhound .
#   docker run --rm -p 8000:8000 \
#       --device=/dev/bus/usb \
#       rfhound web --host 0.0.0.0 --token
#
# The image bundles hackrf + rtl-433 so it can drive real captures; install
# additional decoders (dump1090, AIS-catcher, …) in a derived image as needed.
FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="RFHound" \
      org.opencontainers.image.description="Receive-first HackRF RF situational-awareness & defensive-SIGINT console" \
      org.opencontainers.image.source="https://github.com/jawaman14/rfhound" \
      org.opencontainers.image.licenses="MIT"

# SDR tools RFHound orchestrates (optional at runtime, handy to have baked in).
RUN apt-get update \
    && apt-get install -y --no-install-recommends hackrf rtl-433 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

# Run as a non-root user; add to plugdev so a passed-through HackRF is usable.
RUN useradd --create-home --shell /usr/sbin/nologin rfhound \
    && usermod -aG plugdev rfhound || true
USER rfhound
ENV RFHOUND_HOME=/home/rfhound
VOLUME ["/home/rfhound/.config/rfhound", "/home/rfhound/rfhound-captures"]

EXPOSE 8000
ENTRYPOINT ["rfhound"]
# Safe default: receive-only dashboard, simulate mode, bound to all interfaces.
CMD ["web", "--host", "0.0.0.0", "--simulate"]
