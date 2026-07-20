# Integrated agent pipeline

Process every contract from the configured database source. The runtime has no
mock-data fallback; a database error stops the run:

```bash
python3 -m app.Agent.pipeline
```

Evaluate one externally uploaded contract while still loading the normal source
as portfolio context:

```bash
python3 -m app.Agent.pipeline \
  --input decision_agent_sample/sample_data/new_contract_upload.json \
  --reference-date 2026-07-18
```

The upload JSON is the contract object itself; it has no package wrapper. The
application merges it into an in-memory copy for this run and does not insert it
into the normal contract table.

The accepted upload contract contains exactly these fields:

```text
contract_id, customer_id, start_date, end_date, status, description,
contract_value, gross_margin, payment_terms, requested_amount,
funding_need_type, tenor
```

Precomputed risk fields are intentionally rejected. Risk evidence must come from
the authoritative portfolio/risk sources or be reported as insufficient.

The orchestrator allocates one PostgreSQL `bigint` session id before execution,
then calls `Runner.run()` once. SDK handoffs are wired as:

```text
Finance_Agent --{session_id}--> Risk_Agent --{session_id}--> Decision_Agent
```

Business packs do not travel in handoff tool arguments. Finance inserts one
`FinanceBatchPack` into `context.finance_pack`; Risk reads it by id and updates
one `RiskBatchPack`; Decision reads both and updates `decision_pack`. `LogsAgent`
stores operational logs only.

Approval continuation remains separate:

```bash
python3 -m app.service.approval <session_id> <approval_id> accept
python3 -m app.service.approval <session_id> <approval_id> reject
```

The continuation reloads the saved Decision conversation and may update only the
approved contract card. It never reruns Finance or Risk.
