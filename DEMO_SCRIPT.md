# Five-minute demo

Preparation: start the Compose stack; configure an OpenAI key for AI mode or explicitly announce the limited offline mode. Keep the admin token available. Dates below are future as of October 16, 2026; advance them if needed. Start a fresh session so another demo hold does not occupy the single villa.

**0:00–0:45 · A real search.**

“Goa 2026-11-10 to 2026-11-12 for 2 adults, private pool.” Show the verified cards and tax-inclusive stay totals. Open Tool activity: availability queries run for every night and prices are calculated from database rows. All hotels/prices/rules are fictional.

**0:45–1:20 · Requirements change.**

“What about the second option?” Then “Actually 5 adults.” Show occupancy change, cleared selection/offer, and newly filtered cards. Private-pool capacity leaves Lagoon House's five-person residence. Select the first current option. Explain that old quotes are invalid rather than silently reused.

**1:20–2:00 · Grounded support and persistence.**

“Is the pool heated?” Mira cannot confirm an unrecorded fact. Reload the browser. Messages and requirements persist. The browser retains a session bearer token; authoritative state lives in PostgreSQL, not chat history or a worker’s memory.

**2:00–3:15 · Negotiation and real approval.**

The Lagoon Pool Residence quote is ₹47,040 for two nights, including fictional tax. Ask “Make it ₹43500 total stay.” This needs manager review. Show the pending offer and review event. Open Demo manager, enter the separate token, and approve the offer. Refresh or send the next confirmation after approval. No assistant-generated message can approve the discount.

If using the default simple two-person Casa option instead, the two-night total is ₹10,752 and “Make it ₹9900 total stay” triggers the same review path. Always read the current card first rather than relying on an unavailable room.

**3:15–4:00 · A meaningful escalation.**

“I need a policy exception.” Show the persisted guest-safe review status and the manager’s concrete reason/category. Mira reports marked for review without inventing a human reply or promising a response time. Resolving the flag is a real admin action.

**4:00–4:40 · Temporary hold.**

“Confirm hold.” The server validates the current quote, approved offer, and every inventory night while holding a PostgreSQL inventory lock. Show hold ID, discounted total, and expiry. Emphasize: temporary hold, no confirmed reservation, no payment. Repeat the same HTTP request/key in API docs to demonstrate identical idempotent response if desired.

**4:40–5:00 · Evidence.**

Show reports/evaluation.json, the PostgreSQL last-unit concurrency test, and the measured load-smoke report. Distinguish deterministic business-rule results from optional live-model accuracy and from unverified Docker execution. The UI shows structured state and traces only, never hidden chain of thought.
