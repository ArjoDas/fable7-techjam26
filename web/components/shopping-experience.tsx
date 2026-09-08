"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, createSession, resetSession, sendTurn } from "@/lib/api";
import type { AgentTrace, ChatMessage, DemoMode, MessageOption, ProductCard } from "@/lib/contracts";
import { FunnelCanvas } from "./funnel-canvas";
import { ProductGrid } from "./product-grid";
import { TracePanel } from "./trace-panel";

const WELCOME: Record<DemoMode, string> = {
  demo: "Tell me what you're shopping for — a category, a budget, a material, or simply the feeling you want.",
  internals: "Choose a guided opening below. We'll follow the same request from 50,000 products to the final slate.",
};

const sessionBootstraps: Partial<Record<DemoMode, Promise<Awaited<ReturnType<typeof createSession>>>>> = {};

function createSessionDeduped(mode: DemoMode) {
  const existing = sessionBootstraps[mode];
  if (existing) return existing;
  const request = createSession(mode);
  sessionBootstraps[mode] = request;
  request.then(
    () => window.setTimeout(() => {
      if (sessionBootstraps[mode] === request) delete sessionBootstraps[mode];
    }, 250),
    () => {
      if (sessionBootstraps[mode] === request) delete sessionBootstraps[mode];
    },
  );
  return request;
}

export function ShoppingExperience({ mode }: { mode: DemoMode }) {
  const [sessionId, setSessionId] = useState("");
  const [turn, setTurn] = useState(0);
  const [catalogSize, setCatalogSize] = useState(50000);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: "welcome", role: "assistant", content: WELCOME[mode] },
  ]);
  const [products, setProducts] = useState<ProductCard[]>([]);
  const [options, setOptions] = useState<MessageOption[]>([]);
  const [selectedOption, setSelectedOption] = useState("");
  const [input, setInput] = useState("");
  const [trace, setTrace] = useState<AgentTrace | null>(null);
  const [status, setStatus] = useState<"starting" | "ready" | "working" | "error">("starting");
  const [error, setError] = useState("");
  const transcriptRef = useRef<HTMLDivElement>(null);

  async function start() {
    setStatus("starting");
    setError("");
    try {
      const session = await createSessionDeduped(mode);
      setSessionId(session.session_id);
      setTurn(session.turn);
      setCatalogSize(session.catalog_size);
      setOptions(session.message_options);
      setSelectedOption(session.message_options[0]?.id || "");
      setMessages([{ id: crypto.randomUUID(), role: "assistant", content: WELCOME[mode] }]);
      setProducts([]);
      setTrace(null);
      setStatus("ready");
    } catch (caught) {
      const message = caught instanceof ApiError ? caught.message : "Could not reach the shopping service.";
      setError(message);
      setStatus("error");
    }
  }

  useEffect(() => {
    void start();
    // A mode change creates a new server-side conversation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, status]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!sessionId || status !== "ready" || turn >= 10) return;
    const chosen = options.find((option) => option.id === selectedOption);
    const content = mode === "internals" ? chosen?.message_preview || "" : input.trim();
    if (!content) return;

    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content }]);
    setInput("");
    setStatus("working");
    setError("");
    try {
      const result = await sendTurn(
        sessionId,
        mode === "internals" ? { option_id: selectedOption } : { message: content },
      );
      setTurn(result.turn);
      setProducts(result.recommendations);
      setOptions(result.message_options);
      setSelectedOption(result.message_options[0]?.id || "");
      setTrace(result.trace);
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", content: result.assistant.message },
      ]);
      setStatus("ready");
    } catch (caught) {
      const message = caught instanceof ApiError ? caught.message : "This turn could not be completed.";
      setError(message);
      setStatus("error");
    }
  }

  async function reset() {
    if (!sessionId) return void start();
    setStatus("starting");
    setError("");
    try {
      const session = await resetSession(sessionId);
      setTurn(0);
      setMessages([{ id: crypto.randomUUID(), role: "assistant", content: WELCOME[mode] }]);
      setProducts([]);
      setTrace(null);
      setOptions(session.message_options);
      setSelectedOption(session.message_options[0]?.id || "");
      setStatus("ready");
    } catch {
      await start();
    }
  }

  const isInternals = mode === "internals";
  const terminal = turn >= 10;

  return (
    <main className={`experience-shell ${isInternals ? "internals-mode" : "demo-mode"}`}>
      <header className="app-header">
        <Link className="brand" href="/"><span className="brand-mark">N</span><span>Narrow</span></Link>
        <div className="mode-switch" aria-label="Demo mode">
          <Link className={!isInternals ? "active" : ""} href="/demo">Shop</Link>
          <Link className={isInternals ? "active" : ""} href="/internals">Internals</Link>
        </div>
        <div className="header-actions">
          <span className="turn-count">Turn {turn}<i />10</span>
          <button onClick={() => void reset()}>New session</button>
        </div>
      </header>

      <section className={isInternals ? "internals-grid" : "demo-grid"}>
        <div className="chat-column">
          <div className="column-title">
            <div><span className="section-label">Conversation</span><h1>{isInternals ? "Guide the agent" : "What are you looking for?"}</h1></div>
            <span className={`connection-dot ${status}`} />
          </div>
          <div className="transcript" ref={transcriptRef}>
            {messages.map((message) => (
              <div className={`message ${message.role}`} key={message.id}>
                <span>{message.role === "assistant" ? "N" : "You"}</span>
                <p>{message.content}</p>
              </div>
            ))}
            {status === "working" && (
              <div className="message assistant working-message"><span>N</span><p>Searching the catalog <i /><i /><i /></p></div>
            )}
          </div>

          {error && (
            <div className="error-banner">
              <p>{error}</p>
              <button onClick={() => void start()}>Reconnect</button>
            </div>
          )}

          <form className="composer" onSubmit={submit}>
            {terminal ? (
              <div className="terminal-message"><span>Ten turns complete.</span><button type="button" onClick={() => void reset()}>Start fresh</button></div>
            ) : isInternals ? (
              <>
                <label htmlFor="guided-message">Choose the next message</label>
                <select
                  id="guided-message"
                  value={selectedOption}
                  onChange={(event) => setSelectedOption(event.target.value)}
                  disabled={status !== "ready" || !options.length}
                >
                  {options.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}{option.estimated_remaining !== null ? ` · ~${option.estimated_remaining} remain` : ""}
                    </option>
                  ))}
                </select>
                {selectedOption && <p className="option-preview">{options.find((item) => item.id === selectedOption)?.message_preview}</p>}
                <button className="send-button" disabled={status !== "ready" || !selectedOption}>Run turn <span>→</span></button>
              </>
            ) : (
              <>
                <label htmlFor="shopper-message">Describe what you need</label>
                <div className="input-row">
                  <textarea
                    id="shopper-message"
                    maxLength={1000}
                    rows={2}
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    placeholder="A lightweight rain jacket under $100…"
                    disabled={status !== "ready"}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                  />
                  <button className="send-button icon-button" aria-label="Send message" disabled={status !== "ready" || !input.trim()}>→</button>
                </div>
                <p className="composer-note">Free-form catalog search · no account or API tokens required</p>
              </>
            )}
          </form>
        </div>

        {isInternals ? (
          <>
            <div className="visual-column">
              <FunnelCanvas trace={trace} />
              <div className="result-heading"><span className="section-label">Current slate</span><strong>{products.length} selected</strong></div>
              <ProductGrid products={products} />
            </div>
            <TracePanel trace={trace} />
          </>
        ) : (
          <div className="results-column">
            <div className="results-intro">
              <span className="section-label">Agent selection</span>
              <h2>{products.length ? `${products.length} closest ${products.length === 1 ? "match" : "matches"}` : "A focused edit of the catalog"}</h2>
              <p>{products.length ? "Ranked from the same frozen 50,000-product catalog." : "Your conversation will shape this shelf in real time."}</p>
            </div>
            <ProductGrid products={products} />
          </div>
        )}
      </section>
      <div className="catalog-ribbon"><span>{new Intl.NumberFormat("en-US").format(catalogSize)}</span> products indexed locally</div>
    </main>
  );
}
