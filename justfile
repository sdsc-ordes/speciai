set positional-arguments
set shell := ["bash", "-cue"]
set dotenv-load
root_dir := `git rev-parse --show-toplevel`
flake_dir := root_dir / "tools/nix"
output_dir := root_dir / ".output"
build_dir := output_dir / "build"

[group('modules')]
mod external "./tools/just/external.just"
[group('modules')]
mod nix "./tools/just/nix.just"
[group('modules')]
mod sops "./tools/just/sops.just"
[group('modules')]
mod image "./tools/just/image.just"

# Default target if you do not specify a target.
default:
    just --list --unsorted

# Enter the default Nix development shell and execute the command `"$@`.
[group('tooling')]
develop *args:
    just nix::develop "default" "$@"

# Format the project.
format *args:
    treefmt "$@"

# Setup the project.
[group('tooling')]
setup *args: external::fetch
    cd "{{root_dir}}" \
      && uv sync \
      && prek install \
      && bash tools/scripts/setup-config-files.sh

# Run commands over the ci development shell.
[group('tooling')]
ci *args:
    just nix::develop "ci" "$@"

# Lint the project.
[group('tooling')]
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
    uv run --all-groups --all-extras speciai "$@"
