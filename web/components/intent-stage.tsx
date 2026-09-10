"use client";

import type { AgentTrace } from "@/lib/contracts";

export function IntentStage({ trace }: { trace: AgentTrace }) {
  const browsing = trace.conversation.exploratory;
  const matches = trace.ranking.dialogue_match_count;
  const overloaded = matches !== null && matches > 1;
  return (
    <div>
      <div className="verdict-row">
        <div className={`verdict-card ${!browsing ? "chosen" : ""}`}>
          <div className="verdict-name">Buying</div>
          <div className="verdict-note">
            Precision retrieval, popularity prior on
          </div>
        </div>
        <div className={`verdict-card ${browsing ? "chosen" : ""}`}>
          <div className="verdict-name">Browsing</div>
          <div className="verdict-note">
            Recall retrieval, exploratory ranking
          </div>
        </div>
      </div>
      <div className="badge-row">
        <span className="badge info">mode: {trace.conversation.intent_mode}</span>
        <span className="badge">
          {trace.conversation.protocol_compatible
            ? "protocol dialogue"
            : "lexical fallback"}
        </span>
        {trace.conversation.intent_switched && (
          <span className="badge info">intent switched this turn</span>
        )}
        {trace.conversation.override_seen && (
          <span className="badge warn">override: earlier preference dropped</span>
        )}
        {trace.conversation.boundary_seen && (
          <span className="badge warn">boundary: user deferred a choice</span>
        )}
        {overloaded && (
          <span className="badge warn">
            intent overload: {matches} products still match every clue
          </span>
        )}
        {matches === 1 && (
          <span className="badge info">clues now identify exactly 1 product</span>
        )}
        {trace.query.category_applied && (
          <span className="badge">
            category scope: {trace.query.category}
            {trace.query.category_count !== null
              ? ` (${trace.query.category_count.toLocaleString()} products)`
              : ""}
          </span>
        )}
      </div>
    </div>
  );
}
