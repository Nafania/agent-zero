#!/bin/bash
set -e

# Install Chromium and required system libraries for headless browser automation.
# browser-use 0.12+ uses CDP (Chrome DevTools Protocol) directly — no Playwright needed.

apt-get update
apt-get install -y --no-install-recommends \
    chromium \
    fonts-unifont \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libatk-bridge2.0-0 \
    libcups2
apt-get clean
rm -rf /var/lib/apt/lists/*
