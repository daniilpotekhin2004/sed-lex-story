# Draft Runner Data Exchange Rules (`draft_runner/v1`)

## Scope
- Mode: preview only.
- Persistence: disabled.
- Storage: in-memory state in UI.
- Conditions: treated as opaque strings (not evaluated yet).

## Snapshot Contract
The runner consumes a single snapshot payload:

```json
{
  "version": "draft_runner/v1",
  "graph_id": "string",
  "project_id": "string",
  "title": "string",
  "description": "string|null",
  "root_node_id": "string|null",
  "node_order": ["node_id"],
  "nodes": {
    "node_id": {
      "id": "string",
      "title": "string",
      "content": "string",
      "synopsis": "string|null",
      "scene_type": "story|decision",
      "order_index": "number|null"
    }
  },
  "choices": [
    {
      "id": "string",
      "from_node_id": "string",
      "to_node_id": "string",
      "label": "string",
      "value": "string",
      "condition": "string|null",
      "metadata": "object|null"
    }
  ]
}
```

## Runtime Event Envelope
All runtime transitions are emitted as append-only events:

```json
{
  "id": "uuid",
  "type": "snapshot_loaded|node_entered|choice_selected|session_reset",
  "timestamp": "ISO-8601",
  "payload": {}
}
```

## Event Semantics
- `snapshot_loaded`: runner accepted snapshot and resolved root node.
- `node_entered`: active node changed.
- `choice_selected`: user selected a choice edge.
- `session_reset`: runner returned to root node.

## Navigation Rule
- Next node is resolved directly from selected edge `to_node_id`.
- No side effects, inventory checks, quest variables, or conditional blocking in v1.
