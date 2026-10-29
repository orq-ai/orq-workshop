<p class="stage-chip">Academy · the idea, no code · <a href="../start/academy/">all six stages</a></p>

# Gate and monitor

## The problem

On Friday afternoon a product manager at Lumen Goods tightens one sentence in the refund agent's instructions and merges it. The evaluation from the previous stage exists, on an engineer's laptop, and she is on holiday. The change ships. By Monday the agent is refusing ordinary refunds: a customer with ord_a1, delivered last week, EUR 24.99, is told to wait for human review, and so are forty others. The regression was measurable on Friday. Nothing measured it, because running the evaluation was a thing a person did, not a thing the pipeline did.

The second half of the story is cost. The same week, a model provider changed its pricing and a new persona in the simulation suite ran longer conversations than anyone intended. Spend for the project tripled over the weekend. The team found out on Thursday, from the finance dashboard, not from anything they owned. Two numbers moved, a quality score and a cost total, and in both cases the people who could act were the last to know.

## The idea

A gate is a test that a change cannot skip. It has three parts: a fixed set of inputs, one scorer per failure mode, and a threshold on each scorer's mean. The pipeline runs the agent over the inputs, scores every row, compares the means with the thresholds, and fails the build if any mean falls short. The experiment record is what a reviewer reads to see which row dropped; the exit code is what stops the merge.

Thresholds are calibrated, not aspirational. Run the gate several times on a version you trust and set each bar below the number it scores, with a margin, because a model judge lands on its own mean often enough that a bar set at the mean fails correct changes. Set the bar for the deterministic checks as high as the policy demands: no personal data in the answer is a bar of one hundred percent. Then run the gate on a version you know is bad and confirm it fails; a gate that has never failed has never been tested.

A gate fails closed. A row that errored, or a judge that could not reach a verdict, counts as a failure, so an outage during the run cannot pass as "no problems found". The same shape works for attacks: a fixed file of known attacks, a resistance rate, a bar at zero tolerance.

A gate catches what you already know to test, before it ships. Monitoring catches what you did not, after. The two are not alternatives.

| | Gate in the pipeline | Alert in production |
|---|---|---|
| Runs | on every change, before merge | every few minutes, on live traffic |
| Reads | a fixed dataset and known attacks | the metrics every trace already carries: cost, latency, errors, guardrail blocks |
| Catches | a known failure mode returning | a number moving in a way nobody predicted |
| Misses | the failure you have not named yet | anything that is not a metric |

An alert is a metric query on a timer: the sum of cost in the last five minutes, the error rate, the count of guardrail blocks, compared with a threshold, with a notifier at the end. Because the metrics come from the traces, there is nothing to instrument; the alert reads what the Trace stage already produces.

![Diagram: the application sends traces into the platform; the telemetry store aggregates them; an alert evaluates one metric every five minutes and notifies a channel when its threshold is crossed; a webhook posts signed events to a receiver the team runs; a trace automation routes selected traces into a review queue.](../modules/alerts-and-webhooks/assets/observability-ops.png)

A webhook is the trace store calling you. When an event happens, a model response, an agent configuration change, an experiment finishing, the platform posts it, signed, to an endpoint you run. That is how the loop reaches the systems you already have: a ticket when a guardrail blocks, a message when someone edits the agent in production, a dashboard that is yours.

Two limits are worth knowing in advance. Reporting arrives in minutes, not seconds, so an alert with a five-minute window fires a tick or two late. And a request the gateway rejected before it reached a model may carry less context than a successful one, so an error-rate alert scoped to a project may not see every failure. Alert on the metrics that successful traces carry, and watch rejected requests separately.

## What good looks like

- [ ] No change to the agent's instructions, model or tools reaches production without the gate running, and the gate has failed at least once on purpose.
- [ ] Every threshold has a written reason: the number it was calibrated against and the margin.
- [ ] A rise in cost, error rate or guardrail blocks reaches a person within fifteen minutes, through a channel they already read.
- [ ] A change to the production agent's configuration notifies the team, whoever made it.
- [ ] The gate's results and the alerts read from the same traces the team uses to debug.

## Where teams start

Let's assume you have nothing yet but an evaluation that runs from the command line. Put that command in the pipeline on every pull request and let it exit nonzero. That is the whole first step. Add a cost alert on the project the same day, with a threshold at twice last week's spend.

Let's assume you have an app in production with a pipeline and an on-call rotation. Add the evaluation as a required check and route the alerts to the existing on-call channel, not a new one. Then add the webhook for configuration changes: in most production incidents involving an agent, the first question is "who changed the prompt", and the answer should already be in the channel.

## On orq.ai

On orq.ai the gate is evaluatorq running from the CI runner: a job over a dataset, scorers per failure mode, thresholds on the means, an exit code for the build and an Experiment in the Studio for the reviewer. The red-team gate is the same library in static mode, with a fixed attack file and a resistance bar. Alerts are project-scoped metric queries over the Telemetry API, on signals such as cost, latency, errors and guardrail blocks, with a window, an interval and a notifier. Webhooks post signed events, such as a model response or an agent update, to a URL you own, and trace automations route selected traces into an annotation queue. Read [Alerts](https://docs.orq.ai/ai-studio/observability/alerts) and the [evaluatorq repository](https://github.com/orq-ai/evaluatorq).

## Practice it

- [Evals and agents in CI](../modules/evals-in-ci.md) (core path)
- [Alerts and webhooks](../modules/alerts-and-webhooks.md)

## For leaders

**Cost.** An afternoon to wire the existing evaluation into the pipeline; a few minutes of model time per pull request.

**Risk.** Without a gate, every merge is a release of an untested agent; without alerts, finance finds your incidents.

**Owner.** Whoever owns the pipeline owns the gate; whoever is on call owns the alerts.

**Ask your team.** What blocks a bad change from reaching production, and who gets paged when cost or errors jump?
