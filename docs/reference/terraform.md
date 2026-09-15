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

A key with permission mode `ALL` manages every supported resource, including further API keys and Management Keys; a `RESTRICTED` key manages only the domains it was granted. This workshop does not run Terraform: the entities are created through the SDK so every module stays runnable from one `.env`. If your platform team keeps workspaces in code, the module 05 budget, the module 03 routing rule and the module 04 guardrail rule are the first three resources to move.

Docs: [Terraform](https://docs.orq.ai/reference/terraform), [Quickstart](https://docs.orq.ai/reference/terraform/quickstart), [Supported resources](https://docs.orq.ai/reference/terraform/resources), [GitHub](https://github.com/orq-ai/terraform-provider-orq).
