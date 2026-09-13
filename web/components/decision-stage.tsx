"use client";

import { useState } from "react";
import { ProductPreview } from "./product-preview";
import type { AgentTrace, ProductCard, TurnResponse } from "@/lib/contracts";

function decisionCopy(
  trace: AgentTrace,
  targetShownFirst: boolean,
): { word: string; tone: string; explain: string } {
  const selection = trace.selection;
  if (selection.decision === "rotation") {
    return {
      word: "Rotate",
      tone: "rotation",
      explain:
        "The query gained no new evidence this turn, so instead of repeating itself the agent skips everything already shown and surfaces the next unseen candidates.",
    };
  }
  if (selection.decision === "abstain_1") {
    if (targetShownFirst) {
      return {
        word: "Best pick, then ask",
        tone: "abstain",
        explain:
          "The agent leads with its single strongest candidate, which is already the target, and asks one clarifying question to be certain before committing a full list.",
      };
    }
    return {
      word: "Ask before guessing",
      tone: "abstain",
      explain: selection.opening_abstention_used
        ? "One clue is not enough to fill ten slots honestly, so the agent shows its single best candidate and asks for another requirement."
        : "Several products still match every disclosed clue, so the agent shows one candidate and asks a clarifying question instead of padding the list.",
    };
  }
  return {
    word: "Top 10",
    tone: "top",
    explain:
      "The evidence now separates the candidates, so the agent releases its full ranked window.",
  };
}

export function DecisionStage({
  trace,
  response,
  targetAsin,
}: {
  trace: AgentTrace;
  response: TurnResponse;
  targetAsin: string | null;
}) {
  const [preview, setPreview] = useState<ProductCard | null>(null);
  const targetShownFirst =
    targetAsin !== null &&
    response.recommendations[0]?.parent_asin === targetAsin;
  const copy = decisionCopy(trace, targetShownFirst);
  return (
    <div>
      <div className="decision-banner">
        <span className={`decision-word ${copy.tone}`}>{copy.word}</span>
        <span className="decision-explain">{copy.explain}</span>
      </div>
      {trace.selection.decision === "rotation" &&
        trace.selection.rotation_skipped.length > 0 && (
          <div>
            <div className="control-label">already shown, skipped this turn</div>
            <div className="rotation-skipped">
              {trace.selection.rotation_skipped.slice(0, 10).map((asin) => (
                <span key={asin} className="skipped-chip">
                  {asin}
                </span>
              ))}
            </div>
          </div>
        )}
      <div className="product-grid">
        {response.recommendations.map((product: ProductCard, index: number) => (
          <button
            type="button"
            aria-haspopup="dialog"
            aria-label={`Preview ${product.title}`}
            onClick={() => setPreview(product)}
            key={product.parent_asin}
            className={`product-card ${
              product.parent_asin === targetAsin ? "is-target" : ""
            }`}
            style={{ "--delay": `${index * 90}ms` } as React.CSSProperties}
          >
            {product.parent_asin === targetAsin && (
              <span className="card-target-tag">target</span>
            )}
            <span className="card-rank">{index + 1}</span>
            <span className="card-title">{product.title}</span>
            <span className="card-meta">
              {product.parent_asin}
              {product.price !== null && ` · $${product.price.toFixed(2)}`}
              {product.average_rating !== null &&
                ` · ★ ${product.average_rating.toFixed(1)}`}
            </span>
            {product.store && <span className="card-meta">{product.store}</span>}
            <span className="card-preview-hint">View catalog details ↗</span>
          </button>
        ))}
      </div>
      {preview && <ProductPreview product={preview} onClose={() => setPreview(null)} />}
      <p className="assistant-line">
        Agent: &ldquo;{response.assistant.message}&rdquo;
      </p>
    </div>
  );
}
