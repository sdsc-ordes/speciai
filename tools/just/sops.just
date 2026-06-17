set positional-arguments
set shell := ["bash", "-cue"]

root_dir := `git rev-parse --show-toplevel`
current_dir := source_directory()

ENC_SUFFIX := ".sops"
DEC_SUFFIX := ".dec"

# Default recipe to list all recipes.
[private]
default:
    just --list sops

# Run any sops command
[no-cd]
run *args:
    #!/usr/bin/env bash
    set -eu -o pipefail

    echo "Using 'SOPS_AGE_KEY=decrypted($PROTECTED_SOPS_AGE_KEY_FILE)'" >&2
    export SOPS_AGE_KEY="$(age -d "$PROTECTED_SOPS_AGE_KEY_FILE")" || {
        echo "Could not password decrypt file '$PROTECTED_SOPS_AGE_KEY_FILE'." >&2
        return 1
    }
    sops "$@"

# Create key file to use with sops.
generate-key path:
    #!/usr/bin/env bash
    set -eu -o pipefail
    . "{{root_dir}}/tools/ci/general.sh"

    if [ -f "{{path}}" ]; then
        ci::die "File '{{path}}' already exists."
    fi

    ci::print_info "Generating protected key..."
    age-keygen | age -p -e > "{{path}}"


# Encrypt all secrets.
encrypt-all:
    #!/usr/bin/env bash
    set -eu -o pipefail
    cd "{{root_dir}}"
    fd -gu  '**/*{{DEC_SUFFIX}}*' "." |
        xargs -I{} just sops::encrypt "{}"

# Encrypts a secrets file.
[no-cd]
encrypt file:
    #!/usr/bin/env bash
    set -eu -o pipefail
    . "{{root_dir}}/tools/ci/general.sh"

    f=$(realpath "{{file}}")

    ci::print_info  "Encrypting '$f'..."
    [ -f "$f" ] || ci::die "File '$f' does not exist."

    fbase_real=$(basename "$f")
    fbase="${fbase_real/{{DEC_SUFFIX}}/}"
    if [ "$fbase" = "$fbase_real" ]; then
        ci::die "Can only encrypt files with '{{DEC_SUFFIX}}' extension."
    fi

    fdir=$(dirname "$f")
    ext="${fbase##*.}"
    name="${fbase%.*}"
    enc_file="$fdir/$name{{ENC_SUFFIX}}.$ext"

    if sops filestatus "$f" 2>/dev/null | jq -e '.encrypted == true' &>/dev/null;  then
        ci::die "File is already encrypted."
    fi

    ci::print_info  "Saving to file '$enc_file'"

    sops -e "$f" > "$enc_file" &&
        rm "$f"|| {
            ci::print_info "Sops encryption failed!"
            rm "$enc_file"
            exit 1
        }

    ci::print_info  "Done"

# Decrypt to stdout
decrypt file:
    #!/usr/bin/env bash
    set -eu -o pipefail
    . "{{root_dir}}/tools/ci/general.sh"

    f=$(realpath {{file}})
    ci::print_info "Decrypting '$f'..."

    just -f "{{source_file()}}" run decrypt "$f"

# Edit the file in place.
edit file:
    #!/usr/bin/env bash
    set -eu -o pipefail
    f=$(realpath {{file}})

    . "{{root_dir}}/tools/ci/general.sh"
    ci::print_info "Editing '$f'..."
    just -f "{{source_file()}}" run edit "$f"

# Update secrets based on secrets.yaml (without rotate)
update:
    just -f "{{source_file()}}" re-encrypt "false"

# Re-encrypt secrets based on secrets.yaml and rotate data encryption key.
[no-cd]
re-encrypt rotate="true":
    #!/usr/bin/env bash
    set -eu -o pipefail

    . "{{root_dir}}/tools/ci/general.sh"

    ci::print_info "Re-encrypt all secret files"

    cd "{{root_dir}}"
    readarray -t files < <(fd -gu '**/*{{ENC_SUFFIX}}*' ".")
    for f in "${files[@]}"; do
        sops updatekeys -y "$f"

        if [ "{{rotate}}" = "true" ]; then
            sops rotate -i "$f"
        fi
    done


[doc("Runs command with secrets (env. vars) sourced.")]
exec-env *args:
    #!/usr/bin/env bash
    set -euE -o pipefail
    shift 1

    . "{{root_dir}}/tools/ci/general.sh"
    just -f "{{source_file()}}" run exec-env "{{root_dir}}/.sops.env" "{{args}}"

