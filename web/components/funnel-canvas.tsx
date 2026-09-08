"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentTrace } from "@/lib/contracts";

type Stage = { label: string; count: number; tone: string };

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function FunnelCanvas({ trace }: { trace: AgentTrace | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [step, setStep] = useState(0);
  const [replay, setReplay] = useState(0);
  const [reduceMotion, setReduceMotion] = useState(false);

  const stages = useMemo<Stage[]>(() => {
    if (!trace) return [{ label: "Full catalog", count: 50000, tone: "catalog" }];
    const rows: Stage[] = [
      { label: "Full catalog", count: trace.catalog.count, tone: "catalog" },
    ];
    if (trace.query.category_applied && trace.query.category_count !== null) {
      rows.push({ label: "Category scope", count: trace.query.category_count, tone: "scope" });
    }
    rows.push({ label: "Merged retrieval", count: trace.retrieval.merged_count, tone: "retrieval" });
    if (trace.ranking.dialogue_match_count !== null) {
      rows.push({ label: "Dialogue matches", count: trace.ranking.dialogue_match_count, tone: "ranking" });
    }
    rows.push({ label: "Final slate", count: trace.selection.selected.length, tone: "selected" });
    return rows;
  }, [trace]);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduceMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (reduceMotion) {
      setStep(stages.length - 1);
      return;
    }
    setStep(0);
    if (stages.length === 1) return;
    let next = 0;
    const timer = window.setInterval(() => {
      next += 1;
      setStep(Math.min(next, stages.length - 1));
      if (next >= stages.length - 1) window.clearInterval(timer);
    }, 520);
    return () => window.clearInterval(timer);
  }, [stages, reduceMotion, replay]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const box = canvas.getBoundingClientRect();
    const ratio = Math.min(1.5, window.devicePixelRatio || 1);
    const width = Math.max(300, Math.floor(box.width * ratio));
    const height = Math.max(230, Math.floor(box.height * ratio));
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.fillStyle = "#0c1514";
    context.fillRect(0, 0, width, height);

    const catalogCount = Math.max(1, stages[0]?.count || 50000);
    const active = Math.max(0, stages[Math.min(step, stages.length - 1)]?.count || 0);
    let seed = 928371;
    for (let index = 0; index < catalogCount; index += 1) {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      const x = 12 + (seed / 4294967296) * (width - 24);
      seed = (seed * 1664525 + 1013904223) >>> 0;
      const y = 12 + (seed / 4294967296) * (height - 24);
      const lit = index < active;
      context.fillStyle = lit ? "rgba(126, 255, 198, 0.78)" : "rgba(94, 117, 111, 0.12)";
      context.fillRect(x, y, lit ? 1.45 * ratio : 0.8 * ratio, lit ? 1.45 * ratio : 0.8 * ratio);
    }
  }, [stages, step]);

  const current = stages[Math.min(step, stages.length - 1)];
  return (
    <section className="catalog-field panel-dark">
      <div className="panel-heading">
        <div>
          <span className="section-label">Live catalog field</span>
          <h2>{formatCount(current.count)} <small>{current.count === 1 ? "product" : "products"} in view</small></h2>
        </div>
        {trace && (
          <button className="replay-button" onClick={() => setReplay((value) => value + 1)}>
            Replay
          </button>
        )}
      </div>
      <canvas ref={canvasRef} aria-label={`${formatCount(current.count)} products represented`} />
      <div className="funnel-stages">
        {stages.map((stage, index) => (
          <button
            className={index === step ? "active" : index < step ? "passed" : ""}
            key={`${stage.label}-${index}`}
            onClick={() => setStep(index)}
          >
            <i />
            <span>{stage.label}</span>
            <strong>{formatCount(stage.count)}</strong>
          </button>
        ))}
      </div>
      <p className="field-note">Each pixel is one abstract catalog item. Identities are exposed only for the bounded ranking head.</p>
    </section>
  );
}
