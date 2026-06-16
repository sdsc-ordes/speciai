#!/usr/bin/env bash
git config --global safe.directory "*" || {
    echo "Could not overwrite safe.directory in Git config." >&2
    exit 1
}
git config --global user.name "SDSC CI"
git config --global user.email "ci@sdsc.ethz.ch"
