import Image from "next/image";
import { PipelineExplorer } from "@/components/pipeline-explorer";

const GITHUB_URL =
  "https://github.com/SrivathsanRam/tiktok-techjam-conversational-search";
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
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
          <a href={DEVPOST_URL} target="_blank" rel="noreferrer">
            Devpost
          </a>
        </nav>
      </header>

      <main className="pipeline-main">
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
