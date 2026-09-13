import Image from "next/image";
import { PipelineExplorer } from "@/components/pipeline-explorer";

import { REPOSITORY_URL, LIVE_DEMO_URL } from "@/lib/site";
const DEVPOST_URL = "https://devpost.com/software/fable7";

export default function Home() {
  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-brand">
          <Image
            className="brand-mark"
            src="/icon.svg"
            alt=""
            width={52}
            height={52}
            unoptimized
          />
          <div className="brand-name">
            Fable<em>7</em>
          </div>
        </div>
        <nav className="masthead-links">
          <a href={REPOSITORY_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
          <a href={DEVPOST_URL} target="_blank" rel="noreferrer">
            Devpost
          </a>
        </nav>
      </header>

      <main className="pipeline-main">
        <aside className="demo-notice" aria-label="About this demo">
          <div>
            <strong>This is a static demo with recorded agent responses to minimise hosting costs</strong>
            <p>Explore real structured-query and natural-language sessions, by running our demo locally <a href={LIVE_DEMO_URL} target="_blank" rel="noreferrer">here</a>.</p>
          </div>
        </aside>
        <PipelineExplorer />
      </main>

      <footer className="site-footer">
        <div className="event-strip">
          TikTok TechJam 2026, Conversational search (track 4)
        </div>
        <span className="footer-names">
          Srivathsan Ram, Arjo Das, Jun Wen Mok
        </span>
        <span className="footer-copyright">© 2026 Fable7</span>
      </footer>
    </div>
  );
}
