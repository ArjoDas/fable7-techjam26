# Natural language → structured retrieval

The serving implementation is `search_runtime/translate.py` and `search_runtime/intent.py`. The frontend no longer calls the historical `extension/matrix/translate.py` or its older independent semantic mapper. The isolated `search_runtime` package mirrors the tested runtime from `extension-updated`; historical experiment files remain untouched under `extension`. `api/semantic.py` formats diagnostics; it does not interpret queries. Both frontend modes call the shared wrapper, including when the legacy `semantic` request flag is false.

## 1. Build an active vocabulary from the catalog

`Converter.refresh()` derives categories and evidence values using the same catalog-side intent-card construction as the evaluator. It processes every **active product**, not the current target. Values retain punctuation and units. Token postings find literal evidence spans; per-category reference counts restrict semantic candidates to active evidence. Catalog versions identify additions/removals, so later refreshes touch affected products only. Deleted evidence disappears when its last supporting product disappears.

This is preprocessing from public product metadata. The serving converter never receives a target ASIN, a simulator's hidden card, undisclosed preferences, the original constrained sentence, or a paraphrase-bank lookup key.

## 2. Check the original protocol first

`ProtocolGuard._protocol()` checks the full turn form, turn sequence, previous requested attribute, category, and compatible catalog evidence. A valid original turn is sent unchanged to main. No MiniLM initialization or encoding occurs on that path.

## 3. Parse actions and literal evidence

For a natural turn, the wrapper copies the session's `ShoppingState` before making changes. Rules recognize browsing/buying transitions, corrections, category changes, missing preferences, and exclusions. Category phrases come from the active catalog. Material words do not become category labels just because they are materials.

Literal evidence is matched first. Full matched evidence spans are protected before splitting clauses, so punctuation and conjunctions inside an actual feature do not break it into invented preferences. Category-only request clauses such as “Can you find …?” are not interpreted as product attributes.

Constraints carry `attribute`, `value`, `negative`, and originating `turn`. Known attribute labels and a small color/material vocabulary support replacement. A partial correction replaces the affected attribute while keeping other preferences. A category change clears the previous category's constraints. Explicit replacement of the earlier opening preference retires that opening constraint. Retired constraints remain in `history` with a replacement turn.

These are rules, not a learned intent classifier. Unusual reference resolution, comparisons, ranges, and complex negation are not generally solved.

## 4. Use MiniLM for unresolved phrases

When rules cannot map an eligible phrase literally, the converter supplies a bounded list of active evidence strings. Values are shortlisted through token postings and short values from the current category, capped at 256. Category normalization also compares a bounded active-category list. This shortlist can miss the right value; MiniLM does not search an unlimited vocabulary.

The local quantized all-MiniLM-L6-v2 ONNX encoder tokenizes each phrase, mean-pools token embeddings with the attention mask, and L2-normalizes the resulting 384-dimensional vector. A dot product gives cosine similarity. It is a scoring encoder, not a generative model and does not produce JSON itself.

A mapping is accepted only when the best cosine is at least **0.65**, exceeds the runner-up by at least **0.05**, and preserves the extracted numeric sequence. Equivalent duplicate representations such as `blue` and `color: blue` are collapsed before the margin check. These thresholds are conservative heuristics, not proof of semantic equivalence; units and subtle meaning still require evaluation.

Text embeddings are cached locally. An unchanged evidence string can reuse its vector after deletion/reintroduction. New or changed text is encoded lazily; weights are never retrained. No Qwen process, external model API, or API key is used. The conversion deadline is checked between synchronous encoding batches and cannot forcibly interrupt an ONNX batch.

## 5. Choose the retrieval path

When the parsed turn has a faithful constrained representation—one opening value, an ordinary disclosure, a supported override, or a no-preference reply—the wrapper renders the observed values in their observed order using the official templates. It then validates that rendered turn against the ongoing protocol and active evidence. Only if validation succeeds does it delegate through main's complete lexical/exact retrieval, linear reranking, dialogue-card matching, and output policy (`translated-protocol`). It never pads the conversation with undisclosed values to manufacture a prefix.

For richer state changes, the wrapper renders the active positive constraints for main's general lexical retrieval and linear reranker, with dialogue-card matching disabled (`minilm-rules` or `rules-state`). Negative constraints are enforced separately. Candidate recommendations are rechecked against active category, catalog evidence, exclusions, and availability. This path can rank differently from protocol-card matching.

If parsing or mapping is uncertain, throws an error, or exceeds the conversion budget, the tentative state is rolled back. The raw turn goes through general lexical fallback with the last understood preferences, and the response asks for clarification. Uncertain mapping is not silently treated as a successful normalization.

## Example state transition

A measured example is `public_0002` from the frozen-catalog wording evaluation:

```text
Customer: Can you find Accessories Belts? I prefer Buckle closure.
Canonical: I'm looking for accessories belts. buckle closure
```

The actual internal event was:

```json
{"kind":"opening_old","category":"accessories belts","values":["buckle closure"],"attribute":""}
```

It used `translated-protocol` with zero model calls because both category and value matched literal catalog evidence. A natural sentence does not necessarily require a semantic encoder. This is an observed turn, not a hypothetical MiniLM success.

`I need shirts. I prefer red and cotton.` produces positive `color=red` and `material=cotton` constraints. `Keep cotton, make it blue instead.` replaces red with blue and keeps cotton:

```json
{
  "category": "shirts",
  "mode": "buying",
  "event": "correction",
  "constraints": [
    {"attribute": "material", "value": "cotton", "negative": false, "turn": 2},
    {"attribute": "color", "value": "blue", "negative": false, "turn": 2}
  ]
}
```

Repeated “keep cotton” records its latest confirming turn. If the user instead says `not red`, the value is stored with `negative=true` and excluded from results; it is not rendered as a positive requirement. `Forget shirts. I want shoes instead.` changes category and retires the old constraints. These examples require corresponding categories/evidence in the active catalog.

## Frontend integration

`AgentRuntime` owns the catalog, shared wrapper, and base agent on its single SQLite-owning worker thread. Session reset/close/respond all go through the wrapper. Structured turns retain the existing funnel traces; natural turns add conversion/state diagnostics under `trace.extension` and a display projection under `trace.semantic`. The final selected IDs in the UI trace reflect availability/constraint filtering. Existing `page.tsx` and CSS edits are preserved.

See `frozen-catalog-verification.md` for measured accuracy, retained raw turn files, commands, and failed gates. Public-task paraphrases are historical regression evidence, not a sealed test or a claim about arbitrary natural language.
