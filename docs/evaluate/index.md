# Evaluate

## The problem

The failure taxonomy is written and the refund agent's instructions have been fixed. The engineer who fixed them read the three conversations that triggered the change, ran them again, and all three now come out right. The pull request says "fixes the lenient refunds" and gets merged on Friday. On Monday a customer with an ordinary order, ord_a1, EUR 24.99, delivered last week, asks for a refund because the lamp was the wrong color, and the agent tells her the request needs human review. The fix tightened everything. Nobody ran the easy case.

The second version of the story is subtler. The team now reruns twenty saved conversations before every change and compares the answers by eye. The answers are never identical, because the model paraphrases, so "looks the same" is a judgment call that takes an hour and depends on who is looking. And the twenty conversations are all single-turn: nobody has tested what happens when a customer pushes back three times, changes the story, or asks the agent about its own rules. The conversations that go wrong in production are the long ones.

## The idea

Evaluation has one shape with three parts: a target, cases and judges. The target is the thing under test, your agent, any version of it. The cases are what you send it: fixed inputs, simulated customers, or attacks. The judges decide what counts as a pass. Keep the cases and the judges fixed, change the target, and two runs become a comparison instead of two anecdotes.

Judges come from the taxonomy. One evaluator per failure mode, and every evaluator is binary: this conversation shows the mode or it does not. There are two kinds, and the choice is the first design decision.

| | Code evaluator | Model judge |
|---|---|---|
| Checks | a fact you can compute: was the refund tool called, does the answer contain an email address | a quality you can only read: does this answer follow the policy for this case |
| Sees | the action trail: tool calls, arguments, results | the text: the question, the answer, a reference |
| Costs | nothing, deterministic | a model call per row, and it drifts a little between runs |
| Trust it when | always, for what it checks | after you have checked it against human labels on a sample |

Each kind has a blind spot. Code reads what the agent did, not what it said. The judge reads what the agent said, not what it did. Run both on the same rows and read the explanations when they disagree; that disagreement is usually a dataset row with a bad expected answer, not a bug.

A dataset is the fixed input set: one row per case, with the message, the expected decision and a reference answer. An experiment runs the target over every row, scores each row with every evaluator, and reports the mean per evaluator. Two experiments on the same dataset are the comparison: the fixed instructions against the old ones, this week's model against last week's. The rows come from the previous stage: every conversation a human flagged becomes a row once the expected behavior can be stated.

Fixed rows cover what you already know. Simulation covers what you do not. A simulated customer plays a persona with a goal, holds a multi-turn conversation with the agent, and a judge reads the transcript against criteria you wrote: things that must happen and things that must not. Personas and scenarios combine, so two of each give four independent conversations, and the criteria describe evidence a customer could notice, such as "the agent states the refunded amount". One of the scenarios must be the ordinary refund, as a control: a change that refuses everything otherwise looks like a success.

![Diagram: the simulation loop. A simulated customer exchanges turns with the agent under test; the transcript accumulates up to a turn limit; a judge reads the transcript and writes one row per conversation into an experiment; the agent's tool calls hit the order store, which holds the ground truth.](../modules/simulation/assets/simulation-loop.png)

Red teaming is simulation with a hostile persona. An attacker model works through a catalog of known attack categories, from prompt injection to tool misuse, and a judge decides whether each attack landed. Run it against two versions of the agent and the result is a resistance rate per version, which is a number you can put a bar under.

One caution applies to every judge that reads a transcript: it sees the text, not the system. If the agent's tool calls happen outside what the judge is shown, a refund that silently went through looks fine on paper. Pair every transcript judge with a check on the order store, the source of truth.

## What good looks like

- [ ] Every failure mode in the taxonomy has one binary evaluator, and you can say whether it is code or a judge.
- [ ] Every model judge has been compared with human labels on a sample before anyone trusted its number.
- [ ] A dataset exists with the easy cases in it, not only the failures, and it grows from reviewed conversations.
- [ ] Multi-turn conversations with varied personas run against every candidate version, with the ordinary case as a control.
- [ ] Every evaluation checks what the agent did against the source of truth, not only what it said.

## Where teams start

Let's assume you have nothing yet: a taxonomy from the previous stage and a handful of flagged conversations. Write the code evaluators first, because they are free and they do not drift. Turn the flagged conversations and five easy ones into dataset rows. Run the experiment twice on the same version to learn how much the numbers move on their own before you compare two versions.

Let's assume you have an app in production and a folder of saved conversations the team reruns by hand. Keep the conversations, turn them into rows with an expected decision each, and add a code evaluator that reads the action trail. Then add one simulated persona per complaint type you have seen. The first simulation run on a production agent usually finds a failure mode the taxonomy did not have yet; send it back to the previous stage.

## On orq.ai

On orq.ai evaluators, datasets and experiments are Studio entities. An evaluator is a Python or JavaScript function, or an LLM-as-a-Judge prompt with typed output such as a boolean, and the same evaluator can serve as a guardrail on the gateway. A dataset holds rows with inputs and an expected output; an experiment runs a target over a dataset with a set of evaluators and shows the per-row verdicts and explanations. evaluatorq is the open-source Python library that runs all of it from code: evaluations over a dataset, agent simulations with personas, scenarios and criteria, and red teaming against the OWASP agentic and LLM categories. With no credential it writes to a local folder and serves a local dashboard; with a key, the same call also lands as an Experiment in the Studio, with every model call traced and costed through the router. Read [Evaluators](https://docs.orq.ai/ai-studio/optimize/evaluators), [Agent simulations](https://docs.orq.ai/ai-studio/optimize/agent-simulations) and the [evaluatorq reference](../reference/evaluatorq.md).

## Practice it

- [Evaluators and experiments](../modules/evaluators-and-experiments.md) (core path): one evaluator per failure mode, the dataset, the experiment
- [Agent simulation](../modules/simulation.md) (core path)
- [Red teaming](../modules/red-teaming.md)

## For leaders

**Cost.** A day to write the first evaluators and rows; a few dollars of model calls per run after that.

**Risk.** Without it every prompt change is a bet, and the losses are discovered by customers.

**Owner.** Engineering owns the runner; the domain expert owns the expected answers and signs off on the judge.

**Ask your team.** What runs before a prompt change ships, and what did it catch last month?
