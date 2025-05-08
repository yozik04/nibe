#!/bin/bash

set -ex

# Change to the script's directory
cd "$(dirname "$0")"

# Mark the Git repository as safe to fix ambiguous ownership errors in container
git config --global --add safe.directory "$(realpath ../..)"

# Install Python dependencies
pip install -r ../../requirements.txt

# Install pre-commit hooks
pre-commit install
