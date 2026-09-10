"use client";

import type { AgentTrace, QueryAnnotation } from "@/lib/contracts";

export function AnnotatedMessage({
  message,
  annotations,
}: {
  message: string;
  annotations: QueryAnnotation[];
}) {
  const segments: Array<{ text: string; kind: string | null }> = [];
  let cursor = 0;
  for (const annotation of annotations) {
    if (annotation.start < cursor || annotation.end > message.length) continue;
    if (annotation.start > cursor) {
      segments.push({ text: message.slice(cursor, annotation.start), kind: null });
    }
    segments.push({
      text: message.slice(annotation.start, annotation.end),
      kind: annotation.kind,
    });
    cursor = annotation.end;
  }
  if (cursor < message.length) {
    segments.push({ text: message.slice(cursor), kind: null });
  }
  return (
    <span>
      {segments.map((segment, index) =>
        segment.kind ? (
          <mark key={index} className={`annotation kind-${segment.kind}`}>
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </span>
  );
}

export function QueryStage({ trace }: { trace: AgentTrace }) {
  const isTranslated = Boolean(trace.semantic);
  const raw = trace.input_message ?? trace.message;
  const kinds = new Set(trace.query_annotations.map((item) => item.kind));
  return (
    <div>
      {isTranslated ? (
        <p className="query-message">&ldquo;{raw}&rdquo;</p>
      ) : (
        <p className="query-message">
          <AnnotatedMessage
            message={trace.message}
            annotations={trace.query_annotations}
          />
        </p>
      )}
      {isTranslated ? (
        <div className="annotation-legend">
          <span className="legend-item">
            Free text. The next step matches it against the catalog vocabulary.
          </span>
        </div>
      ) : (
        <div className="annotation-legend">
          {kinds.has("category") && (
            <span className="legend-item">
              <span className="legend-swatch kind-category" /> category
            </span>
          )}
          {kinds.has("constraint") && (
            <span className="legend-item">
              <span className="legend-swatch kind-constraint" /> constraint
            </span>
          )}
          {kinds.has("intent") && (
            <span className="legend-item">
              <span className="legend-swatch kind-intent" /> intent marker
            </span>
          )}
          {(kinds.has("override") ||
            kinds.has("boundary") ||
            kinds.has("exhausted")) && (
            <span className="legend-item">
              <span className="legend-swatch kind-override" /> conversation
              control
            </span>
          )}
        </div>
      )}
    </div>
  );
}
