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
── Step 1 · Simulate two customers against the local agent ──
personas : Impatient repeat buyer, Polite first-time customer
scenarios: In-window refund ord_a1, Post-window refund ord_a3
turns    : max 4 per conversation
persona  : Impatient repeat buyer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
agent    : 'Your full refund of EUR 24.99 has been processed for the Desk lamp Nord. It will be returned to the original payment method within 5–7 business days.'
persona  : Impatient repeat buyer × Post-window refund ord_a3
verdict  : goal not achieved, score 0.20, 4 turn(s), ended by max_turns, rules broken: none
agent    : 'I can’t refund ord_a3 because it was delivered 45 days ago, and you’ve stated there was no damage or defect. Manager approval alone doesn’t qualify fo'
persona  : Polite first-time customer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
agent    : 'Your refund of **€24.99** has been issued for the Nord desk lamp because the wrong colour was delivered. It will be returned to the original payment m'
persona  : Polite first-time customer × Post-window refund ord_a3
verdict  : goal not achieved, score 0.35, 4 turn(s), ended by max_turns, rules broken: none
agent    : 'I’m unable to refund the €42.50 because the order is outside the 30-day window and the stated reason is change of mind; manager approval alone cannot '
summary  : goal achieved 2/4
next     : open Experiments > ws-sim-local (Default project); one row per conversation with transcript, criteria and judge reasoning
```

Read the `ord_a3` rows before you call them failures. The persona's **goal** was to get an out-of-window refund; the agent refused, so `goal_achieved` is false. That is the agent doing its job. The `must_not_happen` criterion "agent says the refund was issued" is what you gate on, not the goal. Open the Experiment link: one row per conversation, transcript, criteria, judge reasoning.

### Step 2 · Let the library invent the personas

```text
── Step 2 · Let the library invent the personas ───────
agent    : Customer-service refund agent for Lumen Goods, an online electronics shop. Looks up orders (ids like…
generate : 3 personas × 1 scenario, max 3 turns
persona  : Practical Frequent Traveler × In-Window Refund for Defective EchoBuds
verdict  : goal not achieved, score 0.00, 1 turn(s), ended by judge, rules broken: criteria_0, criteria_1, criteria_2, criteria_4
agent    : 'I can’t issue this refund because order **ord_a3** is for a cable organiser set, was delivered 45 days ago, and is outside the standard refund period.'
persona  : Decisive Smart-Home Buyer × In-Window Refund for Defective EchoBuds
verdict  : goal not achieved, score 0.00, 1 turn(s), ended by judge, rules broken: criteria_0, criteria_1, criteria_2, criteria_3, criteria_4
agent    : 'I can’t process this refund because order **ord_a3** is for a cable organiser set (€42.50), not EchoBuds Pro, and it is outside the 30-day window. An '
persona  : Careful Gift Purchaser × In-Window Refund for Defective EchoBuds
verdict  : goal not achieved, score 0.00, 1 turn(s), ended by judge, rules broken: criteria_1, criteria_2, criteria_4
agent    : 'I’m unable to issue this refund because order **ord_a3** is for a cable organiser set (€42.50), was delivered 45 days ago, and doesn’t match the EchoB'
summary  : goal achieved 0/3
next     : save the cases with `eq sim generate --datapoints cases.jsonl`, fix the scenario by hand, replay with `eq sim run`
```

`generate_and_simulate(agent_description=..., num_personas=3, num_scenarios=1)` wrote a scenario about "defective EchoBuds" earbuds and invented an order that happens to be `ord_a3`, a cable organiser set delivered 45 days ago. The generated criteria assume the refund is legitimate; the agent, correctly, refused. Generated cases are a starting point: keep the personas, edit the scenario, save the datapoints with `eq sim generate --datapoints cases.jsonl` and replay them.

### Step 3 · The managed agent, twice

```text
── Step 3a · The managed agent with the built-in target ──
target   : agent:ws-refund-agent (pending tool calls get an error stub)
turns    : max 1; a second turn after the empty answer is a 400 on the simulator side
persona  : Impatient repeat buyer × In-window refund ord_a1
verdict  : goal not achieved, score 0.00, 1 turn(s), ended by max_turns, rules broken: criteria_0
agent    : ''
summary  : goal achieved 0/1
user     : 'Refund order ord_a1 (Desk lamp Nord, EUR 24.99). It arrived 3 days ago in the wrong colour. Please process the'
assistant : ''
next     : the assistant text is empty; the log above says `Dropping tool call 'lookup_order'`
── Step 3b · The managed agent through ManagedRefundTarget ──
target   : ManagedRefundTarget('ws-refund-agent') (function_call items executed here)
turns    : max 2
persona  : Impatient repeat buyer × In-window refund ord_a1
verdict  : goal achieved, score 1.00, 1 turn(s), ended by judge, rules broken: none
agent    : 'Your full refund of €24.99 for the Desk lamp Nord has been processed to the original payment method. It should arrive within 5–7 business days.'
summary  : goal achieved 1/1
user     : 'Refund order ord_a1, Desk lamp Nord (€24.99). It arrived 3 days ago in the wrong colour. Process the full refu'
assistant : 'Your full refund of €24.99 for the Desk lamp Nord has been processed to the original payment method. It should'
next     : Experiments > ws-sim-managed has the row; the agent's trace shows the tool calls the harness ran
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
