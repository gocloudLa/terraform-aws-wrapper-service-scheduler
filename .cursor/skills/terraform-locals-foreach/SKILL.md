---
name: terraform-locals-foreach
description: Build Terraform locals with tmp-plus-merge pattern and stable keys for resource for_each. Use when creating or refactoring nested locals that drive for_each in .tf files.
---

# Terraform Locals ForEach

## Goal

Create locals that are safe for `for_each` addressing and resistant to resource churn.

## When To Apply

- Nested inputs must be transformed into a map for `for_each`.
- Existing resources must keep stable addresses over time.
- Team asks to follow local style from another file (for example `create_target_groups`).

## Required Pattern

```hcl
locals {
  my_local_tmp = [
    for k1, v1 in try(var.input, {}) :
    [
      for k2, v2 in try(v1.nested, {}) :
      {
        "${k1}-${k2}" = {
          key1 = k1
          key2 = k2
          # needed resource fields
        }
      } if <include_condition>
    ] if can(v1.nested)
  ]

  my_local = merge(flatten(local.my_local_tmp)...)
}
```

## Rules

- Key must be deterministic and identity-based.
- Keep key format unchanged unless user asks to migrate it.
- If `for_each` needs object fields, iterate the map object directly.
- Avoid mixing map/set iteration shapes for the same domain.
- Keep changes scoped to requested files only.
- Add a short comment before non-trivial locals describing purpose and key shape.
- Add a commented debug output right after each final local map materialization.
- Add a short comment above each consumer resource/data (`for_each = local.xxx`) describing iterated key identity shape.

## Execution Checklist

1. Identify identity fields used to form the key.
2. Build `*_tmp` with nested loops and filters.
3. Materialize final map with `merge(flatten(...)...)`.
4. Ensure consumer resources use compatible `for_each` shape.
5. Add/update local and consumer comments (purpose + key format).
6. Add/update commented debug `output` for each final local map.
7. Run `terraform validate` when possible.