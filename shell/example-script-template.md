---
id: 00000000-0000-0000-0000-000000000003
title: "Bash Script Template"
language: "shell"
tags: [bash, template, boilerplate, example]
description: "Standard bash script template with strict mode and logging - demonstrates snippet format"
created: "2026-03-06"
last_updated: "2026-03-06"
---

#!/usr/bin/env bash
set -euo pipefail

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Cleanup trap
cleanup() {
    local exit_code=$?
    [ ${exit_code} -ne 0 ] && log_error "Script failed"
}
trap cleanup EXIT

# Main logic here
log_info "Script started"
