"use client";

import { useEffect, useMemo, useState } from "react";
import type { AgentTrace } from "@/lib/contracts";
import { useFlip } from "./use-flip";

type Phase = "merged" | "linear";

const PHASES: Array<{ id: Phase; label: string }> = [
  { id: "merged", label: "1 · retrieval order" },
  { id: "linear", label: "2 · 16-feature linear rerank" },
];

export function RerankStage({
  trace,
  targetAsin,
  revealed,
}: {
  trace: AgentTrace;
  targetAsin: string | null;
  revealed: boolean;
}) {
  const [phase, setPhase] = useState<Phase>("merged");

  useEffect(() => {
    if (!revealed) {
      setPhase("merged");
      return;
    }
    const toLinear = setTimeout(() => setPhase("linear"), 1200);
    return () => clearTimeout(toLinear);
  }, [revealed, trace]);

  const scores = useMemo(() => {
    const map = new Map<string, number>();
    for (const entry of trace.ranking.linear_scores) {
      map.set(entry.asin, entry.score);
    }
    return map;
  }, [trace]);

  const order = useMemo(() => {
    const source =
      phase === "merged"
        ? trace.retrieval.candidate_asins
        : trace.ranking.linear_ranking;
    const top = source.slice(0, 10);
    if (targetAsin && source.includes(targetAsin) && !top.includes(targetAsin)) {
      return {
        top,
        extra: { asin: targetAsin, rank: source.indexOf(targetAsin) + 1 },
      };
    }
    return { top, extra: null };
  }, [phase, trace, targetAsin]);

  const shownScores = order.top
    .map((asin) => scores.get(asin) ?? 0)
    .concat(order.extra ? [scores.get(order.extra.asin) ?? 0] : []);
  const minScore = Math.min(...shownScores, 0);
  const maxScore = Math.max(...shownScores, 0.0001);
  const normalize = (value: number) =>
    `${Math.round(((value - minScore) / (maxScore - minScore || 1)) * 100)}%`;

  const flipRef = useFlip(phase);

  const row = (asin: string, rankLabel: number, extraNote?: string) => (
    <div
      key={asin}
      ref={flipRef(asin)}
      className={`rerank-row ${asin === targetAsin ? "is-target" : ""}`}
    >
      <span className="rerank-rank">{rankLabel}</span>
      <span className="rerank-asin">
        {asin}
        {asin === targetAsin && <span className="rerank-title"> · target</span>}
        {extraNote && <span className="rerank-title"> · {extraNote}</span>}
      </span>
      <span
        className="score-bar"
        style={
          {
            "--fill": phase === "merged" ? "0%" : normalize(scores.get(asin) ?? 0),
          } as React.CSSProperties
        }
      >
        <span className="fill" />
      </span>
      <span className="rerank-score">
        {phase === "merged" ? "" : (scores.get(asin) ?? 0).toFixed(3)}
      </span>
    </div>
  );

  return (
    <div>
      <div className="rerank-controls" role="tablist">
        {PHASES.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={phase === item.id}
            className={`phase-pill ${phase === item.id ? "active" : ""}`}
            onClick={() => setPhase(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="rerank-list">
        {order.top.map((asin, index) => row(asin, index + 1))}
        {order.extra &&
          row(order.extra.asin, order.extra.rank, "below the top 10")}
      </div>
      <p className="rerank-note">
        {phase === "merged"
          ? "Retrieval order: exact-evidence hits first, then the fused BM25 pool."
          : "A 16-feature linear model covering coverage, constraints, popularity, and exact-evidence rarity rescores all candidates. Watch the rows trade places."}
      </p>
    </div>
  );
}
