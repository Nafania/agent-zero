#!/bin/bash
set -e

. "/ins/setup_venv.sh"

uv pip install -r /git/agent-zero/requirements.txt
uv pip install -r /git/agent-zero/requirements2.txt

bash /ins/install_chrome.sh
