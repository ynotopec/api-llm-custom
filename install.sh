#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_name="$(basename "${project_dir}")"
venv_dir="${HOME}/venv/${project_name}"
project_venv_link="${project_dir}/.venv"

mkdir -p "${HOME}/venv"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is not installed."
  echo "Install it first, for example:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

cd "${project_dir}"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

# Create or upgrade the canonical virtualenv in ~/venv/<project_name>
uv venv "${venv_dir}"
UV_PROJECT_ENVIRONMENT="${venv_dir}" uv sync

# Ensure project_dir/.venv points to ~/venv/<project_name>
if [ -L "${project_venv_link}" ]; then
  current_target="$(readlink "${project_venv_link}")"
  if [ "${current_target}" != "${venv_dir}" ]; then
    rm -f "${project_venv_link}"
    ln -s "${venv_dir}" "${project_venv_link}"
  fi
elif [ -d "${project_venv_link}" ]; then
  echo "ERROR: ${project_venv_link} exists as a real directory."
  echo "Move or remove it, then rerun ./install.sh"
  exit 1
else
  ln -s "${venv_dir}" "${project_venv_link}"
fi

chmod +x "${project_dir}/run.sh" "${project_dir}/app.py"

echo
echo "Install complete."
echo "Project dir : ${project_dir}"
echo "Venv dir    : ${venv_dir}"
echo "Project .venv -> ${venv_dir}"
echo
echo "Next:"
echo "  edit ${project_dir}/.env"
echo "  source ./run.sh 0.0.0.0 8000"
