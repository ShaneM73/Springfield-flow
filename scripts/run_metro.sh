#!/bin/bash
# Run the per-metro pipeline (panel, Phase 2, Phase 3) for one metro; logs to outputs/<metro>/pipeline.log
set -e
cd "$(dirname "$0")"
m=$1; mkdir -p ../outputs/$m
PY=../.venv/bin/python
{
  echo "== $(date) 02_build_panel $m";   $PY 02_build_panel.py $m
  echo "== $(date) 04_describe $m";      OMP_NUM_THREADS=8 $PY 04_describe.py $m
  echo "== $(date) 05_flow_structure $m"; OMP_NUM_THREADS=8 $PY 05_flow_structure.py $m
  echo "== $(date) done $m"
} > ../outputs/$m/pipeline.log 2>&1
