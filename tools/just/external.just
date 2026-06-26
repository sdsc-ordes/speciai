root_dir := `git rev-parse --show-toplevel`
set positional-arguments
set shell := ["bash", "-cue"]

# Default recipe to list all recipes.
[private]
default:
    just --list external

# Fetch vendored assets based on lockfile.
fetch: (upgrade "--locked")

# Update vendored assets to their latest version.
upgrade *args:
  cd {{root_dir}} && \
    vendir sync \
      --chdir "external/" "$@"
