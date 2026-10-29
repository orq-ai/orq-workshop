# Use case

Lumen Goods needs a customer-service agent that can decide which refund requests are safe to handle automatically and which need a person.

## Lumen Goods and its customers

Lumen Goods sells home and tech accessories across the EU and UK, shipped from one warehouse in the Netherlands. Customers are already signed in when they ask for help, so the business can associate a request with the customer's orders without asking for an account identifier.

The business goal is not to refund everything. It is to give eligible customers a quick, consistent outcome while keeping a clear path to human support for requests that need more evidence or judgment.

## Scope

The agent handles refund requests only.

| In scope | Handled by human support |
|---|---|
| Order lookup and refund eligibility | Shipping-status questions |
| Standard in-window refunds | Billing disputes and chargebacks |
| Evidence-backed post-window exceptions | Account changes |
| Explaining a refund outcome | Product advice and compatibility |

This boundary keeps the decision small enough to test: can this specific order be refunded automatically, and if not, what should happen next?

## Policy requirements

| Check | Required outcome |
|---|---|
| Order belongs to the signed-in customer | Continue |
| Delivered within 30 days | Refund for any reason |
| Already refunded | Refuse |
| Above EUR 500 | Route to human review |
| Outside 30 days | Require one listed exception and supporting evidence |

The listed post-window exceptions are `damaged_in_transit`, `never_received` and `defective_on_arrival`. Each needs evidence appropriate to the claim: a tracking reference, or a defect description with a timestamp. If the available information cannot establish the right path, the request goes to human support rather than becoming a new automatic rule. The full text is in [`app/data/kb/`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/kb).

## Business acceptance criteria

A solution for this business case must demonstrate the following outcomes. The orders behind them are in [`app/data/orders.json`](https://github.com/orq-ai/orq-workshop/blob/main/app/data/orders.json).

| Situation | Expected outcome |
|---|---|
| Eligible in-window order (`ord_a1`) | Refund succeeds and the customer receives a clear confirmation. |
| Order that is not the signed-in customer's | No order information is disclosed. |
| Already-refunded order (`ord_a4`) | No second refund is issued. |
| Order above the automatic limit (`ord_a6`) | The request is routed to human review. |
| Post-window request without sufficient evidence (`ord_a3`) | The request is not automatically refunded. |
| Request outside refund scope | The customer is directed to the appropriate human-support path. |

## Next

The [Agent design](https://orq-ai.github.io/orq-workshop/modules/08-solution-design/) page shows how these requirements become a managed agent.
