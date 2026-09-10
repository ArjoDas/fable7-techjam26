"use client";

import type { ReactNode } from "react";

export function StageFrame({
  number,
  title,
  sub,
  revealed,
  children,
}: {
  number: string;
  title: string;
  sub: string;
  revealed: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`stage ${revealed ? "revealed" : ""}`} aria-hidden={!revealed}>
      <div className="stage-number">{number}</div>
      <div>
        <h2 className="stage-title">{title}</h2>
        <p className="stage-sub">{sub}</p>
        {children}
      </div>
    </section>
  );
}

export function StageConnector({ revealed }: { revealed: boolean }) {
  return (
    <div className={`stage-connector ${revealed ? "revealed" : ""}`} aria-hidden>
      <div className="line" />
      <div className="arrow" />
    </div>
  );
}
