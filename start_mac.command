#!/bin/bash
cd "$(dirname "$0")"
chmod +x ./start_mac.sh
./start_mac.sh
status=$?
if [ "$status" -ne 0 ]; then
  echo "\nThe app stopped with an error (exit code: $status)."
  read -r -p "Press Enter to close this window..."
fi
