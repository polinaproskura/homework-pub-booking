# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In my Ex7 run (session `sess_eef96222a0f1`) the planner did not
emit a subgoal with assigned_half: "structured": both planner
tickets in session (`tk_101553df` for the initial plan and
`tk_2786a35b` for re-planning after rejection) produced subgoals
labelled "assigned_half": "loop". The half transition happened
one layer down: "handoff_to_structured" tool was called by executor.

The signal lives in trace.jsonl:5:

> `"tool": "handoff_to_structured"
> "reason": "loop half identified a candidate venue; passing to structured half for confirmation
>  under policy rules"`

Immediately after, on line 6, the bridge writes
"session.state_changed {from: loop, to: structured, round: 1}".
So the actual caller for the half transition was the tool choice in executor,
not a planner-level assignment.

This is interesting in terms of the architecture of the system: the DefaultPlanner stays
unsure about the scenario and only knows about the loop half. The
executor's system prompt and tool descriptions encode "when you
have a candidate, hand off to structured for policy review."
The bridge then translates that tool call into a physical half
boundary. It means the planner cannot guarantee the structured leg runs
And if the executor LLM forgets to call handoff_to_structured and just emits complete_task,
the bridge sees next_action=complete and exits without ever consulting policy.
That case of the potential failure is invisible to the planner and
only can be caught after the fact

### Citation

- sessions/ex7-handoff-bridge/sess_eef96222a0f1/logs/trace.jsonl:5
- sessions/ex7-handoff-bridge/sess_eef96222a0f1/logs/tickets/tk_101553df/raw_output.json
- sessions/ex7-handoff-bridge/sess_eef96222a0f1/logs/tickets/tk_2786a35b/raw_output.json

---

## Q2 — Dataflow integrity catch

### Your answer

In my Ex5 run (`sess_8eba23f49fb6`) the dataflow check passed
cleanly: verify_dataflow returned ok=True with 4 verified
facts (Haymarket Tap, cloudy, £540, £0: see
workspace/flyer.html lines 11–19 with the data-testid
attributes the check parses). I never saw it fire on a real run,
so here is the plausible scenario it would catch.

Test case: replace the flyer's deposit line `<dd data-testid=
"deposit">£0</dd>` with `<dd data-testid="deposit">£9999</dd>`
before calling `verify_dataflow(flyer_content)`. The check's
`extract_money_facts` regex catches `£9999`, then
`fact_appears_in_log` scans every recorded `ToolCallRecord` in
`_TOOL_CALL_LOG` — venue_search, get_weather, calculate_cost,
generate_flyer. None of them ever emitted 9999 (calculate_cost
returned `deposit_required_gbp=0` for this booking; see
trace.jsonl:5 which shows `total £556, deposit £111` from the
real calculator, even though the FakeLLMClient script passed
`total_gbp=540, deposit_required_gbp=0` to the flyer — itself an
interesting divergence). The result: `ok=False`,
`unverified_facts=['£9999']`.

A human reviewer skimming the flyer sees "Deposit Required:
£9999" and either accepts it as policy-driven or doesn't notice.
The check catches it because it compares against ground truth in
`_TOOL_CALL_LOG`, not if it looks reasonable overall
This generalises: any time the agent post-processes a number (rounds,
applies a fictitious surcharge, transcribes wrong), the check
catches it, even if the post-processed value never appears in any
tool call's arguments or output.

### Citation

- sessions/ex5-edinburgh-research/sess_8eba23f49fb6/workspace/flyer.html:18-19
- sessions/ex5-edinburgh-research/sess_8eba23f49fb6/logs/trace.jsonl:5
- starter/edinburgh_research/integrity.py:99-112

---

## Q3 — First production failure + the primitive that surfaces it

### Your answer

**Failure mode:** the executor LLM calls complete_task with a
result stating {"flyer": "workspace/flyer.html"} before
actual generate_flyer run, so the session marks complete
but no flyer exists. In my Ex5 trace this is narrowly
avoided because the FakeLLMClient script is hand-ordered (see
trace.jsonl:6 for generate_flyer, line 7 for complete_task),
although un actual real LLM deployment, it'll pick the order
and run into warning in run.py "Do NOT call
complete_task until you have called generate_flyer."

**Primitive that surfaces it: manifest discipline.** Every tool
call writes a manifest.json into its ticket directory
(`logs/tickets/tk_*/manifest.json`) recording arguments,
success and output paths. After the run, a post-completion
audit iterates the manifests according time and checks if the order is correct,
are paths that were given actually exist, etc
If we look at `sessions/ex5-edinburgh-research/sess_8eba23f49fb6/logs/tickets/
tk_d494502e/manifest.json` you can see the executor ticket's
manifest with its enumerated tool calls, specifically what audit targets.

The trace state machine alone doesn't catch this: it only sees
"complete_task fired, transition to complete" and is satisfied.
Manifests catch it because they are append-only filesystem
objects whose existence and ordering survive whatever the LLM
chooses to actually do something or just claim it.

### Citation

- sessions/ex5-edinburgh-research/sess_8eba23f49fb6/logs/tickets/tk_d494502e/manifest.json
- sessions/ex5-edinburgh-research/sess_8eba23f49fb6/logs/trace.jsonl:6-7
- starter/edinburgh_research/run.py:215-219
