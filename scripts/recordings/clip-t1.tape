# Clip T1 · One changed line, a named trace (tracing module, step 1). Storyboard approved 2026-11-06.
# Record from the repo root: ORQ_ACADEMY=1 vhs scripts/recordings/clip-t1.tape, then
# scripts/recordings/caption.sh adds the captions. Hidden parts (setup, waiting for the API) are cut,
# so the visible timing below is fixed; the captions in clip-t1.captions match it.
# The tape edits modules/tracing/run.py for real: run `git checkout modules/tracing/run.py` after.

Output .context/recordings/clip-t1.raw.mp4

Set Shell "bash"
Set FontSize 22
Set Width 1440
Set Height 900
Set Padding 36
Set TypingSpeed 45ms
Set Theme "GitHub Dark"

Hide
Type `export PATH=/opt/homebrew/bin:$PATH PS1='$ ' ORQ_ENV_FILE=.env.academy; set -a; . ./.env.academy; set +a; clear`
Enter
Sleep 1s
Show

# Scene 1 · 0:00 · the script says which line to change
Type `uv run python modules/tracing/run.py --step 1`
Sleep 400ms
Enter
Hide
Wait+Screen@120s /search the trace ids above/
Show
Sleep 6s

# Scene 2 · the one value
Hide
Type `clear`
Enter
Show
Type `vim -c '/trace_name = None' modules/tracing/run.py`
Sleep 300ms
Enter
Sleep 2s
Type `fN`
Sleep 600ms
Type `cw`
Type `"refund-turn"`
Escape
Sleep 2500ms
Type `:wq`
Enter

# Scene 3 · the rerun: the trace has a name
Hide
Type `clear`
Enter
Show
Type `uv run python modules/tracing/run.py --step 1`
Sleep 400ms
Enter
Hide
Wait+Screen@120s /search the trace ids above/
Show
Sleep 7s

# Scene 4 · the same from the CLI
Hide
Type `clear`
Enter
Show
Type `orq traces search --from now-10m --to now --limit 3 -j "data[].{name: name, trace: trace_id}"`
Sleep 400ms
Enter
Hide
Wait+Screen@60s /refund/
Show
Sleep 5s
