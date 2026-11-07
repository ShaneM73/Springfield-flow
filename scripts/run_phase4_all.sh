#!/bin/bash
# wait for KC/STL phase 3, run phase 4 for them, wait for all phase-4 runs, then compare + web data
cd "$(dirname "$0")"
for m in kansascity stlouis; do
  until grep -q "done $m" ../outputs/$m/pipeline.log; do sleep 20; done
  (OMP_NUM_THREADS=8 ../.venv/bin/python 07_structure_tests.py $m > ../outputs/$m/phase4.log 2>&1) &
done
wait
while pgrep -f "python 07_structure_tests.py" > /dev/null; do sleep 10; done
for m in springfield columbia jeffcity joplin stjoseph capegirardeau kansascity stlouis; do
  grep -q Traceback ../outputs/$m/phase4.log && echo "PHASE4 FAILED $m"
done
../.venv/bin/python 06_compare.py > ../outputs/comparison_log.txt 2>&1 || echo "06 FAILED"
cd .. && .venv/bin/python tools/build_webdata.py > outputs/build_webdata.log 2>&1 || echo "WEBDATA FAILED"
echo PHASE4 ALL DONE
