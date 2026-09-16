# Terraform

Everything the workshop creates by hand or with `make seed` can also be declared as code. The official [orq Terraform provider](https://registry.terraform.io/providers/orq-ai/orq/latest/docs) manages projects, model access, credentials, budgets, guardrails, evaluators and routing rules, with Terraform or OpenTofu. It is the Admin track's "day 2": module 05 mints the Management Key the provider authenticates with.

```hcl
terraform {
  required_providers {
    orq = { source = "orq-ai/orq", version = "~> 0.2" }
  }
}

provider "orq" {}   # reads ORQ_API_KEY (a Management Key); ORQ_API_BASE_URL for on-prem
```

## What the provider manages today

| Area | Resources |
|---|---|
| Workspace | `orq_project`, `orq_workspace_settings` (display name, model enforcement, PII redaction), `orq_api_key`, `orq_management_key` |
| Models and routing | `orq_workspace_model` (enable a catalog model, share it with projects), `orq_model` (OpenAI-compatible, private base URL), `orq_bedrock_model`, `orq_routing_rule` (fallback, weighted, latency-based, round-robin) |
| Quality and cost | `orq_evaluator` (LLM-as-judge and Python), `orq_guardrail_rule`, `orq_budget` (spend, token and rate ceilings), `orq_notifier` (email, webhook) |
| Data sources | `orq_projects` |

Read the absences as carefully as the list: agents, knowledge bases, deployments, prompts, MCP servers, webhooks and annotation queues have **no** resources yet, so the Managed Agents and AI Observability tracks stay SDK or Studio work. Everything the provider covers is gateway and admin surface — which is why this page sits in this section.

Adoption does not require starting over. Every managed resource can be imported, one `import` block at a time with `terraform plan -generate-config-out=generated.tf`, or a whole existing workspace at once. See [Supported resources](https://docs.orq.ai/reference/terraform/resources) and [Importing an existing workspace](https://docs.orq.ai/reference/terraform/importing) for the current list and syntax.

A key with permission mode `ALL` manages every supported resource, including further API keys and Management Keys; a `RESTRICTED` key manages only the domains it was granted. This workshop does not run Terraform: the entities are created through the SDK so every module stays runnable from one `.env`. If your platform team keeps workspaces in code, the module 05 budget, the module 03 routing rule and the module 04 guardrail rule are the first three resources to move.

Docs: [Terraform](https://docs.orq.ai/reference/terraform), [Quickstart](https://docs.orq.ai/reference/terraform/quickstart), [Supported resources](https://docs.orq.ai/reference/terraform/resources), [GitHub](https://github.com/orq-ai/terraform-provider-orq).
