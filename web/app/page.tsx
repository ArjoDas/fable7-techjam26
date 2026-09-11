import { PipelineExplorer } from "@/components/pipeline-explorer";

const GITHUB_URL =
  "https://github.com/SrivathsanRam/tiktok-techjam-conversational-search";
const DEVPOST_URL = "https://devpost.com/software/fable7";

export default function Home() {
  return (
    <div className="shell">
      <div className="event-strip">
        TikTok TechJam 2026 · Conversational search track
      </div>
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
        <nav className="masthead-links">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
          <a href={DEVPOST_URL} target="_blank" rel="noreferrer">
            Devpost
          </a>
        </nav>
      </header>

      <PipelineExplorer />

      <footer className="site-footer">
        <span className="footer-names">
          Srivathsan Ram · Arjo Das · Jun Wen Mok
        </span>
        <span className="footer-copyright">© 2026 Fable7</span>
      </footer>
    </div>
  );
}
