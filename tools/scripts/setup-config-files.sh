#!/usr/bin/env bash
# shellcheck disable=SC1091

set -e
set -u

ROOT_DIR=$(git rev-parse --show-toplevel)
. "$ROOT_DIR/tools/ci/general.sh"

function main() {
    cd "$ROOT_DIR"

    # link config files to the root directory.

    ci::print_info "Linking configs files to root '$ROOT_DIR'."

    rm -rf ".prettierrc.yaml" || true
    ln -s "tools/configs/prettier/prettierrc.yaml" ".prettierrc.yaml"

    rm -rf ".typos.toml" || true
    ln -s "tools/configs/typos/typos.toml" ".typos.toml"

    rm -rf ".yamllint.yaml" || true
    ln -s "tools/configs/yamllint/yamllint.yaml" ".yamllint.yaml"

    rm -rf ".pre-commit-config.yaml" || true
    ln -s "tools/configs/prek/pre-commit-config.yaml" ".pre-commit-config.yaml"

}

main "$@"
