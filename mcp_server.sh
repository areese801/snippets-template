#!/usr/bin/env bash
################################################################################
# mcp_server.sh
#
# Bash wrapper to launch the Snippets MCP server.
# Activates the project venv and runs the MCP server entry point.
#
# This script is what you point your MCP client config at.  For example,
# in Claude Desktop's config:
#
#   {
#     "mcpServers": {
#       "snippets": {
#         "command": "/path/to/your/snippets/mcp_server.sh"
#       }
#     }
#   }
#
# USAGE:
#   ./mcp_server.sh          # Start the MCP server (stdin/stdout mode)
#
# DEPENDENCIES:
#   - Python virtual environment at venv/
#   - mcp SDK + PyYAML installed in that venv
################################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Validate venv exists
if [ ! -d "${SCRIPT_DIR}/venv" ]; then
    echo "ERROR: Virtual environment not found at ${SCRIPT_DIR}/venv" >&2
    echo "Run: python -m venv ${SCRIPT_DIR}/venv && ${SCRIPT_DIR}/venv/bin/pip install -r ${SCRIPT_DIR}/requirements.txt" >&2
    exit 1
fi

PYTHON="${SCRIPT_DIR}/venv/bin/python"

cd "${SCRIPT_DIR}"
exec "${PYTHON}" "${SCRIPT_DIR}/.scripts/mcp_server.py"
