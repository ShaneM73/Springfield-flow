#!/bin/bash
# Wait for the out-of-state fetch to finish, then run every metro in parallel, then build the web data.
cd "$(dirname "$0")"
while pgrep -f "python 00_fetch_outofstate.py" > /dev/null; do sleep 15; done
grep -q "^done" ../outputs/fetch_outofstate.log || { echo "fetch did not finish cleanly"; exit 1; }
for m in springfield columbia jeffcity joplin stjoseph capegirardeau kansascity stlouis; do
  ./run_metro.sh $m &
done
wait
cd .. && .venv/bin/python tools/build_basemap.py --raw /tmp/claude-660438191/-home-sgf-edubear-net-xm7303/f0265116-52ce-47b1-b6c1-12285dcd6781/scratchpad/raw springfield columbia jeffcity joplin stjoseph capegirardeau kansascity stlouis > outputs/build_basemap.log 2>&1
.venv/bin/python tools/build_webdata.py > outputs/build_webdata.log 2>&1
echo ALL DONE
