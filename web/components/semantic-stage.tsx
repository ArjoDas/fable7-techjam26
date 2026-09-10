"use client";

import type { AgentTrace, SemanticTrace } from "@/lib/contracts";
import { AnnotatedMessage } from "./query-stage";

function percent(score: number): string {
  return `${Math.round(Math.max(0, Math.min(1, score)) * 100)}%`;
}

export function SemanticStage({
  trace,
  semantic,
}: {
  trace: AgentTrace;
  semantic: SemanticTrace;
}) {
  const usedCanonical = Boolean(semantic.canonical_message);
  return (
    <div>
      <div className="semantic-grid">
        <div className="semantic-column">
          <div className="column-title">Closest catalog categories</div>
          {semantic.category_candidates.length === 0 && (
            <div className="match-row">
              <span className="match-value" style={{ color: "var(--ink-soft)" }}>
                {semantic.no_preference || semantic.buy_switch
                  ? "not needed for this message"
                  : "no category expressed this turn"}
              </span>
            </div>
          )}
          {semantic.category_candidates.map((candidate) => (
            <div
              key={candidate.category}
              className={`match-row ${
                candidate.category === semantic.chosen_category ? "chosen" : ""
              }`}
            >
              <span className="match-value">{candidate.category}</span>
              <span
                className="match-bar"
                style={{ "--fill": percent(candidate.score) } as React.CSSProperties}
              >
                <span className="fill" />
              </span>
              <span className="match-score">{candidate.score.toFixed(2)}</span>
            </div>
          ))}
        </div>
        <div className="semantic-column">
          <div className="column-title">Closest catalog keywords</div>
          {semantic.value_candidates.length === 0 && (
            <div className="match-row">
              <span className="match-value" style={{ color: "var(--ink-soft)" }}>
                no constraint keywords matched
              </span>
            </div>
          )}
          {semantic.value_candidates.slice(0, 6).map((candidate) => (
            <div
              key={candidate.value}
              className={`match-row ${
                semantic.chosen_values.includes(candidate.value) ? "chosen" : ""
              }`}
            >
              <span className="match-value" title={candidate.value}>
                {candidate.value}
              </span>
              <span
                className="match-bar"
                style={{ "--fill": percent(candidate.score) } as React.CSSProperties}
              >
                <span className="fill" />
              </span>
              <span className="match-score">{candidate.score.toFixed(2)}</span>
            </div>
          ))}
        </div>
        <div className="canonical-out">
          <div className="column-title">
            {usedCanonical
              ? "Structured message handed to the agent"
              : "No confident match — raw text goes to the lexical funnel"}
          </div>
          <p className="canonical-message">
            <AnnotatedMessage
              message={trace.message}
              annotations={trace.query_annotations}
            />
          </p>
        </div>
      </div>
      <div className="semantic-note">
        {semantic.encoder_used
          ? "similarity = lexical overlap blended with MiniLM cosine (local ONNX encoder)"
          : `lexical overlap only — encoder unavailable${
              semantic.encoder_error ? ` (${semantic.encoder_error})` : ""
            }`}
        {semantic.browsing && " · browsing tone detected"}
        {semantic.override && " · override detected"}
        {semantic.no_preference && " · no-preference detected"}
        {semantic.buy_switch && " · buying switch detected"}
      </div>
    </div>
  );
}
