#!/bin/bash
set -e

bash /ins/install_A0.sh

. "/ins/setup_venv.sh"
pip cache purge
uv cache prune
