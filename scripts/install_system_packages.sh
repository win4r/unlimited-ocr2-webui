#!/usr/bin/env bash
set -euo pipefail
# Keep the existing NVIDIA driver. Runtime CUDA 13 is installed in the venv.
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential ffmpeg ca-certificates curl unzip python3-pip python3-venv ufw
# Cloud images may point gcc at GCC 12 while build-essential installs G++ 11.
UOCR_GCC_MAJOR="$(gcc -dumpversion | cut -d. -f1)"
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "g++-$UOCR_GCC_MAJOR"
