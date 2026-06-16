root_dir := `git rev-parse --show-toplevel`
set shell := ["bash", "-cue"]

# Default recipe to list all recipes.
[private]
default:
    just --list external

# Fetch external files.
fetch:
  cd {{root_dir}} && \
    vendir sync --locked -f vendir.yaml --chdir external

# Update external manifests to their latest version.
[confirm("Update external files? [y/n]")]
refresh:
  cd {{root_dir}} && \
    vendir sync -f vendir.yaml --chdir external
