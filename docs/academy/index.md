# Academy

What orq.ai does, and when it helps your team. One loop of six stages, one page per stage, no code: about an hour in total. Written for team leaders, product owners and anyone new to running AI in production; engineers practice every stage in the [Workshop](../workshop/index.md).

## Where does your team stand?

Tick what sounds like your team today. The loop lights up the stages where orq.ai helps first, in the order to take them.

<div class="symptom-finder" data-symptom-finder>
<div class="symptom-options">
<label class="symptom-option"><input type="checkbox" data-stage="trace"> A customer complains about an answer, and nobody on the team can show what the agent saw or did.</label>
<label class="symptom-option"><input type="checkbox" data-stage="route"> The model bill doubled last month, and nobody can say which feature did it.</label>
<label class="symptom-option"><input type="checkbox" data-stage="evaluate"> Every prompt change fixes one thing and breaks another.</label>
<label class="symptom-option"><input type="checkbox" data-stage="build"> The agent improvises: it promises things no system behind it can do.</label>
<label class="symptom-option"><input type="checkbox" data-stage="find-failures"> Everyone has a story about the agent failing; nobody can name the three most common ways it fails.</label>
<label class="symptom-option"><input type="checkbox" data-stage="gate"> A bad prompt change reached customers before anyone noticed.</label>
<label class="symptom-option"><input type="checkbox" data-stage="route"> When the model provider has an outage, your product has one too.</label>
<label class="symptom-option"><input type="checkbox" data-stage="trace"> The team argues about whether a problem is the model, the prompt or your own data, and there is no way to settle it.</label>
<label class="symptom-option"><input type="checkbox" data-stage="evaluate"> "It looks fine to me" is how changes get approved.</label>
<label class="symptom-option"><input type="checkbox" data-stage="build"> Every team builds its own agent from scratch, with its own tools and prompts.</label>
<label class="symptom-option"><input type="checkbox" data-stage="find-failures"> You have thousands of conversations and no idea which ones to read.</label>
<label class="symptom-option"><input type="checkbox" data-stage="gate"> You hear about problems from customers before your dashboards show them.</label>
<label class="symptom-option"><input type="checkbox" data-stage="route"> Legal asked what customer data you send to model providers.</label>
<label class="symptom-option"><input type="checkbox" data-stage="trace"> Finance asks what one conversation costs, and the answer is the monthly invoice.</label>
<label class="symptom-option"><input type="checkbox" data-stage="evaluate"> You cannot say whether a cheaper model would be good enough.</label>
<label class="symptom-option"><input type="checkbox" data-stage="build"> Nobody can say which decisions the agent takes alone and which go to a person.</label>
<label class="symptom-option"><input type="checkbox" data-stage="find-failures"> Complaints about the agent pile up, and nobody reads them systematically.</label>
<label class="symptom-option"><input type="checkbox" data-stage="gate"> Quality checks happen when someone remembers to run them.</label>
<label class="symptom-option"><input type="checkbox" data-stage="route"> One user stuck in a loop can spend a week's budget in an afternoon.</label>
<label class="symptom-option"><input type="checkbox" data-stage="evaluate"> Nobody has tried to make the agent misbehave on purpose.</label>
<label class="symptom-option"><input type="checkbox" data-stage="trace"> You are about to put an agent in front of customers and cannot say how you would investigate its first incident.</label>
</div>
<nav class="loop-map">
<a class="loop-stage" data-stage="build" data-mode="development" href="build/">Build</a>
<a class="loop-stage" data-stage="route" data-mode="production" href="route/">Route and protect</a>
<a class="loop-stage" data-stage="trace" data-mode="production" href="trace/">Trace</a>
<a class="loop-stage" data-stage="find-failures" data-mode="development" href="find-failures/">Find failures</a>
<a class="loop-stage" data-stage="evaluate" data-mode="development" href="evaluate/">Evaluate</a>
<a class="loop-stage" data-stage="gate" data-mode="production" href="gate/">Gate and monitor</a>
</nav>
<div class="symptom-result" aria-live="polite"></div>
</div>

## The six stages

Read them in order the first time. The loop is a cycle: a change shipped at the last stage is what the first stage builds on next.

<div class="steps" markdown>

1. [Build](build.md): the agent, its instructions and its tools, hosted where it suits you.
2. [Route and protect](route.md): every model call through one gateway, with fallbacks, guardrails and budgets.
3. [Trace](trace.md): what the agent did, for any customer, after the fact.
4. [Find failures](find-failures.md): thousands of traces, a handful of ways the agent goes wrong.
5. [Evaluate](evaluate.md): prove a change is better before it ships.
6. [Gate and monitor](gate.md): stop a bad change in CI, hear about trouble before customers do.

</div>

## You don't have to close the loop at once

Most teams do not start with all six stages, and that is fine. The value adds up: every stage you add gives a better signal for the next. Two starting points cover most teams.

- **Already live, flying blind.** Start with [Route and protect](route.md) and [Trace](trace.md): route the calls through orq.ai and every conversation becomes readable, with its cost, from that day on. Failures and evaluation build on those traces.
- **Not live yet, need confidence first.** Start with [Evaluate](evaluate.md): a small set of test conversations and an evaluator tell you whether the agent is ready, before a customer finds out. Add tracing on the day the first outside user arrives.

## What to ask your team

One question per stage. If the answer is a shrug, that stage is where to invest next.

- **Build:** which decisions does the agent take on its own, and which does it hand to a person?
- **Route and protect:** what happens to a request when the model provider is down, and who pays when a user runs a loop?
- **Trace:** can you show me the full conversation behind one complaint, within a minute?
- **Find failures:** what are the three most common ways the agent fails today, and how do you know?
- **Evaluate:** what runs before a prompt change ships, and what did it catch last month?
- **Gate and monitor:** what blocks a bad change from reaching production, and who gets paged when cost or errors jump?

## If you want to go further

The [core path](../workshop/index.md) is the engineer's version of the same loop: hands-on modules on one sample agent, about four hours. Sit in on one; the "Done when" list at the end of each module is what your team can show you.
