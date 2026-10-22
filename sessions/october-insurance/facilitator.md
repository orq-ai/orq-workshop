# Facilitator notes · October Insurance, on site, Mon 19 to Thu 22 Oct 2026

Local sources (gitignored, in `.context/`): `october-insurance-prep-notes.md` (call 14 Oct), `october-insurance-sow.md` (SOW 001), `october-insurance-plan.md` (generic 2-day test plan, block ids D1-x / D2-x), `october-insurance-deck.md` (text of Workshop Master Deck 05; the pptx is in `october-insurance-deck-dl/`).

## Where call, SOW and plan agree, and where they differ

- Agree: technical track Mon-Tue then non-technical Wed-Thu, technical first; a hands-on working session on Tue 20 Oct with October Insurance's nominated use cases, closing with a backlog October Insurance owns; governance (roles, SSO, keys, audit logs, EU/ZDR, guardrails/PII), gateway, MCP gateway, KB, agents, evals, CLI/MCP tooling on the technical days; prompting, evaluation and A/B testing for the business days; no production-grade agents.
- Differ, follow the call (later): SOW has the non-technical track as a separate group of 4-8; the call has 5 technical carry-overs paired with 5 business people. the customer contact's four use cases (advice, compliance, claims, TBC) vs the SOW's two nominated for Tue: claims (needs integration work) plus one of advice or compliance on Tue; the rest on Thu.
- Open: SOW Part B (v) status is the yes/no item in the checklist above.
- Plan tips to keep: set EU and ZDR filters before anyone builds; always test the deny path; use the full Chat, not the lighter panels; new builds on Agents or Prompts, not Deployments; open the trace first.

## Reuse map (deck slide numbers from october-insurance-deck.md)

- Day 1 overview and basics, day 3 concepts: slides 5-8, 30-38 (Orqflow, platform, what's new); 10-27 (LLM vs workflow vs agent, tools, parameters).
- Day 1 IT controls: slides 36, 44-45, 69-75 (governance, risk layers, guardrails, PII); plan blocks D1-1, D1-2, D1-5, D1-7, D1-9.
- Day 2: slides 95-101 (agents, orchestrator and sub-agents); plan D2-3 to D2-5.
- Day 3: Plan 39-49 (requirements map), Build 50-64 (prompting, versions), Experiment 65-85 (evaluators, datasets, annotation).
- IT controls 4: also slide 45 (eight risks, eight owners). Day 3 governance block: slides 8 (centrally governed, decentrally delivered) and 45.
- Platform options: slide 33 (SaaS / VPC / on-prem), plan D2-7.
- Day 3 agent block: also slides 95-101.
- Right vs wrong material (Do's and Don'ts): slides 41 (Plan), 52-53 (Build and prompting), 72 (Experiment), 78 (Datasets), 83 (Annotation), 88 (Deploy), 93 (Operate), 96 (Agents), 107 (Enterprise Chat). Open each block with its Do's and Don'ts slide.
- Test materials (Dutch polisvoorwaarden, public MCP servers, golden questions): plan section 5.


## Before the week

- [ ] Hotel booked in Emmen (Van der Valk preferred), Mon to Thu
- [ ] Added to the October Insurance orq environment (the customer contact); on-prem URL still pending, SaaS workspace is the fallback
- [ ] Confirm orq MCP is available in the Claude marketplace; the ZIP plugin works without an enterprise account
- [ ] Pre-session checklist from Cameron received
- [ ] Participant roles per day received from the customer contact (5 technical carry over to days 3 and 4, plus 5 business)
- [ ] 10 Studio accounts exist (EUR 35/user; the customer contact aligns with finance)
- [ ] EU location and ZDR filters set on the workspace before Monday (SOW Part B ii)
- [ ] Each technical participant ran `make doctor && make smoke` on their own laptop (SOW Part B v); each runs `make seed` under their own `WS_PREFIX` in module 00 (`make reset` refuses the bare prefix)
- [ ] Trainer has workspace admin; participants who do module 05 need it too
- [ ] Day 1 click-path for roles, SSO, audit logs written (no module backs it): create a restricted key in the Studio, attempt a write, open the audit-log entry (see the dry-run item below)
- [ ] Budget threshold alert to the notifier set in the Studio and seen firing once (SOW Part B iv; module 05 does not create it)
- [ ] Dutch BSN redaction tested once in the Studio (module 04 does not cover it)
- [ ] Module 10: leave `MCP_SERVER_URL` empty to use the DeepWiki stand-in; check it is reachable from the on-prem instance
- [ ] Day 3: a Studio dataset (10 rows) and judge template per use case (advice, compliance, claims, fourth), not per pair: pairs pick on Wednesday 10:35
- [ ] Claims: third-party agent endpoint and credentials confirmed, one test call made before Monday. Fallback: advice + compliance on Tuesday, claims on Thursday
- [ ] Fourth use case confirmed by Fri 16 Oct, else a policy-FAQ agent over the Dutch polisvoorwaarden (plan section 5)
- [ ] Day 3 per use case: knowledge base with the use case's documents uploaded before Wednesday, one ready-made tool a business person can attach (pre-registered code tool or a public MCP server from plan section 5), Chat enabled on the instance in use
- [ ] SOW Part B (v) done for business participants (orq MCP connected in Claude or Codex): yes/no. If no, the Day 3 Claude Desktop block is a 10 min demo and 10 min go to Experiment
- [ ] Dry-run in the Studio: a restricted key refuses a write, a model outside the EU/ZDR pool is denied. Module 05 stored API-created restrictions as `permission_mode: all`, so do not promise the refusal before seeing it
- [ ] Insurance data for the 4 use cases from the customer contact, Tuesday's two in hand first (SOW 1.5.1 iv): advice, compliance officer, claims (reuses a third-party agent), fourth TBC

## Day 1 and 2 (technical)

Day 1 is platform options and IT controls (the IT manager is in the room): keys, budgets, audit logs, spend. Day 2 builds. Setup (module 00) runs at 09:45, before the agent-basics talk, on purpose: install problems on corporate laptops show up early, while there is still talk content to cover the fix. Right vs wrong for the IT controls (no deck slide covers them): restricted and service-account keys, never personal All keys in apps; budgets on the key or identity, not only the workspace; guardrail rules at the gateway, not per agent; EU/ZDR filters before anyone builds; test the deny path, not only the happy path. Optional if time: module 03 step 3 (routing rule keeping EU traffic on EU providers). Take the brakes off. Order: generic agent first (chatbot, knowledge base), a fun non-insurance example if the room needs energy (not scheduled), insurance in the Tue working session. Python evals and LLM-as-judge intro live here only. Every block says right vs wrong and why, not only how the software works. Attendees: Peter and Martijn (T-shaped analysts, Claude Code daily), 2 developers (API integration, invocation), IT manager (infra).

## Ask the room (do not decide these in advance)

- Day 1 welcome: what they use today (Claude Code, which models, which providers) and what they want to leave with.
- Day 1 platform options: which deployment October Insurance runs, who operates it, which identity provider (SSO).
- Day 1 model access: which models October Insurance wants in the EU/ZDR pool; let the IT manager pick it live.
- Day 1 IT controls: budget per team, who gets which key, audit-log retention, which personal data to redact (BSN, patient data), which tools and MCP servers they would allow. Capture the answers in the IT checklist.
- Day 2 kickoff and MCP: which October Insurance systems they would connect first; who owns each use case.
- Day 3 plan: business people state the requirements, risks and success measure for their pair's use case; ask which tasks they do by hand today.
- Day 4 evaluate: business people write the golden questions and say what a good answer is. They know the right answers, the engineers do not.
- Day 4 request block: priorities for the backlog; which item goes first to the build team.

## Day 3 and 4 (mixed, business-led)

Technical people pair with business people and share an account. Day 4 is not a build day: engineers built the agents on Tuesday, the business pairs now own and improve them (prompts, knowledge, golden questions, judge, annotation), which is the SOW's non-technical outcome. The build hackathon is Tuesday afternoon. Some business people struggle with AI basics, so keep evals light on day 3. The product owner attends for awareness, not building. Buffer on Day 4: demos can start earlier if all pairs are done.

## What to cut when the room runs slow

- Day 1: module 02 step 5, module 04 step 4, module 01 step 4, module 14 step 3 (webhook receiver needs a public URL). Module 14: start the burst at the top of its block; the alert lags a few minutes (use `ALERT_WAIT=600`).
- Day 2: module 08 steps 2b, 6 and 9; module 09 steps 3 and 7 (step 7 needs a tunnel); module 13 entirely; module 07 steps 3 and 7 (need a coding agent).
- Day 3: cut annotation, never the A/B comparison (SOW Annex I names it).
- Day 4: if a pair is stuck at the 14:00 checkpoint, drop the A/B and demo the judge verdicts only.
- Day 2: module 07 and the Tuesday build are tight; if Build 1 runs long, cut the module 07 steps listed above and keep the evaluator in Build 2.
- Gotcha for the IT manager: key restrictions set through the API are not stored (module 05). Create keys in the Studio or CLI.
- Product owner: Day 3 until lunch and the governance block, Day 4 demos. The 5 technical carry-overs coach their partner on Day 3.

## After the week

- [ ] Hackathon on 24 Nov at the October Insurance offices (4 h build, then food and drinks): follow up
- [ ] Handover note and follow-up recommendations to the customer contact by 31 Oct (SOW close-out), seeded from the Tuesday backlog and the Day 1 IT checklist
- [ ] Review account count in 3 months
