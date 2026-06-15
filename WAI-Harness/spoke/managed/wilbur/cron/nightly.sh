#!/bin/bash
#
# Wilbur Nightly Scan Cron Wrapper
# Scheduled: 02:00 UTC daily
# Sets environment and executes nightly_scan.py
#

set -e

FRAMEWORK_ROOT="/home/mario/projects/wheelwright/framework"
WILBUR_ROOT="${FRAMEWORK_ROOT}/wilbur"
NIGHTLY_SCRIPT="${WILBUR_ROOT}/tools/nightly_scan.py"
LOG_FILE="${WILBUR_ROOT}/logs/nightly-cron.log"

# Ensure log directory exists
mkdir -p "$(dirname "${LOG_FILE}")"

# Export environment
export PYTHONUNBUFFERED=1
export PATH="/usr/local/bin:/usr/bin:/bin"

# Log entry
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting nightly scan" >> "${LOG_FILE}"

# Run the scan with error handling
if python3 "${NIGHTLY_SCRIPT}" >> "${LOG_FILE}" 2>&1; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Nightly scan completed successfully" >> "${LOG_FILE}"
    exit 0
else
    EXIT_CODE=$?
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Nightly scan failed with exit code ${EXIT_CODE}" >> "${LOG_FILE}"
    exit ${EXIT_CODE}
fi
