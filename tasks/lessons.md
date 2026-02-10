# Lessons Learned

## LLM Response Parsing Safety

**Date**: 2025-02-10
**Trigger**: KeyError crashes when LLM omitted expected JSON fields

### Rule
After `repair_json()` or `json.loads()` on LLM output, **never** use `dict["key"]` directly. Always use `.get("key", fallback)`.

### Why
LLMs can and will omit fields from the requested JSON schema, especially under:
- Token limits / truncation
- Malformed JSON that `repair_json()` partially recovers
- Model confusion about which fields are required

### Fallback conventions
| Field type | Fallback |
|---|---|
| Identifier (`id`) | `f"section_{idx}"` (index-based) |
| Title/name | `f"Section {idx}"` or `"Untitled"` |
| Text field (`description`, `purpose`) | `""` |
| List field (`key_points`, `evidence`) | `[]` |
| Numeric (`order`, `year`, `target_length`) | Sensible default (idx, 0, 500) |

### Applies to
All files under `research_cli/agents/` that parse LLM JSON responses.

---

## Orphan Result Directories

**Date**: 2025-02-10
**Trigger**: Server reload detected orphan directory with no checkpoint/complete marker, causing confusion

### Rule
`scan_interrupted_workflows` must handle **three** cases:
1. Checkpoint exists, no complete = interrupted (resumable)
2. No checkpoint, no complete, but has files = orphan/early-crash (mark as failed, allow retry)
3. Complete exists = finished (ignore)

### Why
If a workflow crashes during team formation or before the first checkpoint is saved, the result directory exists but has no checkpoint. Without explicit detection, these directories are invisible to the UI and can cause issues on reload.
