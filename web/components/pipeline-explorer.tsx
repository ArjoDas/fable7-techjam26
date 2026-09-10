"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createSession,
  getExamples,
  getReady,
  sendTurn,
} from "@/lib/api";
import type {
  AgentTrace,
  ExampleSession,
  TurnResponse,
} from "@/lib/contracts";
import { StageConnector, StageFrame } from "./stage-frame";
import { QueryStage } from "./query-stage";
import { IntentStage } from "./intent-stage";
import { SemanticStage } from "./semantic-stage";
import { FunnelStage } from "./funnel-stage";
import { RerankStage } from "./rerank-stage";
import { PrefixStage } from "./prefix-stage";
import { DecisionStage } from "./decision-stage";

type QueryMode = "structured" | "natural";

type TurnView = {
  turn: number;
  input: string;
  response: TurnResponse;
};

type Run = {
  sessionId: string;
  mode: QueryMode;
  exampleId: string | null;
  target: { asin: string; title: string } | null;
  turns: TurnView[];
};

const FREE_ID = "__free__";

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
  const [ready, setReady] = useState<"checking" | "initializing" | "ready" | "error">(
    "checking",
  );
  const [examples, setExamples] = useState<ExampleSession[]>([]);
  const [mode, setMode] = useState<QueryMode>("structured");
  const [selectedId, setSelectedId] = useState<string>("");
  const [freeText, setFreeText] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [activeTurn, setActiveTurn] = useState(0);
  const [reveal, setReveal] = useState(0);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const revealTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // ── readiness polling + examples ─────────────────────────
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      const status = await getReady();
      if (cancelled) return;
      if (status.status === "ready") {
        setReady("ready");
        try {
          const payload = await getExamples();
          if (!cancelled) {
            setExamples(payload.examples);
            setSelectedId((current) => current || payload.examples[0]?.id || "");
          }
        } catch {
          /* examples are optional */
        }
        return;
      }
      setReady(status.status === "error" ? "error" : "initializing");
      timer = setTimeout(poll, 2500);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const selectedExample = useMemo(
    () => examples.find((example) => example.id === selectedId) ?? null,
    [examples, selectedId],
  );
  const isFree = mode === "natural" && selectedId === FREE_ID;

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

  useEffect(() => () => revealTimers.current.forEach(clearTimeout), []);

  // ── run control ──────────────────────────────────────────
  const scriptedMessage = useCallback(
    (example: ExampleSession, turnIndex: number) =>
      mode === "natural"
        ? example.turns[turnIndex]?.natural
        : example.turns[turnIndex]?.structured,
    [mode],
  );

  const beginRun = useCallback(async () => {
    setError(null);
    const firstMessage = isFree
      ? freeText.trim()
      : selectedExample
        ? scriptedMessage(selectedExample, 0)
        : "";
    if (!firstMessage) {
      setError(
        isFree ? "Type a first message to start." : "Choose an example first.",
      );
      return;
    }
    setSending(true);
    try {
      const session = await createSession({ semantic: mode === "natural" });
      const response = await sendTurn(session.session_id, {
        message: firstMessage,
      });
      const newRun: Run = {
        sessionId: session.session_id,
        mode,
        exampleId: isFree ? null : selectedExample?.id ?? null,
        target:
          !isFree && selectedExample
            ? {
                asin: selectedExample.target_asin,
                title: selectedExample.target_title,
              }
            : null,
        turns: [{ turn: 1, input: firstMessage, response }],
      };
      setRun(newRun);
      setActiveTurn(0);
      if (isFree) setFreeText("");
      const semanticStage = Boolean(response.trace?.semantic);
      startReveal(semanticStage ? 7 : 6);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed.");
    } finally {
      setSending(false);
    }
  }, [freeText, isFree, mode, scriptedMessage, selectedExample, startReveal]);

  const nextTurn = useCallback(async () => {
    if (!run) return;
    setError(null);
    const turnIndex = run.turns.length;
    let message = "";
    if (run.exampleId) {
      const example = examples.find((item) => item.id === run.exampleId);
      message = example ? scriptedMessage(example, turnIndex) ?? "" : "";
    } else {
      message = freeText.trim();
    }
    if (!message) {
      setError(
        run.exampleId
          ? "This example has no more scripted turns."
          : "Type the next message first.",
      );
      return;
    }
    setSending(true);
    try {
      const response = await sendTurn(run.sessionId, { message });
      const updated: Run = {
        ...run,
        turns: [...run.turns, { turn: turnIndex + 1, input: message, response }],
      };
      setRun(updated);
      setActiveTurn(turnIndex);
      if (!run.exampleId) setFreeText("");
      const semanticStage = Boolean(response.trace?.semantic);
      startReveal(semanticStage ? 7 : 6);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed.");
    } finally {
      setSending(false);
    }
  }, [examples, freeText, run, scriptedMessage, startReveal]);

  const resetRun = useCallback(() => {
    revealTimers.current.forEach(clearTimeout);
    setRun(null);
    setActiveTurn(0);
    setReveal(0);
    setError(null);
  }, []);

  const switchMode = useCallback(
    (nextMode: QueryMode) => {
      if (nextMode === mode) return;
      setMode(nextMode);
      resetRun();
      if (nextMode === "structured" && selectedId === FREE_ID) {
        setSelectedId(examples[0]?.id ?? "");
      }
      if (nextMode === "natural") {
        setSelectedId(FREE_ID);
      }
    },
    [examples, mode, resetRun, selectedId],
  );

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
          ? "Pick a scripted session and watch the agent work: it reads the query, decides buying or browsing, retrieves candidates through exact-evidence and BM25 lanes, reranks the pool, checks the evidence-prefix index, then shows ten products, abstains with one, or rotates to unseen items."
          : "Type anything, or pick an example. Free text passes through one extra step: the closest semantic match maps your words onto the catalog's known categories and keywords before retrieval begins."}
      </p>
    </>
  );

  if (ready !== "ready") {
    return (
      <div>
        {header}
        <div className="boot-panel">
          <div className="boot-title">
            {ready === "error"
              ? "The agent failed to start"
              : "Indexing 50,000 products"}
          </div>
          <div className="boot-note">
            {ready === "error"
              ? "Check the API logs and reload."
              : "Building the full-text, exact-evidence, and dialogue-prefix indexes. This takes about forty seconds."}
          </div>
          {ready !== "error" && <div className="dot-field" />}
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
              {mode === "structured"
                ? "Example session (target known)"
                : "Query"}
            </label>
            <select
              id="example-select"
              value={selectedId}
              onChange={(event) => {
                setSelectedId(event.target.value);
                resetRun();
              }}
            >
              {mode === "natural" && (
                <option value={FREE_ID}>Type your own query</option>
              )}
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
            disabled={sending}
          >
            {sending && !run ? (
              <>
                <span className="spinner-inline" />
                running
              </>
            ) : run ? (
              "New run"
            ) : (
              "Run"
            )}
          </button>
        </div>
        {isFree && !run && (
          <div className="controls-row">
            <div className="control-field">
              <label className="control-label" htmlFor="free-first">
                Your first message
              </label>
              <input
                id="free-first"
                type="text"
                value={freeText}
                maxLength={400}
                placeholder="e.g. I need a durable leather belt for jeans"
                onChange={(event) => setFreeText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") beginRun();
                }}
              />
            </div>
          </div>
        )}
        {error && <div className="status-line error">{error}</div>}
        {!run && selectedExample && !isFree && (
          <div className="status-line">
            {selectedExample.turns.length} scripted turns · target:{" "}
            {selectedExample.target_title.slice(0, 90)}
          </div>
        )}
      </div>

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
          {run.exampleId ? (
            scriptedRemaining !== null &&
            scriptedRemaining > 0 && (
              <button
                className="run-button secondary"
                onClick={nextTurn}
                disabled={sending}
              >
                {sending ? (
                  <>
                    <span className="spinner-inline" />
                    sending
                  </>
                ) : (
                  `Next turn (${scriptedRemaining} left)`
                )}
              </button>
            )
          ) : (
            <div className="free-input-row">
              <input
                type="text"
                value={freeText}
                maxLength={400}
                placeholder="Add another requirement, or repeat the same one to trigger rotation"
                onChange={(event) => setFreeText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") nextTurn();
                }}
              />
              <button
                className="run-button secondary"
                onClick={nextTurn}
                disabled={sending}
              >
                {sending ? "Sending" : "Send"}
              </button>
            </div>
          )}
          <button
            className="run-button secondary"
            onClick={() => startReveal(stageCount)}
            disabled={sending || !activeTrace}
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
                title: "Closest semantic match",
                sub: "Free text is matched against the catalog's known categories and disclosure keywords: lexical shortlist first, then MiniLM cosine similarity.",
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
            {isFree ? "Type a query and press Run" : "Pick an example and press Run"}
          </div>
          <div className="boot-note">
            {mode === "structured"
              ? "Each example scripts a full conversation toward a known target product, so you can watch it climb to rank 1."
              : "Your words are matched to the closest catalog vocabulary before retrieval. Examples with known targets are also available in the dropdown."}
          </div>
          <div className="dot-field" />
        </div>
      )}
    </div>
  );
}
