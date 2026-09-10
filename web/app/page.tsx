import { PipelineExplorer } from "@/components/pipeline-explorer";

export default function Home() {
  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-brand">
          <div className="brand-mark" aria-hidden>
            <div className="book-left" />
            <div className="book-right" />
            <div className="book-spine" />
            <div className="lens" />
            <div className="lens-handle" />
          </div>
          <div className="brand-name">
            Fable<em>7</em>
          </div>
        </div>
        <div className="masthead-note">
          TikTok TechJam 2026 · Conversational search track
        </div>
      </header>

      <h1 className="headline">
        From prompt to results, <em>one decision at a time</em>
      </h1>
      <p className="subhead">
        Watch the agent turn a shopping message into recommendations: it reads
        the query, decides buying vs browsing, retrieves candidates through
        exact-evidence and BM25 lanes fused with reciprocal-rank fusion,
        reranks the pool, and then chooses whether to show ten products,
        abstain with one, or rotate to unseen items.
      </p>

      <PipelineExplorer />

      <footer className="footer-note">
        Python standard library + SQLite FTS5 · Local MiniLM for semantic
        matching · No cloud APIs
      </footer>
    </div>
  );
}
