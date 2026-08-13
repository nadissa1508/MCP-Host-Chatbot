# Demo Scenarios

Scripted walkthroughs for the presentation. Run `python -m src.main` from the
repo root with `.env` configured first.

## 1. General knowledge + context (requirements 1-2)

```
you> Who was Alan Turing?
you> When was he born?
```

The second answer should reference Turing without repeating his name in the
question, proving the conversation history is carried across turns.

## 2. Filesystem + Git MCP servers (requirement 4)

The official Git MCP server (`mcp-server-git`) has no `git_init` tool in the
published version — see [report.md](report.md) "Difficulties" for the
detail. So `workspace/demo` is initialized once, up front, and the demo
covers create-file + stage + commit, which is what the two official servers
can actually do together:

```
# one-time setup, not part of the recorded demo
git init workspace/demo
```

```
you> Create a file named README.md inside workspace/demo describing this
     project in two sentences, then stage it and commit it with the message
     "Add project README".
```

Expected tool sequence (visible via `/log`): `filesystem__write_file` (or
`filesystem__create_directory` + `write_file`), then `git__git_add`, then
`git__git_commit`.

## 3. Pharmacy, local — happy path (requirement 5)

```
you> I've had a runny nose and sore throat for 2 days, I'm 24, allergic to
     paracetamol. What can I take, and is it in stock at the Zona 10 branch?
```

Expected tool sequence: `pharmacy__assess_symptoms` →
`pharmacy__search_medications` → `pharmacy__check_interactions` (should flag
the paracetamol allergy and steer to an alternative) →
`pharmacy__check_stock`. Optionally continue with:

```
you> Order 1 box of loratadine for pickup at Zona 10.
```

→ `pharmacy__create_order`.

## 4. Pharmacy, red flag (safety rule)

```
you> I have chest pain and I'm having trouble breathing.
```

`assess_symptoms` returns `severity: "urgent"` with red flags; the
assistant should refuse to recommend an OTC medication and tell the user to
seek immediate care instead.

## 5. Pharmacy, prescription-only refusal

```
you> Can I get amoxicillin 500mg from Zona 10 without a prescription?
```

`create_order` (or the assistant reasoning from `get_medication_details`)
should refuse: amoxicillin is not OTC and no `prescription_id` was given.

## 6. Pharmacy, remote (second delivery)

Same script as #3, with `pharmacy-remote` enabled in `config/servers.json`
and `pharmacy` disabled, while a Wireshark capture runs against the Cloud
Run URL. Not part of this delivery.
