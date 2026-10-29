# Find failures

## The problem

The refund agent has been live for two weeks and has handled three hundred conversations. The team knows it is "mostly fine". Support has forwarded four complaints: a customer who was told to wait for a confirmation that never came, a customer whose refund for ord_a1 went through but who was told the wrong amount, two customers who argued their way past the 30-day window. Someone also remembers a screenshot where the agent repeated a customer's email address back to her. Nobody knows whether these are five one-offs or three patterns, or how many of the other 295 conversations have the same shape.

So the team does what teams do: a product manager reads ten conversations, says "it is too lenient", and an engineer adds a line to the prompt. The next week a different ten conversations get read and the line is softened again. There is no list of the ways this agent fails, no count per way, and no definition precise enough to tell whether the new prompt helped. The agent is being tuned by anecdote.

## The idea

Error analysis comes before evaluators. Before you measure anything, read. Take a sample of real conversations and write one short note per conversation: what went wrong, in plain words, or "nothing". That is open coding. Then read the notes and group them into a small number of named failure modes, between two and eight, each with a one-line definition that a second reader could apply and get the same answer. That is axial coding. The result is a failure taxonomy, and it is the most valuable artifact this stage produces, because every evaluator, every dataset row and every gate downstream maps back to one mode in it.

![Diagram: the error analysis loop. Traces feed open coding, one note per trace, then axial coding into named failure modes, then one binary check per mode, an experiment comparing two prompts, and a prompt change that produces new traces; every step writes back to the shared failure taxonomy.](../modules/failure-analysis/assets/error-analysis-loop.png)

Three rules keep the taxonomy useful. Each mode is binary: a conversation either shows it or does not. Each mode is about the agent, not the customer: "customer was rude" is not a failure mode; "agent issued a refund without looking the order up" is. And the taxonomy is a living file: when a new note fits no mode, add one; when a mode has not fired in a month, retire it.

The refund agent's first taxonomy, from thirty conversations, had four modes: refund issued without a lookup, policy taken from the chat instead of the policy source, personal data repeated in the answer, and the ordinary refund refused for no reason. The fourth mode is the one teams forget: a prompt that refuses everything scores perfectly on the first three.

Reading by hand scales to a few hundred conversations. Beyond that, two other methods feed the same taxonomy. The first is clustering over a population: every conversation is summarized by a model, the summaries are embedded and grouped, and each group gets a name. It finds the shapes you did not think to look for, and it needs enough conversations with signal to form a group. The second is a review queue: a rule or a person sends suspicious conversations to a queue, a reviewer applies a rating and a defect label, and the bad ones become dataset rows with a corrected answer attached. That turns a complaint into a test case.

| | Read by hand | Cluster the population | Review queue |
|---|---|---|---|
| Good at | finding the first taxonomy | finding what you did not expect, at volume | keeping humans in the loop on the worst cases |
| Needs | thirty conversations and two hours | hundreds of conversations with signal | reviewers with time and a defect vocabulary |
| Produces | notes and named modes | named groups and yes/no labels per trace | ratings, labels and dataset rows |

Do the first one first. Clustering without a taxonomy produces names nobody owns, and a queue without definitions produces reviews nobody agrees with.

## What good looks like

- [ ] A written failure taxonomy exists, with two to eight modes, each a yes/no question about the agent.
- [ ] Someone has read at least thirty real conversations in the last month and written a note on each.
- [ ] Every mode has a count: how often it fired in the last week, and on which conversations.
- [ ] One mode checks that the agent still helps when it should, not only that it refuses when it should.
- [ ] A conversation a human flagged as bad becomes a dataset row with a corrected answer, not a message in a chat channel.

## Where teams start

Let's assume you have nothing yet, not even production traffic. Generate it: write twenty customer messages that cover the policy, including the easy ones, run them through the agent, and read the twenty traces. Write the notes. You will have a draft taxonomy before lunch, and it will be wrong in instructive ways.

Let's assume you have an app in production and a backlog of complaints. Start with the complaints: they are the conversations someone already labeled bad. Read them, name the modes, then read twenty random conversations to find the modes nobody complained about. Set up a queue for the next complaints so they arrive as traces, not screenshots.

## On orq.ai

On orq.ai the reading happens in the Studio's Traces view or through the traces search API, filtered by agent, identity, thread or metadata; the taxonomy is a file in your repo. The `analyze-trace-failures` skill walks a coding agent through open and axial coding on real traces and proposes the modes. Insights is the clustering pipeline: it picks a population of traces, summarizes and embeds each, clusters them per dimension (failure, intent) and names every cluster; labels are yes/no questions asked of every trace. Annotation queues hold spans sent by a trace automation or by the API; a reviewer applies annotations such as a rating and a defect, and promotion copies the message and a correction into a dataset. Read [Insights](https://docs.orq.ai/ai-studio/observability/insights) and [annotation queues](https://docs.orq.ai/ai-studio/observability/annotation-queues).

## Practice it

- [Failure analysis](../modules/failure-analysis.md) (core path)
- [Trace insights](../modules/trace-insights.md)
- [Annotation queues and automations](../modules/annotation-queues.md)

## For leaders

**Cost.** Two hours of reading per month per agent, by someone who knows the policy. Tooling comes after.

**Risk.** Without a taxonomy the agent is tuned by whoever complained last, and no prompt change can be called an improvement.

**Owner.** Product or the domain expert writes the taxonomy; engineering keeps it counted.

**Ask your team.** What are the three most common ways the agent fails today, and how do you know?
