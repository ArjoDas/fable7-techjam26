import type { AgentTrace } from "@/lib/contracts";

function count(value: number | null): string {
  return value === null ? "—" : new Intl.NumberFormat("en-US").format(value);
}

export function TracePanel({ trace }: { trace: AgentTrace | null }) {
  if (!trace) {
    return (
      <aside className="trace-panel">
        <span className="section-label">Pipeline inspector</span>
        <div className="trace-empty">
          <span>↳</span>
          <p>Choose an opening message to reveal the retrieval path.</p>
        </div>
      </aside>
    );
  }

  const special = trace.selection.ambiguity_abstention_used
    ? "The agent returned a smaller slate because several products remain observationally similar."
    : trace.selection.opening_abstention_used
      ? "The opening slate was intentionally reduced to earn another useful constraint."
      : trace.selection.coverage_rotation_used
        ? "Previously shown products rotated out to expose fresh coverage."
        : "The highest-ranked eligible products were returned directly.";

  return (
    <aside className="trace-panel">
      <div className="trace-title-row">
        <div>
          <span className="section-label">Pipeline inspector</span>
          <h2>{trace.conversation.intent_mode}</h2>
        </div>
        <span className={trace.conversation.protocol_compatible ? "status-badge compatible" : "status-badge fallback"}>
          {trace.conversation.protocol_compatible ? "Protocol path" : "Lexical fallback"}
        </span>
      </div>

      <div className="trace-section">
        <h3>Query understanding</h3>
        <dl className="trace-list">
          <div><dt>Category</dt><dd>{trace.query.category || "Global catalog"}</dd></div>
          <div><dt>Category filter</dt><dd>{trace.query.category_applied ? "Applied" : "Fail-open"}</dd></div>
          <div><dt>Override</dt><dd>{trace.conversation.override_seen ? "Seen" : "No"}</dd></div>
        </dl>
        <div className="chip-list">
          {trace.query.constraints.length ? trace.query.constraints.map((item) => <span key={item}>{item}</span>) : <span className="muted-chip">No hard constraints yet</span>}
        </div>
      </div>

      <div className="trace-section">
        <h3>Candidate lanes</h3>
        <div className="metric-grid">
          <div><span>Category</span><strong>{count(trace.query.category_count)}</strong></div>
          <div><span>BM25</span><strong>{count(trace.retrieval.bm25_count)}</strong></div>
          <div><span>Exact evidence</span><strong>{count(trace.retrieval.exact_evidence_count)}</strong></div>
          <div><span>Merged</span><strong>{count(trace.retrieval.merged_count)}</strong></div>
          <div><span>Linear rank</span><strong>{count(trace.ranking.linear_count)}</strong></div>
          <div><span>Dialogue match</span><strong>{count(trace.ranking.dialogue_match_count)}</strong></div>
        </div>
      </div>

      <div className="trace-section">
        <h3>Decision</h3>
        <p className="decision-copy">{special}</p>
        <div className="ranking-head">
          {trace.ranking.dialogue_head.slice(0, 5).map((asin, index) => (
            <div key={asin}><span>{index + 1}</span><code>{asin}</code></div>
          ))}
        </div>
      </div>
    </aside>
  );
}

