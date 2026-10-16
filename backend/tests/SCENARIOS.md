# Deterministic acceptance scenarios

The suite freezes UTC to `2026-10-16 06:00:00`. Default stay: Goa, Nov 10–12, two adults. `search` means `search_properties` → per-room `check_availability` and `calculate_price`. `select` means `check_availability` and `get_room_details` against an existing quote. Tests use the limited parser to isolate state/business-rule correctness from nondeterministic model output. Live extraction quality is evaluated separately by `scripts/live_eval.py`.

| Scenario | Expected state change | Expected tools / business outcome | Executable test |
|---|---|---|---|
| Relative dates | Tomorrow → Oct 17; two nights → Oct 19 | Search for exact frozen-clock dates | `test_relative_dates_frozen` |
| Missing checkout | Preserve arrival and guests; collect departure | No availability or quote yet | `test_missing_checkout_preserves_partial_state` |
| Date change | Invalidate old quote/offer; clear selection/confirmation | Fresh search; old offer expired | `test_date_change_invalidates_quotes_offers` |
| Guest count change | Clear quote; update occupancy | Search filters every room by capacity | `test_guest_count_change_filters_capacity` |
| Budget change | Set all-in budget; filter new cards | Search; every total satisfies hard budget | `test_budget_change_is_hard_constraint` |
| Private pool | Set required amenity | Search cannot substitute shared pool | `test_private_pool_requirement` |
| Unavailable rooms | Do not recommend occupied/closed inventory | Availability subtracts reservations/restrictions | `test_unavailable_seed_reservation_and_closure` |
| Capacity conflict | No matching recommendations | Twelve adults cannot fit any single room | `test_capacity_conflict_returns_no_rooms` |
| Unknown amenity | Keep selected property | `get_policy`: null heating remains unknown | `test_unknown_pool_heating_never_invented` |
| Ambiguous yes | No pending room → no hold | No mutation; ask for selection | `test_ambiguous_yes_cannot_hold` |
| Second option | Select second current quote | Recheck availability; use exact second room | `test_second_option_selects_existing_quote` |
| Too expensive | Create validated automatic offer | Evaluate discount; persist offer | `test_too_expensive_generates_verified_offer` |
| Approved discount | Persist accepted offer; pending confirmation | Hold uses approved amount after confirmation | `test_discount_auto_approval_and_hold` |
| Counteroffer | Persist countered offer | Prohibited low proposal produces permitted amount | `test_counteroffer_never_exposes_policy` |
| Repeated negotiation | Review status; no fraud label | Flag after three offers, create handoff | `test_repeated_negotiation_is_not_fraud` |
| Manager request | Pending human review | Flag and handoff; no fabricated human reply | `test_manager_request_creates_real_handoff` |
| Guest complaint | Pending review | Complaint flag/handoff persisted | `test_rule_escalation` |
| Explicit human | Pending review | Human flag/handoff persisted | `test_rule_escalation` |
| Policy exception | Pending review | Policy exception flag; no unauthorized exception | `test_rule_escalation` |
| Inventory disappears during negotiation | No new offer | Availability failure before discount evaluation | `test_room_disappears_during_negotiation` |
| Quote expiration | Confirmation disabled | No hold from expired quote | `test_expired_quote_blocks_confirmation` |
| Duplicate confirmation | Same response; one hold | Chat idempotency and hold uniqueness | `test_duplicate_confirmation_returns_one_hold` |
| Simultaneous last-unit holds | One success, one unavailable | PostgreSQL row lock prevents overbooking | `test_two_sessions_cannot_hold_last_unit` |
| Concurrent messages in one session | Versions 1 then 2; four messages | PostgreSQL session lock prevents lost updates | `test_same_session_messages_are_serialized` |
| Language timeout | Preserve committed state/version | 503; persisted operational flag/handoff | `test_timeout_preserves_state_records_operational_flag` |
| Read tool timeout | Next action is retry/correct | Exactly two attempts; failed trace and review flag | `test_repeated_read_tool_timeout_escalates` |
| Database failure | No committed booking | Redacted structured 503 | `test_database_failure_structured_error` |
| Prompt injection | Injection intent; no hotel changes | Technical flag, no booking tools | `test_prompt_injection_is_flagged_without_business_tools` |
| Patch semantics | UNSET preserves; SET replaces; CLEAR defaults | No history-based state inference | `test_patch_semantics` |
| Checkout exclusive | Departing reservation frees arrival date | Availability succeeds on previous checkout night | `test_checkout_exclusive` |
| Tax and paid add-ons | Quote contains full breakdown | Integer prices + Decimal rounding; ₹13,664 total | `test_price_uses_minor_units_tax_and_addons` |
| Manager authorization | Guest token cannot approve | Admin endpoint rejects without separate secret | `test_guest_api_session_isolation_and_admin_auth` |
| Actual manager approval | Offer accepted; pending hold | Approval persists, hold uses exact approved total | `test_manager_approval_persists_and_controls_price` |
| Stale approval | Changed requirement expires offer | Manager approval returns 409 | `test_stale_manager_offer_cannot_be_approved` |
| Browser/session restoration | Same authoritative state/history | Authenticated GET returns persisted records | `test_persistent_state_and_history` |
| State version conflict | Preserve current state | 409 on stale expected_version | `test_version_conflict` |
| Reused key, different body | Preserve first response | 409 on altered payload | `test_idempotency_key_cannot_change_message` |
| Per-session rate limit | Do not advance state | 429 with retry header | `test_rate_limit` |
| Unsupported free breakfast | No invented concession | Explain limitation, create review record | `test_free_breakfast_cannot_be_promised` |
| Ambiguous negotiation basis | Preserve quote; no offer | Ask nightly versus total | `test_ambiguous_offer_basis_asks_question` |
| Redacted traces | No personal requests in logs | Correlation ID and safe tool summaries | `test_trace_redacts_special_requests` |
| Missing live key | Preserve state | Explicit 503; never simulated AI response | `test_no_live_model_key_fails_honestly` |
| Threshold rounding | Do not round a violation into approval | One paise over each boundary follows stricter rule | `test_threshold_comparisons_do_not_round_into_approval` |
| Expired hold | Release occupied inventory | Availability ignores expired hold | `test_expired_holds_release_inventory` |
| Past dates | No recommendations | Deterministic validation rejects past arrival | `test_past_dates_are_rejected` |
| Inconsistent child ages | No quote | Reject partial/inconsistent supplied ages | `test_child_age_validation` |
| Paid breakfast request | Invalidate offer/quote; preserve add-on selection | Search reprices matching property rooms and taxes | `test_paid_breakfast_reprices_and_invalidates_previous_offer` |

All tests assert useful state or business outcomes. PostgreSQL-only cases explicitly skip on SQLite; an SQLite pass is never presented as proof of concurrent safety. UI checks, including genuine manager approval and a real hold, are covered in `scripts/browser-smoke.mjs` and a separately generated browser report.

The refactored conversation boundary is covered separately in `test_agent_contracts.py`, `test_state_updates.py`, and `test_llm_agent.py`: strict schemas/allowlisted arguments; paraphrased negotiation; mixed selection, paid breakfast and negotiation; prior numbered policy references; explicit clearing; relative arithmetic; ambiguity without mutations; small talk; exact percentage calculations; manager authority; semantic complaints/handoff/injection; timeouts, schema repairs, and authentication failures; bounded replanning; transaction rollback; scoped recent context; factual response references; preserved receipts after a response outage; abusive language versus ordinary frustration; and safe references through quote invalidation. These tests mock model outputs rather than claiming to measure live language quality.

`test_cancellation.py` checks inventory release, preserved requirements, repeat requests, persistence, policy questions without cancellation, explicit authorization, cross-session rejection, and expired-hold handling. Live semantic, feature, browser and load results remain separate in `reports/` and are summarized in `REFACTOR_REPORT.md`.
