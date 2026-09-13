"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { loadManifest, loadRecording } from "@/lib/recordings";
import type { DemoManifest, QueryMode, RecordedSession, RecordedTurn } from "@/lib/recordings";
import type {
  AgentTrace,
} from "@/lib/contracts";
import { StageConnector, StageFrame } from "./stage-frame";
import { QueryStage } from "./query-stage";
import { IntentStage } from "./intent-stage";
import { SemanticStage } from "./semantic-stage";
import { FunnelStage } from "./funnel-stage";
import { RerankStage } from "./rerank-stage";
import { PrefixStage } from "./prefix-stage";
import { DecisionStage } from "./decision-stage";

type Run = {
  sessionId: string;
  mode: QueryMode;
  exampleId: string;
  target: { asin: string; title: string };
  turns: RecordedTurn[];
};

function targetRanks(
  trace: AgentTrace,
  asin: string,
): Array<{ label: string; rank: number | null }> {
  const rank = (list: string[]) => {
    const index = list.indexOf(asin);
    return index < 0 ? null : index + 1;
  };
  return [
    { label: "exact lane", rank: rank(trace.retrieval.exact_asins) },
    { label: "BM25 fused", rank: rank(trace.retrieval.fused_asins) },
    { label: "merged 80", rank: rank(trace.retrieval.candidate_asins) },
    { label: "linear rerank", rank: rank(trace.ranking.linear_ranking) },
    { label: "prefix match", rank: rank(trace.ranking.prefix?.matches ?? []) },
    { label: "after hoist", rank: rank(trace.ranking.dialogue_ranking) },
    { label: "shown", rank: rank(trace.selection.selected) },
  ];
}

export function PipelineExplorer() {
  const [manifest, setManifest] = useState<DemoManifest | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [mode, setMode] = useState<QueryMode>("structured");
  const [selectedId, setSelectedId] = useState("");
  const [recording, setRecording] = useState<RecordedSession | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [activeTurn, setActiveTurn] = useState(0);
  const [reveal, setReveal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const revealTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const recordingRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setManifestError(null);
    loadManifest(controller.signal).then((payload) => {
      if (controller.signal.aborted) return;
      setManifest(payload);
      setSelectedId(payload.examples[0].id);
    }).catch((cause) => {
      if (!controller.signal.aborted) setManifestError(cause instanceof Error ? cause.message : "Could not load the recordings.");
    });
    return () => controller.abort();
  }, [retry]);

  const examples = manifest?.examples ?? [];
  const selectedExample = examples.find((example) => example.id === selectedId) ?? null;

  const activeView = run?.turns[activeTurn] ?? null;
  const activeTrace = activeView?.response.trace ?? null;
  const hasSemanticStage = Boolean(activeTrace?.semantic);
  const stageCount = activeTrace ? (hasSemanticStage ? 7 : 6) : 0;

  // ── staged reveal timeline ───────────────────────────────
  const startReveal = useCallback((total: number) => {
    revealTimers.current.forEach(clearTimeout);
    revealTimers.current = [];
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setReveal(total);
      return;
    }
    setReveal(0);
    for (let index = 1; index <= total; index += 1) {
      revealTimers.current.push(
        setTimeout(() => setReveal(index), 350 + (index - 1) * 1050),
      );
    }
  }, []);

  useEffect(() => () => {
    revealTimers.current.forEach(clearTimeout);
    recordingRequest.current?.abort();
  }, []);

  const resetRun = useCallback(() => {
    recordingRequest.current?.abort();
    revealTimers.current.forEach(clearTimeout);
    setRecording(null);
    setRun(null);
    setActiveTurn(0);
    setReveal(0);
    setLoading(false);
    setError(null);
  }, []);

  const beginRun = useCallback(async () => {
    if (!selectedExample) return;
    recordingRequest.current?.abort();
    const controller = new AbortController();
    recordingRequest.current = controller;
    setError(null);
    setLoading(true);
    try {
      const captured = await loadRecording(selectedExample, mode, controller.signal);
      if (controller.signal.aborted) return;
      setRecording(captured);
      const first = captured.turns[0];
      setRun({
        sessionId: first.response.session_id,
        mode,
        exampleId: selectedExample.id,
        target: { asin: selectedExample.target_asin, title: selectedExample.target_title },
        turns: [first],
      });
      setActiveTurn(0);
      startReveal(first.response.trace?.semantic ? 7 : 6);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not load this recording. Please try again.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [selectedExample, mode, startReveal]);

  const nextTurn = useCallback(() => {
    if (!run || !recording) return;
    const next = recording.turns[run.turns.length];
    if (!next) return;
    setRun({ ...run, turns: [...run.turns, next] });
    setActiveTurn(run.turns.length);
    startReveal(next.response.trace?.semantic ? 7 : 6);
  }, [recording, run, startReveal]);

  const switchMode = useCallback((nextMode: QueryMode) => {
    if (nextMode === mode) return;
    resetRun();
    setMode(nextMode);
  }, [mode, resetRun]);

  const viewTurn = useCallback(
    (index: number) => {
      setActiveTurn(index);
      const trace = run?.turns[index]?.response.trace;
      startReveal(trace?.semantic ? 7 : 6);
    },
    [run, startReveal],
  );

  // ── derived: example progress, target status ─────────────
  const exampleForRun = run?.exampleId
    ? examples.find((item) => item.id === run.exampleId) ?? null
    : null;
  const scriptedRemaining = exampleForRun
    ? exampleForRun.turns.length - (run?.turns.length ?? 0)
    : null;

  const target = run?.target ?? null;
  const foundAtTurn = useMemo(() => {
    if (!run || !target) return null;
    for (const view of run.turns) {
      const selected = view.response.trace?.selection.selected ?? [];
      if (selected[0] === target.asin) return view.turn;
    }
    return null;
  }, [run, target]);

  const ranks =
    target && activeTrace ? targetRanks(activeTrace, target.asin) : null;

  // ── render ───────────────────────────────────────────────
  const header = (
    <>
      <div className="headline-row">
        <h1 className="headline">
          From prompt to results, <em>one decision at a time</em>
        </h1>
        <div className="mode-toggle" role="tablist" aria-label="Query mode">
          <button
            role="tab"
            aria-selected={mode === "structured"}
            className={mode === "structured" ? "active" : ""}
            onClick={() => switchMode("structured")}
          >
            Structured query
          </button>
          <button
            role="tab"
            aria-selected={mode === "natural"}
            className={mode === "natural" ? "active" : ""}
            onClick={() => switchMode("natural")}
          >
            Natural language
          </button>
        </div>
      </div>
      <p className="subhead">
        {mode === "structured"
          ? "Pick a recorded session and follow the engine’s decisions: it reads the query, decides buying or browsing, retrieves candidates through exact-evidence and BM25 lanes, reranks the pool, checks the evidence-prefix index, then shows ten products, abstains with one, or rotates to unseen items."
          : "Replay a recorded natural-language conversation. Follow how the engine mapped the shopper’s words onto catalog categories and clues before retrieval began."}
      </p>
    </>
  );

  if (!manifest) {
    return (
      <div>
        {header}
        <div className="boot-panel" role="status">
          <div className="boot-title">{manifestError ? "Recordings could not be loaded" : "Loading recorded examples"}</div>
          <p className="boot-note">{manifestError ?? "Fetching the example index. No engine or model runs in this demo."}</p>
          {manifestError && <button className="run-button secondary" onClick={() => setRetry((value) => value + 1)}>Try again</button>}
        </div>
      </div>
    );
  }

  return (
    <div>
      {header}
      <div className="controls">
        <div className="controls-row">
          <div className="control-field">
            <label className="control-label" htmlFor="example-select">
              Recorded example (target known)
            </label>
            <select
              id="example-select"
              value={selectedId}
              onChange={(event) => {
                setSelectedId(event.target.value);
                resetRun();
              }}
            >
              {examples.map((example) => (
                <option key={example.id} value={example.id}>
                  {example.label}
                </option>
              ))}
            </select>
          </div>
          <button
            className="run-button"
            onClick={run ? resetRun : beginRun}
            disabled={loading}
          >
            {loading && !run ? (
              <>
                <span className="spinner-inline" />
                loading recording
              </>
            ) : run ? (
              "Reset example"
            ) : (
              "Play example"
            )}
          </button>
        </div>
        {error && <div className="status-line error" role="alert">{error}</div>}
        {!run && selectedExample && (
          <div className="status-line">
            {selectedExample.turns.length} recorded turns · target:{" "}
            {selectedExample.target_title.slice(0, 90)}
          </div>
        )}
      </div>

      {selectedExample && (
        <div className="recorded-message">
          <span className="control-label">{activeView ? `Recorded shopper message · turn ${activeView.turn}` : "First recorded shopper message"}</span>
          <p>{activeView?.input ?? selectedExample.turns[0][mode]}</p>
        </div>
      )}

      {run && target && (
        <div className={`target-banner ${foundAtTurn !== null ? "found" : ""}`}>
          <span className="target-chip" />
          <span className="target-copy">
            Target: <strong>{target.title.slice(0, 90)}</strong>{" "}
            <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
              ({target.asin})
            </span>
          </span>
          {foundAtTurn !== null ? (
            <span className="target-found-note">
              reached rank 1 in {foundAtTurn} turn{foundAtTurn === 1 ? "" : "s"}
            </span>
          ) : (
            <span className="target-found-note" style={{ color: "var(--blue)" }}>
              not at rank 1 yet
            </span>
          )}
          {ranks && (
            <span className="rank-strip">
              {ranks.map((entry) => (
                <span
                  key={entry.label}
                  className={`rank-pill ${entry.rank === 1 ? "hit" : ""}`}
                >
                  {entry.label}:{" "}
                  <strong>{entry.rank === null ? "out" : `#${entry.rank}`}</strong>
                </span>
              ))}
            </span>
          )}
        </div>
      )}

      {run && (
        <div className="turn-strip">
          <span className="turn-label">Turns</span>
          {run.turns.map((view, index) => {
            const decision = view.response.trace?.selection.decision;
            const decisionClass =
              decision === "abstain_1"
                ? "decision-abstain"
                : decision === "rotation"
                  ? "decision-rotation"
                  : "decision-top";
            return (
              <button
                key={view.turn}
                className={`turn-tab ${decisionClass} ${
                  index === activeTurn ? "active" : ""
                }`}
                onClick={() => viewTurn(index)}
              >
                {view.turn}
              </button>
            );
          })}
          {scriptedRemaining !== null && scriptedRemaining > 0 && (
            <button className="run-button secondary" onClick={nextTurn}>
              Next turn ({scriptedRemaining} left)
            </button>
          )}
          <button
            className="run-button secondary"
            onClick={() => startReveal(stageCount)}
            disabled={!activeTrace}
          >
            Replay animation
          </button>
        </div>
      )}

      {activeTrace && activeView && (
        <div className="stage-rail" key={`${run?.sessionId}-${activeView.turn}`}>
          {(() => {
            const targetForStage = target?.asin ?? null;
            const stages: Array<{
              title: string;
              sub: string;
              node: React.ReactNode;
            }> = [
              {
                title: "The query",
                sub: hasSemanticStage
                  ? "The shopper's message, exactly as typed."
                  : "The message, with the parts the agent latches onto highlighted.",
                node: <QueryStage trace={activeTrace} />,
              },
              {
                title: "Buying or browsing?",
                sub: "Conversation state decides retrieval weights, and ambiguity signals decide whether the agent may abstain.",
                node: <IntentStage trace={activeTrace} />,
              },
            ];
            if (hasSemanticStage && activeTrace.semantic) {
              stages.push({
                title: "Natural-language mapping",
                sub: "Recorded category and clue matching. Literal phrases are resolved first; MiniLM scores unfamiliar wording only when needed.",
                node: (
                  <SemanticStage
                    trace={activeTrace}
                    semantic={activeTrace.semantic}
                  />
                ),
              });
            }
            stages.push(
              {
                title: "Retrieval lanes → 80 candidates",
                sub: "An exact-evidence lane plus three BM25 routes fused with reciprocal-rank fusion; exact hits go first, the union is deduplicated and capped at 80.",
                node: (
                  <FunnelStage trace={activeTrace} targetAsin={targetForStage} />
                ),
              },
              {
                title: "Learned reranking",
                sub: "The pool is rescored by a 16-feature linear model trained on evaluator sessions.",
                node: (
                  <RerankStage
                    trace={activeTrace}
                    targetAsin={targetForStage}
                    revealed={reveal >= stages.length + 2}
                  />
                ),
              },
              {
                title: "Ordered evidence-prefix index",
                sub: "Category plus the clues in disclosure order form a key into a catalog-wide prefix index; matching products are promoted above the learned ranking.",
                node: (
                  <PrefixStage
                    trace={activeTrace}
                    targetAsin={targetForStage}
                    revealed={reveal >= stages.length + 3}
                  />
                ),
              },
              {
                title: "The decision",
                sub: "Show a full top 10, abstain with a single candidate and ask again, or rotate to products not shown before.",
                node: (
                  <DecisionStage
                    trace={activeTrace}
                    response={activeView.response}
                    targetAsin={targetForStage}
                  />
                ),
              },
            );
            return stages.map((stage, index) => (
              <div key={stage.title}>
                {index > 0 && <StageConnector revealed={reveal >= index + 1} />}
                <StageFrame
                  number={`${index + 1}`}
                  title={stage.title}
                  sub={stage.sub}
                  revealed={reveal >= index + 1}
                >
                  {stage.node}
                </StageFrame>
              </div>
            ));
          })()}
        </div>
      )}

      {!run && (
        <div className="boot-panel">
          <div className="boot-title">
            Pick an example and press Play example
          </div>
          <div className="boot-note">
            {mode === "structured"
              ? "Each recording follows a real conversation toward a known target product. Advance through its turns to inspect the engine’s decisions."
              : "These natural-language messages and responses were recorded from the real engine. Choose an example to inspect how its wording was interpreted."}
          </div>
          <div className="dot-field" />
        </div>
      )}
    </div>
  );
}
