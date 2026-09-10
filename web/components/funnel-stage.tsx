"use client";

import type { AgentTrace, RouteTrace } from "@/lib/contracts";

const ROUTE_LABELS: Record<string, { label: string; note: string }> = {
  conjunctive: { label: "BM25 · AND", note: "all terms required" },
  phrase: { label: "BM25 · phrases", note: "adjacent bigrams" },
  disjunctive: { label: "BM25 · OR", note: "any term" },
  popularity: { label: "Popularity prior", note: "buying mode only" },
};

function Dots({
  asins,
  cap,
  targetAsin,
  variant,
}: {
  asins: string[];
  cap: number;
  targetAsin: string | null;
  variant?: string;
}) {
  const shown = asins.slice(0, cap);
  const targetVisible = targetAsin !== null && shown.includes(targetAsin);
  const targetBeyond =
    targetAsin !== null && !targetVisible && asins.includes(targetAsin);
  return (
    <span className="lane-dots">
      {shown.map((asin, index) => (
        <span
          key={asin}
          className={`dot ${variant ?? ""} ${
            asin === targetAsin ? "is-target" : ""
          }`}
          style={{ "--delay": `${index * 10}ms` } as React.CSSProperties}
          title={asin}
        />
      ))}
      {targetBeyond && (
        <span
          className="dot is-target"
          style={{ "--delay": `${shown.length * 10}ms` } as React.CSSProperties}
          title={targetAsin ?? undefined}
        />
      )}
    </span>
  );
}

export function FunnelStage({
  trace,
  targetAsin,
}: {
  trace: AgentTrace;
  targetAsin: string | null;
}) {
  const routes: RouteTrace[] = trace.retrieval.routes ?? [];
  return (
    <div>
      <div className="lane-grid">
        <div className="lane exact">
          <span className="lane-name">
            Exact evidence
            <span className="lane-weight">verbatim catalog values</span>
          </span>
          <Dots
            asins={trace.retrieval.exact_asins}
            cap={60}
            targetAsin={targetAsin}
            variant="exact"
          />
          <span className="lane-count">
            {trace.retrieval.exact_evidence_count}
          </span>
        </div>
        {routes.map((route) => (
          <div className="lane" key={route.name}>
            <span className="lane-name">
              {ROUTE_LABELS[route.name]?.label ?? route.name}
              <span className="lane-weight">
                RRF weight {route.weight} ·{" "}
                {ROUTE_LABELS[route.name]?.note ?? ""}
              </span>
            </span>
            <Dots asins={route.asins} cap={60} targetAsin={targetAsin} />
            <span className="lane-count">{route.count}</span>
          </div>
        ))}
        {routes.length === 0 && (
          <div className="lane">
            <span className="lane-name">BM25 routes</span>
            <span className="stage-sub">no sparse retrieval this turn</span>
            <span className="lane-count">0</span>
          </div>
        )}
      </div>
      <div className="merge-summary">
        <div className="merge-count">
          <div className="big">{trace.retrieval.merged_count}</div>
          <div className="small">merged · deduplicated · cap 80</div>
        </div>
        <div>
          <span className="lane-dots">
            {trace.retrieval.merged_pool.slice(0, 80).map((entry, index) => (
              <span
                key={entry.asin}
                className={`dot ${entry.exact ? "exact" : "fused"} ${
                  entry.asin === targetAsin ? "is-target" : ""
                }`}
                style={
                  { "--delay": `${200 + index * 12}ms` } as React.CSSProperties
                }
                title={`${entry.asin}${entry.exact ? " · exact" : ""}${
                  entry.routes.length ? ` · ${entry.routes.join(", ")}` : ""
                }`}
              />
            ))}
          </span>
          <div className="annotation-legend" style={{ marginTop: 12 }}>
            <span className="legend-item">
              <span
                className="legend-swatch"
                style={{ background: "var(--ink)", borderRadius: "50%" }}
              />{" "}
              exact-evidence hit (goes first)
            </span>
            <span className="legend-item">
              <span
                className="legend-swatch"
                style={{ background: "var(--blue)", borderRadius: "50%" }}
              />{" "}
              BM25 + RRF
            </span>
            {targetAsin && (
              <span className="legend-item">
                <span
                  className="legend-swatch"
                  style={{ background: "var(--target)", borderRadius: "50%" }}
                />{" "}
                target product
              </span>
            )}
          </div>
        </div>
      </div>
      {trace.retrieval.category_dropped && (
        <p className="rerank-note">
          The category-scoped search came back empty, so retrieval failed open
          to the full catalog.
        </p>
      )}
    </div>
  );
}
