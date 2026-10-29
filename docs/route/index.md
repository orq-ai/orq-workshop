<p class="stage-chip">Academy · the idea, no code · <a href="../start/academy/">all six stages</a></p>

# Route and protect

## The problem

It is the Monday after a sale weekend and the refund agent is busy. At 09:40 the model provider starts timing out. The refund agent calls the model directly, so every customer turn waits, then fails, and the support queue fills with "your chat is broken". A customer with an in-window order, ord_a1, EUR 24.99, has typed her request three times. Nobody changed any code; the vendor had a bad morning, and the agent had no second option.

The same week, two smaller things. A customer pasted her full postal address and phone number into the chat, and the agent repeated them back in its answer, which the policy forbids. And one customer, or a script pretending to be one, sent four hundred refund questions in an hour; nobody noticed until the monthly invoice came. Three failures, one cause: every model call went straight from the application to the provider, with nothing in between that could switch, judge, rewrite or count.

## The idea

Put one door between your application and every model. All model calls, from your own loop, from a framework, from a managed agent and from the coding agents on your engineers' machines, go through the same gateway. Once that is true, four things attach to that door without touching the agent.

Resilience is a set of fields on the request: a timeout, a retry on the error codes that are worth retrying, a fallback model when the first one fails, and a cache for repeated questions. The application sends the same request it always sent; the gateway reads the fields and does the switching.

![Diagram: a fallback chain as a sequence. The refund app sends one request with a timeout, a fallback and a retry; the gateway calls the primary model, which times out, retries once, records the fallback, calls the cheaper model, which answers, and returns the response to the app. The same request again within the cache window costs nothing.](../modules/gateway/assets/fallback-chain.png)

Routing decides which model answers. A routing rule is a condition on the request (its model, its metadata, who sent it) and a replacement model; it sits in front of everything else. A smart router is a pool of models and a profile that trades cost against quality per request. Either way the trace names the model that actually answered.

Protection is three controls that differ in what they are allowed to do. A redaction plugin rewrites content: personal data goes out as placeholders and comes back restored. A guardrail judges content with an evaluator and can only pass or block, never rewrite. A guardrail rule is the same check attached by a condition instead of by the request body. The question teams get wrong is when to block and when to measure.

| | Guardrail | Evaluator |
|---|---|---|
| Runs | on the request, before the answer leaves | after the fact, on a sample or a dataset |
| Can | block | score and explain |
| Adds latency | yes, every call | no |
| Use it for | the few rules that must never be broken in front of a customer | everything you want to measure and improve |

A guardrail on every rule slows every turn and turns your evaluators into a wall. A handful of hard rules (no personal data in the answer, no refund above the limit) belong on the request; the rest belong in the Evaluate stage.

Budgets answer who pays. A budget is a limit per period on a scope: the workspace, a project, a user identity, a key, a provider or a model, with an optional rate per minute. The most restrictive matching budget wins, so one customer running a loop hits their own ceiling before they hit yours. This needs two kinds of credential: one that calls models, and a separate administrative one that creates keys and budgets and cannot call models.

## What good looks like

- [ ] Every model call in the company, including coding agents, goes through the same gateway, and you can list the exceptions.
- [ ] A provider outage degrades to a fallback model, and the trace shows when the fallback was chosen.
- [ ] Personal data never reaches a provider in the clear, and never appears in an answer.
- [ ] The rules that must never break in front of a customer are guardrails; everything else is an evaluator.
- [ ] Every user, key and project has a spending limit, and someone is told when it is hit.

## Where teams start

Let's assume you have nothing yet. Change one line: the base URL of your model client. The gateway is a drop-in for the OpenAI endpoint, so nothing else moves. Then add a timeout and one fallback to the request, and send a test request with your own email address in it to see what the provider receives.

Let's assume you have an app in production with its own retry logic and a provider key per service. Move the routing decision out of the code and into the gateway first, so one outage is handled in one place. Then give each service its own key and budget, so the invoice has names on it. Add guardrails last, and only for the rules a guardrail already caught in your traces.

## On orq.ai

On orq.ai the door is the AI Gateway. Fallbacks, retries, timeouts, cache and load balancing travel as fields the OpenAI client forwards untouched, on the chat completions endpoint and on the Responses API. Routing rules match a request by model, metadata, identity, headers or project and replace its model; a Smart Router is a model id that picks from a pool by a cost, balanced or quality profile. Guardrails are evaluators attached to the request or by rule, and they block with a documented error code; the PII redaction plugin rewrites the input and restores it on the way back. Budgets are scoped to workspace, project, identity, API key, provider or model, and are managed with a Management Key, a credential that cannot call models. Read [the gateway introduction](https://docs.orq.ai/ai-gateway/get-started/introduction), [guardrails](https://docs.orq.ai/ai-gateway/configuration/guardrails) and [budgets](https://docs.orq.ai/ai-gateway/budgets).

## Practice it

- [Gateway](../modules/gateway.md) (core path)
- [Smart routing](../modules/smart-routing.md)
- [Guardrails](../modules/guardrails.md)
- [Budgets and keys](../modules/budgets-and-keys.md)

## For leaders

**Cost.** One line changed per application, then an afternoon per control. The gateway itself adds milliseconds, not minutes.

**Risk.** Without it, one vendor incident is your incident, personal data leaves the building, and the invoice has no names on it.

**Owner.** Platform or infrastructure, with the budgets reviewed by whoever reviews cloud spend.

**Ask your team.** What happens to a request when the model provider is down, and who pays when a user runs a loop?
