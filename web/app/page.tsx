import Link from "next/link";

function Arrow() {
  return <span aria-hidden="true">↗</span>;
}

export default function Home() {
  return (
    <main className="landing-shell">
      <nav className="landing-nav">
        <Link className="brand" href="/">
          <span className="brand-mark">N</span>
          <span>Narrow</span>
        </Link>
        <span className="nav-note">TechJam shopping intelligence</span>
      </nav>

      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><span /> 50,000 products. One useful answer.</div>
          <h1>Shopping search,<br /><em>made visible.</em></h1>
          <p>
            Explore the retrieval engine under the surface, or talk to the
            same agent the way a shopper naturally would.
          </p>
        </div>

        <div className="mode-grid">
          <Link href="/internals" className="mode-card mode-card-dark">
            <div className="mode-index">01</div>
            <div className="mode-visual mini-funnel" aria-hidden="true">
              <span>50K</span><i /><span>80</span><i /><span>1</span>
            </div>
            <div>
              <span className="card-kicker">For builders</span>
              <h2>Open the engine</h2>
              <p>Guide a conversation and watch every retrieval stage narrow the catalog.</p>
            </div>
            <div className="mode-link">Explore internals <Arrow /></div>
          </Link>

          <Link href="/demo" className="mode-card mode-card-light">
            <div className="mode-index">02</div>
            <div className="mode-visual chat-preview" aria-hidden="true">
              <span>I need a durable black belt.</span>
              <span>Here are the closest matches.</span>
            </div>
            <div>
              <span className="card-kicker">For shoppers</span>
              <h2>Try the conversation</h2>
              <p>Describe what you want in your own words and browse the agent&apos;s picks.</p>
            </div>
            <div className="mode-link">Start shopping <Arrow /></div>
          </Link>
        </div>
      </section>

      <footer className="landing-footer">
        <span>Offline inference</span><span>SQLite FTS5</span><span>Zero API tokens</span>
      </footer>
    </main>
  );
}

