# Failsafe Dashboard -- Demo Video Script

Walkthrough for recording a demo of the Failsafe Failsafe dashboard at `http://localhost:8420`. Structured as a top-to-bottom screen tour, followed by four live simulation scenarios. Estimated runtime: 4-6 minutes.

---

## Before You Start

- Run `python dashboard/app.py` and confirm the terminal prints `http://localhost:8420`.
- Open the URL in a browser. The page loads with seed data already populated (11 handoffs, a mix of passes and failures). No login required.
- Maximize the browser window. The layout is single-column, so scrolling top-to-bottom is the natural flow.

---

## Part 1 -- Top-to-Bottom Tour (about 2 minutes)

### Nav Bar

- Point out the **Failsafe** brand mark (top-left) and the green pulsing dot that says "Monitoring" (top-right).
- Say: "This is Failsafe, a contract testing and compliance validation framework for multi-agent AI systems. The green dot means the engine is live and monitoring handoffs between agents in real time."
- Note the right side shows "4 agents, 3 contracts" -- this is the scope of the system.

### Stat Cards (four boxes across the top)

- Hover over each label to show the tooltip that explains it. The tooltips are useful if viewers pause the video.
- Say: "These four numbers give us the overall health at a glance."
  - **Total Handoffs** -- how many data transfers have been validated.
  - **Passed** (green) -- handoffs where data matched the contract schema, authority was sufficient, and no policy rules fired.
  - **Failed** (red) -- handoffs with at least one critical or high severity violation.
  - **Blocked** (amber) -- failed handoffs that were actively prevented from executing. In enforce mode, any critical or high violation blocks the handoff.
- Say: "You can see we already have some failures from the seed data. That is intentional -- it shows the engine catching real problems."

### Agent Pipeline

- Say: "This is the agent workflow. Data flows left to right through four agents."
- Point to each node and explain what it does:
  - **Customer Service (CS)** -- READ_ONLY authority. This is the front door. It handles customer inquiries, looks up accounts, and routes requests. It cannot modify anything or trade.
  - **Research (RA)** -- READ_WRITE authority. This agent analyzes market data, runs portfolio analysis, and generates investment recommendations. It can write recommendations but cannot execute trades on its own.
  - **Trading (TA)** -- EXECUTE authority. The highest operational authority. This is the only agent that can actually execute trades and rebalance portfolios. It takes approved recommendations and acts on them.
  - **Compliance (CA)** -- ADMIN authority. Full access for auditing. It reviews executed transactions against SOX, SEC, FINRA, and PCI-DSS regulations. Think of it as the internal auditor watching everything.
- Point to the arrows between them:
  - **CTR-001** governs Customer Service to Research.
  - **CTR-002** governs Research to Trading.
  - **CTR-003** governs Trading to Compliance.
- Say: "Each arrow is a contract. The contract defines exactly what data fields are allowed, what format they must be in, and what authority level is required. If any agent tries to hand off data that violates its contract, the engine catches it."
- Note: "The arrow colors reflect the last validation result on that edge -- green means pass, red means fail or blocked, gray means idle."

### Simulate Buttons and Custom Handoff Form

- Say: "Below the pipeline we have four pre-built scenarios and a custom handoff form. I will run each scenario in a moment."
- Point out the four buttons: Valid Handoff, SSN Leak, Large Transaction, Authority Escalation.
- Hover over each button briefly so the tooltip appears -- the tooltip explains what each one does.
- Point at the Custom Handoff form:
  - Say: "You can also build your own handoff from scratch. Pick a source agent, a target agent, write a JSON payload, and hit Validate. The engine checks it against the contract schema, authority rules, and the full finance policy pack in real time."

### Top Violations and Agent Activity (side-by-side cards)

- Say: "The left card shows the most frequently triggered rules across all handoffs, ranked by count. Severity badges show critical, high, or medium."
- Say: "The right card is agent activity -- green bars are passes, red bars are failures. You can see at a glance which agents are involved in the most handoffs and where problems concentrate."

### Audit Trail

- Say: "This is the full audit trail. Every validation result, newest first."
- Click on one of the rows to expand it. Point out:
  - The metadata bar at the top of the expanded row: handoff ID, contract ID, validation duration, direction.
  - The **Payload** tab showing the raw JSON data that was handed off.
  - Click the **Violations** tab to see each individual rule that fired, with severity and message.
- Say: "Sub-millisecond validation times. You can inspect every handoff after the fact for auditing or debugging."

### Contracts Section

- Say: "These are the three contract definitions. Each card shows the source and target agents, the required fields with types and patterns, and the compliance scopes."
- Point out a few details on CTR-002 (Research to Trading):
  - `symbol` requires a regex pattern of 1-5 uppercase letters.
  - `amount` is marked as financial data, with a range of 0 to 500,000.
  - `rationale` is a required string, max 1000 characters.
  - Compliance scopes: SOX, SEC, FINRA.
- Say: "These contracts are the source of truth. The engine validates every handoff against them automatically."

### Validation Log (terminal at the bottom)

- Say: "Finally, the terminal log. This is the raw output from the validation engine, formatted like server logs."
- Point out the structure of a log line: timestamp, PASS/FAIL result, agent pair, contract ID, duration in milliseconds.
- Point out the tree-style violations underneath failed entries.
- Point out the payload preview keys at the bottom of each entry.
- Say: "This is what you would see if you were tailing the engine logs in a terminal. Every field is here for forensic review."

---

## Part 2 -- Live Simulations (about 2-3 minutes)

Scroll back up to the Simulate section before starting. After each click, briefly pause so the viewer can see the toast notification (bottom-right corner), then scroll down to the audit trail to show the new row.

### Scenario 1: Valid Handoff

- Click the **Valid Handoff** button (the purple/accent one).
- Say: "This sends a clean portfolio review request from Customer Service to Research. The customer ID matches the CUST-XXXXXX pattern, the request type is one of the allowed enum values, and the account ID matches the expected format."
- A green toast appears: "Valid handoff: Passed -- 0 violations."
- Point out the pipeline arrow between CS and RA turning green.
- Scroll to audit trail and show the new row with a green PASS badge.
- Click the row to expand it. Show the payload. Switch to Violations tab -- it says "No violations."
- Say: "That is the happy path. Schema valid, authority sufficient, no policy rules triggered."

### Scenario 2: SSN Leak

- Click the **SSN Leak** button.
- Say: "Now the Research agent is sending a trade recommendation to Trading, but someone embedded a Social Security Number in the rationale field -- 'Client SSN: 111-22-3333 wants AAPL'."
- A red toast appears.
- Point out the pipeline arrow between RA and TA turning red.
- Scroll to audit trail. Click the new failed row.
- Switch to the Violations tab. Point out the violation:
  - Rule: **FIN-PII-002** (ssn_in_payload)
  - Severity: CRITICAL
  - Message: "SSN pattern detected in field 'rationale'"
- Say: "The engine scans every string field with a regex for SSN patterns. It does not matter where in the payload the SSN appears -- the rationale field, a nested object, an array. It will find it. This handoff is blocked."

### Scenario 3: Large Transaction

- Click the **Large Transaction** button.
- Say: "Research recommends an $80,000 buy of AMZN, but there is no human_approved flag in the metadata."
- A red toast appears.
- Scroll to audit trail and expand the new row.
- Point to the violation:
  - Rule: **FIN-AUTH-003** (large_transaction_no_approval)
  - Severity: HIGH
  - Message: "Transaction amount $80,000.00 exceeds $10,000.00 threshold and requires human approval"
- Say: "The finance policy pack has a $10,000 threshold. Any transaction above that amount requires a human_approved flag in the metadata. Without it, the handoff is blocked. This is a FINRA and SOX compliance requirement."
- Optional: scroll down to the Custom Handoff form. Set amount to 80000, check the "Human approved" checkbox, and click Validate to show that the same handoff passes when approval is present.

### Scenario 4: Authority Escalation

- Click the **Authority Escalation** button.
- Say: "This is the most dangerous scenario. Customer Service tries to send a trade directly to Trading, skipping the Research agent entirely."
- A red toast appears.
- Point out: there is no pipeline arrow between CS and TA because there is no contract for that pair.
- Scroll to audit trail and expand the new row.
- Point to the violations (there will be multiple):
  - **CONTRACT_VIOLATION** -- no contract exists between customer_service and trading_agent.
  - **FIN-AUTH-002** -- trade action requires execute-level authority, but customer_service is READ_ONLY.
  - **FIN-DATA-001** -- financial data being passed to an agent not authorized for financial records.
- Say: "Three violations fire at once. The engine checks contract existence, authority levels, and data domain boundaries independently. Customer Service has READ_ONLY authority and is not authorized to handle financial records. Even if someone bypasses the intended workflow, the engine catches it at every level."

---

## Part 3 -- Custom Handoff (optional, 30 seconds)

If you have time, show a quick custom handoff to demonstrate flexibility:

- In the Custom Handoff form, set From to `research_agent`, To to `trading_agent`.
- In the payload, type something like:
  ```json
  {
    "symbol": "NVDA",
    "action": "buy",
    "amount": 5000,
    "rationale": "Pre-release earnings data suggests strong Q4. Insider sources confirm."
  }
  ```
- Set action to `recommend`. Leave Human approved unchecked.
- Click **Validate Handoff**.
- Say: "This triggers FIN-SEC-001 -- the engine detected keywords like 'pre-release', 'earnings', and 'insider' that indicate potential material non-public information. The SEC requires this to be flagged with an mnpi_reviewed metadata field before it can proceed."
- Point out the result appearing inline below the form.

---

## Closing Statement

- Say: "That is Failsafe Failsafe. Contract testing and compliance validation for multi-agent AI systems. Every handoff between agents is validated against typed schemas, authority levels, and regulatory policy packs -- in sub-millisecond time. The audit trail captures everything for SOX, SEC, FINRA, and PCI-DSS compliance."

---

## Quick Reference -- The 10 Finance Policy Rules

| Rule ID | Name | What it catches | Severity |
|---|---|---|---|
| FIN-PII-001 | pii_exposure_to_unauthorized_agent | PII field passed to agent without PII domain access | CRITICAL |
| FIN-PII-002 | ssn_in_payload | SSN pattern (XXX-XX-XXXX) anywhere in payload | CRITICAL |
| FIN-PII-003 | unmasked_account_number | Raw account number (8+ digits) not masked | HIGH |
| FIN-AUTH-001 | amount_exceeds_agent_limit | Transaction exceeds agent's max_amount domain limit | CRITICAL |
| FIN-AUTH-002 | trade_without_execute_authority | Trade action by agent without execute/admin authority | CRITICAL |
| FIN-AUTH-003 | large_transaction_no_approval | Amount over $10K without human_approved metadata | HIGH |
| FIN-AUDIT-001 | missing_audit_metadata | SOX-required metadata fields (request_id, timestamp, initiator) missing | HIGH |
| FIN-AUDIT-002 | segregation_of_duties_violation | Same agent both approves and executes a transaction | CRITICAL |
| FIN-DATA-001 | financial_data_boundary_violation | Financial data sent to agent without financial_records domain access | CRITICAL |
| FIN-SEC-001 | potential_mnpi_unflagged | Keywords suggesting material non-public info without mnpi_reviewed flag | HIGH |
