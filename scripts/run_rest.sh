#!/bin/bash
# Phase 3 (parallel code) for all metros, then Phase 4, comparison, web data.
cd "$(dirname "$0")"
MS="springfield columbia jeffcity joplin stjoseph capegirardeau kansascity stlouis"
for m in $MS; do
  (OMP_NUM_THREADS=2 ../.venv/bin/python 05_flow_structure.py $m > ../outputs/$m/phase3.log 2>&1 && echo "== $(date) done $m (05 parallel)" >> ../outputs/$m/pipeline.log || echo "PHASE3 FAILED $m") &
done
wait
for m in $MS; do
  (OMP_NUM_THREADS=4 ../.venv/bin/python 07_structure_tests.py $m > ../outputs/$m/phase4.log 2>&1 || echo "PHASE4 FAILED $m") &
done
wait
../.venv/bin/python 06_compare.py > ../outputs/comparison_log.txt 2>&1 || echo "06 FAILED"
cd .. && .venv/bin/python tools/build_webdata.py > outputs/build_webdata.log 2>&1 || echo "WEBDATA FAILED"
echo REST ALL DONE
