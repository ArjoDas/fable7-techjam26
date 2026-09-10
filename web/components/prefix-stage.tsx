"use client";

import { useEffect, useMemo, useState } from "react";
import type { AgentTrace } from "@/lib/contracts";
import { useFlip } from "./use-flip";

/**
 * Ordered evidence-prefix index: (category, clue 1, clue 2, …) → matching
 * products, looked up over the whole catalog and promoted above the learned
 * ranking.
 */
export function PrefixStage({
  trace,
  targetAsin,
  revealed,
}: {
  trace: AgentTrace;
  targetAsin: string | null;
  revealed: boolean;
}) {
  const prefix = trace.ranking.prefix;
  const [hoisted, setHoisted] = useState(false);

  useEffect(() => {
    if (!revealed) {
      setHoisted(false);
      return;
    }
    const timer = setTimeout(() => setHoisted(true), 1200);
    return () => clearTimeout(timer);
  }, [revealed, trace]);

  const linearRankOf = useMemo(() => {
    const map = new Map<string, number>();
    trace.ranking.linear_ranking.forEach((asin, index) => {
      map.set(asin, index + 1);
    });
    return map;
  }, [trace]);

  const order = useMemo(() => {
    const source = hoisted
      ? trace.ranking.dialogue_ranking
      : trace.ranking.linear_ranking;
    const top = source.slice(0, 10);
    if (targetAsin && source.includes(targetAsin) && !top.includes(targetAsin)) {
      return {
        top,
        extra: { asin: targetAsin, rank: source.indexOf(targetAsin) + 1 },
      };
    }
    return { top, extra: null };
  }, [hoisted, trace, targetAsin]);

  const flipRef = useFlip(hoisted);

  if (!prefix) {
    return (
      <p className="rerank-note">
        This turn ran outside the structured dialogue protocol, so the prefix
        index is skipped and the learned ranking stands unchanged.
      </p>
    );
  }

  const hasKey = Boolean(prefix.category) && prefix.values.length > 0;
  const matchSet = new Set(prefix.matches);

  return (
    <div>
      <div className="prefix-key">
        <span className="prefix-crumb category">
          {prefix.category || "no category"}
        </span>
        {prefix.values.map((value, index) => (
          <span key={`${value}-${index}`} className="prefix-crumb-wrap">
            <span className="prefix-arrow">›</span>
            <span className="prefix-crumb">{value}</span>
          </span>
        ))}
        {!hasKey && (
          <span className="prefix-crumb empty">
            {prefix.category
              ? "no clues disclosed yet; the lookup needs at least one"
              : "no category parsed; lookup unavailable"}
          </span>
        )}
      </div>

      <div className="prefix-result">
        <div className="merge-count">
          <div className="big">{prefix.match_count}</div>
          <div className="small">
            product{prefix.match_count === 1 ? "" : "s"} match the full prefix
          </div>
        </div>
        <div>
          {prefix.match_count > 0 ? (
            <>
              <span className="lane-dots">
                {prefix.matches.slice(0, 80).map((asin, index) => (
                  <span
                    key={asin}
                    className={`dot fused ${
                      asin === targetAsin ? "is-target" : ""
                    }`}
                    style={
                      { "--delay": `${index * 14}ms` } as React.CSSProperties
                    }
                    title={asin}
                  />
                ))}
              </span>
              <p className="rerank-note" style={{ marginTop: 10 }}>
                Prefix matches are looked up across the <strong>whole
                catalog</strong>, not just the 80-candidate pool, ordered by
                popularity, and promoted above the learned ranking.
                {prefix.match_count === 1 &&
                  " A unique match means the agent can commit."}
                {prefix.match_count > 1 &&
                  " More than one match keeps the ambiguity abstention armed."}
              </p>
            </>
          ) : (
            <p className="rerank-note">
              {hasKey
                ? "No product's disclosed-clue sequence starts with this exact ordered prefix, so the learned ranking stands."
                : "Without a category and at least one clue there is nothing to look up."}
            </p>
          )}
        </div>
      </div>

      {prefix.match_count > 0 && (
        <>
          <div className="rerank-controls" role="tablist" style={{ marginTop: 16 }}>
            <button
              role="tab"
              aria-selected={!hoisted}
              className={`phase-pill ${!hoisted ? "active" : ""}`}
              onClick={() => setHoisted(false)}
            >
              before hoist
            </button>
            <button
              role="tab"
              aria-selected={hoisted}
              className={`phase-pill ${hoisted ? "active" : ""}`}
              onClick={() => setHoisted(true)}
            >
              after hoist
            </button>
          </div>
          <div className="rerank-list">
            {order.top.map((asin, index) => {
              const isMatch = matchSet.has(asin);
              const promoted =
                hoisted &&
                isMatch &&
                (linearRankOf.get(asin) ?? Infinity) > index + 1;
              return (
                <div
                  key={asin}
                  ref={flipRef(asin)}
                  className={`rerank-row ${
                    asin === targetAsin ? "is-target" : ""
                  } ${hoisted && isMatch ? "hoisted" : ""}`}
                >
                  <span className="rerank-rank">{index + 1}</span>
                  <span className="rerank-asin">
                    {asin}
                    {asin === targetAsin && (
                      <span className="rerank-title"> · target</span>
                    )}
                    {promoted && (
                      <span className="rerank-title">
                        {" "}
                        · promoted from #{linearRankOf.get(asin) ?? "80+"}
                      </span>
                    )}
                    {hoisted && isMatch && !promoted && (
                      <span className="rerank-title"> · prefix match</span>
                    )}
                  </span>
                  <span />
                  <span />
                </div>
              );
            })}
            {order.extra && (
              <div
                key={order.extra.asin}
                ref={flipRef(order.extra.asin)}
                className="rerank-row is-target"
              >
                <span className="rerank-rank">{order.extra.rank}</span>
                <span className="rerank-asin">
                  {order.extra.asin}
                  <span className="rerank-title"> · target (below the top 10)</span>
                </span>
                <span />
                <span />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
