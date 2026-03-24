#!/bin/bash
set -e

. "/ins/setup_venv.sh"

# HACK: litellm was pulled from PyPI due to supply-chain attack (2026-03-24).
# --find-links points to a vendored safe wheel. Remove once litellm is back on PyPI.
uv pip install -r /git/agent-zero/requirements.txt --find-links /git/agent-zero/vendor/
uv pip install -r /git/agent-zero/requirements2.txt --find-links /git/agent-zero/vendor/

bash /ins/install_chrome.sh
