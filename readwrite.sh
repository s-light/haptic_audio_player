#!/bin/sh
# Temporarily remount / read-write (git pull, setup steps, config edits) on a board that went through
# `./setup_pb2.py readonly-root`. Pair with ./readonly.sh when done. The data partition is unaffected.
set -eu
sudo mount -o remount,rw /
mount | grep ' / '
