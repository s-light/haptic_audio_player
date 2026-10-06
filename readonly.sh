#!/bin/sh
# Remount / read-only again after ./readwrite.sh (hard-shut-off safe).
set -eu
sync
sudo mount -o remount,ro /
mount | grep ' / '
