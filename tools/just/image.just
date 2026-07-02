root_dir := `git rev-parse --show-toplevel`
set positional-arguments
set shell := ["bash", "-cue"]

# Container engine: podman by default, override with `just image::build docker`.
engine := env("CONTAINER_ENGINE", "podman")

# Default recipe to list all recipes.
[private]
default:
    just --list image

# Build the web server image.
build *args:
  cd "{{root_dir}}" && \
    {{engine}} build -f tools/images/Containerfile -t speciai:latest "$@" .

# Run the web server via compose (`up`), pass e.g. `-d` to detach.
serve *args:
  cd "{{root_dir}}" && \
    {{engine}} compose up "$@"
