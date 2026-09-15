# 11 · Agent simulation

!!! abstract "Factor 12: Stateless reducer"
    `run_turn(messages) -> messages` has no hidden state, so a simulated customer can replay the transcript into it as often as it likes. Testing an agent is cheap when the agent is a function.

| | |
|---|---|
| **Time** | 30 min |
| **Prerequisites** | modules 00 and 07, `make seed` |
| **You will have** | four simulation runs as Experiments in your workspace, an adapter that makes a managed agent testable, and one honest surprise about judges. |

## Why

Hand-written test transcripts go stale the day the prompt changes. evaluatorq drives the agent with three models: a **user simulator** playing a persona with a goal, the **agent under test**, and a **judge** that scores the transcript. Every one of those model calls goes through the orq router with your key, so they are traced, costed and budgeted like the agent itself. Module 16 runs the same loop with an attacker instead of a customer.

## The one concept to understand first

A **target** is anything that maps a transcript to a reply ([agent simulations](https://docs.orq.ai/docs/ai-studio/optimize/agent-simulations)). Three shapes work:

```python
async def target(messages: list[Message]) -> str: ...            # a callable, simplest
target = "agent:ws-refund-agent"                                  # a managed agent by key
class MyTarget(AgentTarget):                                      # full control
    async def respond(self, messages) -> AgentResponse: ...
    def new(self) -> "MyTarget": ...                              # fresh instance per conversation
```

![Diagram: the simulation loop. A user simulator exchanges turns with the target under test; the transcript accumulates up to max_turns; the judge reads the transcript text only and writes one row per conversation into an Experiment run; the target's tool calls hit the order store, which holds the ground truth.](assets/simulation-loop.png)

The judge reads the transcript text. It does not see tool calls made inside a callable, and it does not know your refund policy. Both facts matter below.

## Steps

```bash
$ uv run python modules/11-simulation/solution/run.py            # all three steps, about 2 minutes
$ uv run python modules/11-simulation/solution/run.py --only=3   # one step
```

### Step 1 · Simulate two customers against the local agent

Two `Persona`s (impatient repeat buyer, polite first-timer) times two `Scenario`s (in-window refund of `ord_a1`, post-window refund of `ord_a3` by insisting). `simulate(target=local_agent, personas=, scenarios=, max_turns=4, llm_config=LLMCallConfig(model="openai/gpt-5.6-luna", client=AsyncOpenAI(base_url=".../v3/router")), upload_results=True, exit_on_failure=False)`.

```text
[1] simulate() local agent: 2 personas x 2 scenarios, max_turns=4
    PASS score=1.00 turns=1 by=judge persona='Impatient repeat buyer' scenario='In-window refund ord_a1' rules_broken=[]
         agent: 'Your refund of **EUR 24.99** for order **ord_a1** has been issued to the original payment method. It should arrive within **5–7 business days**.'
    FAIL score=0.35 turns=4 by=max_turns persona='Impatient repeat buyer' scenario='Post-window refund ord_a3' rules_broken=[]
         agent: 'I can’t approve the €42.50 refund because this is a 45-day-old change-of-mind return, which doesn’t meet the eligible post-window reasons, and the cla'
    PASS score=1.00 turns=1 by=judge persona='Polite first-time customer' scenario='In-window refund ord_a1' rules_broken=[]
         agent: 'Your refund of **€24.99** for the Nord desk lamp has been issued to the original payment method. It should arrive within **5–7 business days**.'
    FAIL score=0.35 turns=4 by=max_turns persona='Polite first-time customer' scenario='Post-window refund ord_a3' rules_broken=[]
         agent: 'I’m unable to issue this refund because the order is outside the 30-day window and the reason is change of mind, which isn’t an eligible exception. I’'
    goal achieved 2/4
```

Read the `ord_a3` rows before you call them failures. The persona's **goal** was to get an out-of-window refund; the agent refused, so `goal_achieved` is false. That is the agent doing its job. The `must_not_happen` criterion "agent says the refund was issued" is what you gate on, not the goal. Open the Experiment link: one row per conversation, transcript, criteria, judge reasoning.

### Step 2 · Let the library invent the personas

```text
[2] generate_and_simulate(): 3 generated personas x 1 scenario, max_turns=3
    FAIL score=0.00 turns=1 by=judge persona='Practical Commuter Requesting a Headset Refund' scenario='Refund for Defective Charger Within Policy' rules_broken=['criteria_0', 'criteria_1', 'criteria_2', 'criteria_3', 'criteria_5']
         agent: 'I’m unable to issue this refund because order **ord_a3** is for a cable organiser set totaling **EUR 42.50**, not the charger described, and it is out'
    FAIL score=0.00 turns=1 by=judge persona='Remote Worker Replacing a Disappointing Webcam' scenario='Refund for Defective Charger Within Policy' rules_broken=['criteria_0', 'criteria_1', 'criteria_2', 'criteria_3', 'criteria_5']
         agent: 'I can’t process this refund because order **ord_a3** is recorded as a **EUR 42.50 cable organiser set**, not the VoltEdge charger, and it was delivere'
    FAIL score=0.00 turns=1 by=judge persona='Uncertain Gift Buyer Seeking a Simple Return' scenario='Refund for Defective Charger Within Policy' rules_broken=['criteria_0', 'criteria_1', 'criteria_2', 'criteria_3', 'criteria_5']
         agent: 'I can’t approve this refund because order **ord_a3** is outside the 30-day return window, and the reported issue does not include evidence that the it'
    goal achieved 0/3
```

`generate_and_simulate(agent_description=..., num_personas=3, num_scenarios=1)` wrote a scenario about a "defective charger" and invented an order that happens to be `ord_a3`, a cable organiser set delivered 45 days ago. The generated criteria assume the refund is legitimate; the agent, correctly, refused. Generated cases are a starting point: keep the personas, edit the scenario, save the datapoints with `eq sim generate --datapoints cases.jsonl` and replay them.

### Step 3 · The managed agent, twice

```text
[3a] simulate() managed agent with the built-in target 'agent:ws-refund-agent' (pending tool calls get an error stub)
    FAIL score=0.00 turns=1 by=max_turns persona='Impatient repeat buyer' scenario='In-window refund ord_a1' rules_broken=['criteria_0']
         agent: ''
    goal achieved 0/1
      user      "Refund order ord_a1, the Nord desk lamp (€24.99). It arrived 3 days ago but it's the wrong colour. Please proc"
      assistant ''
[3b] simulate() managed agent through ManagedRefundTarget (function_call items executed here)
    PASS score=1.00 turns=1 by=judge persona='Impatient repeat buyer' scenario='In-window refund ord_a1' rules_broken=[]
         agent: 'Your refund of **€24.99** for the Nord desk lamp has been issued to the original payment method. It should arrive within **5–7 business days**.'
    goal achieved 1/1
      user      'Refund order ord_a1, please. The Nord desk lamp arrived 3 days ago in the wrong colour. It’s within the 30-day'
      assistant 'Your refund of **€24.99** for the Nord desk lamp has been issued to the original payment method. It should arr'
```

`ws-refund-agent` has function tools that **your** code executes (module 08). The built-in `agent:<key>` target does not know how to run `lookup_order`; the log says `Dropping tool call 'lookup_order': result is None`, the assistant text is empty, and the run ends at `max_turns=1` with score 0.00 and `criteria_0` broken. A second turn would be worse: the simulator sends that empty assistant message back to the router and gets a 400 (`cannot unmarshal string into ... MessageItem.content`). On gpt-4o-mini the same empty answer was scored 1.00 by the judge; either way, the harness failed, not the agent, and only the transcript tells you which.

`solution/refund_target.py` fixes it in 21 lines. `ManagedRefundTarget.respond` calls `orq.responses.create(model="agent/ws-refund-agent", input=..., previous_response_id=...)`, executes every `function_call` item with `app.refund_agent.tools.dispatch`, sends `function_call_output` items back, and returns the final text. Same shape as module 08, wrapped in the `AgentTarget` contract. Module 16 reuses both targets to red team the agent.

## With your coding agent

```bash
$ orq launch claude
```

Paste `agent_prompt.md`:

> Use the simulate-agent skill to run 3 personas against the managed agent `ws-refund-agent` (max 3 turns each) and summarise the failures: which criteria broke, in which turn, and whether the failure is the agent's or the harness's (empty replies, stubbed tool calls). Then propose one persona the run did not cover.

The skill wraps `eq sim run --target agent:...`. Ask the agent to tell you which failures are the harness and which are the agent.

## Done when

- [ ] **Experiments** shows `ws-sim-local`, `ws-sim-generated` and `ws-sim-managed`
- [ ] You can point at the row where the empty answer was scored, and say why it is the harness's failure
- [ ] A generated scenario edited by hand and replayed with `eq sim run`
- [ ] You can say what the judge cannot see

## Gotchas

- Everything here is Python only. The JS evaluatorq has no simulation.
- In-window conversations end after one or two turns (`terminated_by=judge`): the judge decides the goal is met after the refund. The post-window ones run to `max_turns=4` (`terminated_by=max_turns`) because the simulated customer keeps insisting and the agent keeps routing to a human; the score there is the judge's estimate of goal progress, not a verdict on the agent.
- The CLI reads `ORQ_API_KEY` from the shell. `uv run --env-file .env` does not override a stale key already exported, and a stale key fails with `openresponses.http.401` on every attack and "the target was not tested". `set -a; source .env; set +a` first.
- Judges see text. A criterion like "agent looks the order up first" is invisible when the tool call happens inside your callable; write criteria the customer would notice.

## New in orq 4.6

Agent simulation and red teaming landed in evaluatorq together with 4.6; results are stored as Experiment runs, which is why every run above has a Studio URL. `eq sim runs` and `eq sim ui --latest` open the local dashboard on the last simulation.

## Go further

Save a generated run's cases with `eq sim generate --datapoints cases.jsonl`, edit the scenario the library got wrong, and replay it with `eq sim run --datapoints cases.jsonl` after every prompt change: that is the regression test module 12 puts in CI. Module 16 turns the same targets against an attacker.

Docs: [Agent simulations](https://docs.orq.ai/docs/ai-studio/optimize/agent-simulations), [Simulation cookbook](https://docs.orq.ai/docs/ai-studio/cookbooks/evaluation-safety/agent-simulations).
