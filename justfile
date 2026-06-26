set positional-arguments
set shell := ["bash", "-cue"]
set dotenv-load
root_dir := `git rev-parse --show-toplevel`
flake_dir := root_dir / "tools/nix"
output_dir := root_dir / ".output"
build_dir := output_dir / "build"

mod external "./tools/just/external.just"
mod nix "./tools/just/nix.just"
mod sops "./tools/just/sops.just"

# Default target if you do not specify a target.
default:
    just --list --unsorted

# Enter the default Nix development shell and execute the command `"$@`.
develop *args:
    just nix::develop "default" "$@"

# Format the project.
format *args:
    "{{root_dir}}/tools/scripts/setup-config-files.sh"
    just develop -- treefmt "$@"

# Setup the project.
setup *args: external-fetch
    cd "{{root_dir}}" \
      && uv sync \
      && prek install \
      && bash tools/scripts/setup-config-files.sh

# Pull latest version matching the ref (`main`)
external-upgrade *args:
    vendir sync \
        --chdir "{{root_dir}}/external/" "$@"

# Pull exact reference from lockfile
external-fetch: (external-upgrade "--locked")

# Run commands over the ci development shell.
ci *args:
    just nix::develop "ci" "$@"

# Lint the project.
[group('general')]
lint *args:
    ruff check

# Build the project.
[group('general')]
build *args:
    uv build --out-dir "{{build_dir}}" "$@"

# Generate the Darwin Core JSON Schema artifact (pass --check to verify only).
[group('general')]
gen-schema *args:
    uv run python -m speciai.generate_schema "$@"

# Test the project.
[group('general')]
test *args:
   uv run pytest "$@"

# Run an executable.
[group('general')]
run *args:
    uv run speciai "$@"

# Run the Jupyter notebook.
[group('general')]
notebook *args:
    uv run python -m notebook "$@"
