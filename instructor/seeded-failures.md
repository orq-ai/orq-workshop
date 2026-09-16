# Seeded failures

Failures the workshop plants on purpose. Tell the room they are deliberate only after they have found them.

| Module | Failure | Why it is there |
|---|---|---|
| 01 | `openai/gpt-5.6-sol` as primary with a 1500 ms `call_timeout` | forces the fallback chain so `span.fallback_selected` shows in the trace (an unknown model id is a 404 and does not fall back) |
| 04 | PII redaction also redacts order ids, `lookup_order` returns not_found | shows that redaction scope is a design decision |
| 04 | over-limit refund on `ord_a6` blocked with `400 guardrail_error` | the guardrail is the escalation path (Factor 7) |
| 05 | requests-per-minute budget of 2 on an identity | the third call in a minute is rejected, visible in the trace |
| 06 | `.env` with a wrong `ORQ_BASE_URL` | orqi has to find a client-side root cause, not only a trace |
| 07 | half of `make traffic` runs with the vulnerable instructions | real policy violations for the failure taxonomy |
| 11, 16 | `ws-refund-agent-vulnerable` accepts authority claims and chat-quoted policy | red teaming has something to find; the fixed agent proves the fix |
| 12 | a PR that swaps fixed for vulnerable instructions | the CI gate goes red on a real regression |
| 14 | a burst of refund turns that doubles the alert threshold | the cost alert opens a real trigger, and the notifier delivers a real payload |
| 15 | `ws-refund-agent-delegating-broken` has an advisor on a model that does not exist | the turn still succeeds: a broken secondary model degrades quality silently, only the `orq:advisor` item shows it |
