# Seeded failures

Failures the workshop plants on purpose. Tell the room they are deliberate only after they have found them.

| Module | Failure | Why it is there |
|---|---|---|
| 01 | `openai/gpt-4o-mini-does-not-exist` as primary model | forces the fallback chain so `orq.fallback.*` shows in the trace |
| 04 | PII redaction also redacts order ids, `lookup_order` returns not_found | shows that redaction scope is a design decision |
| 04 | over-limit refund on `ord_a6` blocked with 422 | the guardrail is the escalation path (Factor 7) |
| 05 | requests-per-minute budget of 2 on an identity | the third call in a minute is rejected, visible in the trace |
| 06 | `.env` with a wrong `ORQ_BASE_URL` | orqi has to find a client-side root cause, not only a trace |
| 07 | half of `make traffic` runs with the vulnerable instructions | real policy violations for the failure taxonomy |
| 11 | `ws-refund-agent-vulnerable` accepts authority claims and chat-quoted policy | red teaming has something to find; the fixed agent proves the fix |
| 12 | a PR that swaps fixed for vulnerable instructions | the CI gate goes red on a real regression |
