# Pharmacy MCP Server — Specification

Industry use case: a pharmacy chain assistant. Given a patient's self-reported
symptoms, it triages them, recommends an over-the-counter (OTC) treatment,
checks drug interactions and allergies, checks branch stock, and can place
an order. Prescription-only medications are refused unless a prescription id
is supplied.

This document is the tool-level API reference. For the protocol-level detail
(JSON-RPC framing, MCP lifecycle) see the root [README](../README.md) and
`src/protocol/`, `src/mcp/`.

## Running the server

- **Local (stdio):** `python -m src.servers.pharmacy.stdio_server`
  Reads one JSON-RPC request per line from stdin, writes one JSON-RPC
  response per line to stdout. No banner, no extra output — anything on
  stdout that isn't a JSON-RPC frame would break the protocol.
- **Remote (Streamable HTTP):** see the "Remote deployment" section of the
  README once `http_server.py` is deployed (second delivery of this project).

## MCP lifecycle

Same as every MCP server: `initialize` → `notifications/initialized` →
`tools/list` → any number of `tools/call` / `ping`. Server info:

```json
{ "name": "pharmacy-mcp", "version": "0.1.0" }
```

Protocol version: `2025-06-18`.

## Data model

All catalog data lives in `src/servers/pharmacy/data/*.json` and is loaded
once per process:

- `medications.json` — 10 SKUs: 8 OTC, 2 prescription-only (amoxicillin,
  warfarin is prescription-only too, losartan is prescription-only). Each
  entry has dosage, contraindications, allergy tags, side effects, a
  pregnancy-safety flag and a price.
- `symptoms.json` — six symptom-to-condition mappings (e.g. common cold,
  tension headache, seasonal allergy) plus a list of red-flag keywords
  (chest pain, difficulty breathing, blood, fainting, confusion, ...).
- `interactions.json` — pairwise drug-drug interaction rules, each tagged
  `warning` or `blocking`.
- `branches.json` — three branches with per-SKU stock counts.

Orders are kept in memory for the lifetime of the process (`orders.py`);
creating an order decrements the branch's stock for the SKUs ordered.

## Safety rules

These are enforced in `core/domain/triage.py` and `core/domain/orders.py`,
not left to the LLM's prompt, so they hold regardless of what the model
decides to say:

- Any red-flag keyword in the reported symptoms (e.g. "chest pain",
  "difficulty breathing"), age under 2, or symptoms lasting more than 10
  days forces `severity: "urgent"` and a warning to seek in-person care.
- `create_order` refuses any line item where the medication is not OTC and
  no `prescription_id` was supplied.
- Every `assess_symptoms` result carries an explicit disclaimer that it is
  not a medical diagnosis.

## Tools

### `assess_symptoms`

Assess self-reported symptoms; always call before recommending a medication.

| Param | Type | Required | Notes |
|---|---|---|---|
| `symptoms` | `string[]` | yes | e.g. `["runny nose", "sore throat"]` |
| `duration_days` | `integer` | no | default 1 |
| `age` | `integer` | no | default 30 |
| `pregnant` | `boolean` | no | default false |
| `chronic_conditions` | `string[]` | no | e.g. `["hypertension"]` |

Returns `likely_conditions`, `severity` (`mild`/`moderate`/`urgent`),
`red_flags`, `therapeutic_classes`, `advice`, `disclaimer`.

```json
// tools/call params
{ "name": "assess_symptoms", "arguments": { "symptoms": ["runny nose", "sore throat"], "duration_days": 2, "age": 24 } }
```

### `search_medications`

Search the catalog by free text and/or therapeutic class.

| Param | Type | Required |
|---|---|---|
| `query` | `string` | no |
| `therapeutic_class` | `string` | no |
| `otc_only` | `boolean` | no (default `true`) |

### `get_medication_details`

Full monograph for one SKU: dosage, contraindications, side effects,
pregnancy safety, price.

| Param | Type | Required |
|---|---|---|
| `sku` | `string` | yes |

### `check_interactions`

Check candidate SKUs against the patient's current medications and
allergies.

| Param | Type | Required |
|---|---|---|
| `candidate_skus` | `string[]` | yes |
| `current_medications` | `string[]` | no — active ingredients, e.g. `["warfarin"]` |
| `allergies` | `string[]` | no |

Returns `safe_to_recommend`, `blocking[]`, `warnings[]`, `allergy_conflicts[]`.

### `check_stock`

| Param | Type | Required |
|---|---|---|
| `sku` | `string` | yes |
| `branch_id` | `string` | no — omit to check every branch (`zona10`, `zona1`, `mixco`) |

### `create_order`

| Param | Type | Required |
|---|---|---|
| `items` | `{sku: string, quantity: integer}[]` | yes |
| `branch_id` | `string` | yes |
| `fulfillment` | `"pickup"` \| `"delivery"` | no (default `pickup`) |
| `prescription_id` | `string` | no — required for prescription-only items |

Returns the confirmed order (`order_id`, line items, `total`) or a tool
error (`isError: true`) if a prescription is missing or stock is
insufficient.

### `get_order_status`

| Param | Type | Required |
|---|---|---|
| `order_id` | `string` | yes |

## Example: end-to-end tool call

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"check_interactions","arguments":{"candidate_skus":["IBU400"],"current_medications":["warfarin"]}}}
```

```json
{"jsonrpc":"2.0","id":4,"result":{"content":[{"type":"text","text":"{\n  \"safe_to_recommend\": false,\n  \"blocking\": [...]\n}"}],"isError":false}}
```

Note `isError` stays `false` here: the interaction was checked
successfully, it just came back unsafe. `isError: true` is reserved for
tool *execution* failures (unknown SKU, missing prescription, no stock).

## Sample SKUs for testing

`PARA500` (paracetamol, OTC), `IBU400` (ibuprofen, OTC, blocks with
warfarin), `LORA10` (loratadine, OTC), `AMOX500` (amoxicillin,
prescription-only), `WARF5` (warfarin, prescription-only).
