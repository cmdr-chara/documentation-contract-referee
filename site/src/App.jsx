import { useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import heroEditorial from "./assets/hero-editorial.webp";
import evidenceEditorial from "./assets/evidence-editorial.webp";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const PLAY_URL = "https://play.modiqo.ai/cmdr-chara/documentation-contract-referee@0.1.0";
const SOURCE_URL = "https://github.com/cmdr-chara/documentation-contract-referee";
const RUN_COMMAND = "rote play run cmdr-chara/documentation-contract-referee@0.1.0 repo_path=/path/to/repository";

const receipts = [
  {
    verdict: "CONTRACT HOLDS",
    tone: "holds",
    copy: "Every checked documentation claim matches repository evidence.",
    detail: "2 documents · 1 command · 1 local link",
  },
  {
    verdict: "CONTRACT BROKEN",
    tone: "broken",
    copy: "The README points to a missing setup path and an unavailable build script.",
    detail: "Evidence attached · correction suggested",
  },
  {
    verdict: "REVIEW REQUIRED",
    tone: "review",
    copy: "An executable contract changed without a corresponding documentation change.",
    detail: "Read-only · deterministic · bounded output",
  },
];

function Arrow() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20">
      <path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

function App() {
  const root = useRef(null);
  const [receiptIndex, setReceiptIndex] = useState(0);
  const [copyState, setCopyState] = useState("Copy command");

  useGSAP(
    () => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion) return;

      gsap.from(".hero-copy > *", {
        y: 44,
        duration: 1,
        stagger: 0.11,
        ease: "power3.out",
      });

      const media = gsap.matchMedia();
      media.add("(min-width: 981px)", () => {
        ScrollTrigger.create({
          trigger: ".proof-chapter",
          start: "top top+=96",
          end: "bottom bottom-=80",
          pin: ".proof-heading",
          pinSpacing: false,
        });
      });

      gsap.utils.toArray(".evidence-image").forEach((image) => {
        gsap.fromTo(
          image,
          { scale: 0.82, opacity: 0.34 },
          {
            scale: 1,
            opacity: 1,
            ease: "none",
            scrollTrigger: {
              trigger: image,
              start: "top 88%",
              end: "center 46%",
              scrub: true,
            },
          },
        );
        gsap.to(image, {
          opacity: 0.2,
          filter: "grayscale(1) brightness(.55)",
          ease: "none",
          scrollTrigger: {
            trigger: image,
            start: "center 34%",
            end: "bottom 8%",
            scrub: true,
          },
        });
      });

      return () => media.revert();
    },
    { scope: root },
  );

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(RUN_COMMAND);
      setCopyState("Copied");
      window.setTimeout(() => setCopyState("Copy command"), 1800);
    } catch {
      setCopyState("Select command below");
    }
  }

  const receipt = receipts[receiptIndex];

  return (
    <main ref={root} className="site-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>

      <header className="topbar">
        <a className="brand" href="#top" aria-label="Documentation Contract Referee home">
          <span className="brand-mark">R</span>
          <span>Contract Referee</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#proof">How it works</a>
          <a href={SOURCE_URL} target="_blank" rel="noreferrer">Source</a>
          <a className="nav-cta" href={PLAY_URL} target="_blank" rel="noreferrer">
            <span className="nav-label-desktop">Run Play</span>
            <span className="nav-label-mobile">Run</span>
            <Arrow />
          </a>
        </nav>
      </header>

      <section className="hero" id="top">
        <div className="hero-glow" aria-hidden="true" />
        <div className="hero-copy" id="main-content" tabIndex="-1">
          <p className="eyebrow">Read-only repository evidence</p>
          <h1>
            Documentation
            <span
              className="inline-image"
              role="img"
              aria-label="Printed technical documentation"
            />
            people can trust.
          </h1>
          <p className="hero-lede">
            Catch broken commands, stale paths and false setup promises before they cost another developer an afternoon.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href={PLAY_URL} target="_blank" rel="noreferrer">
              Run the Play <Arrow />
            </a>
            <a className="button button-secondary" href={SOURCE_URL} target="_blank" rel="noreferrer">
              Inspect source
            </a>
          </div>
        </div>
        <figure className="hero-visual">
          <img
            src={heroEditorial}
            alt="Layered technical papers, registration marks and measuring tools"
            width="1100"
            height="1300"
            fetchPriority="high"
          />
          <figcaption>
            <span>Verdict</span>
            <strong>CONTRACT HOLDS</strong>
            <small>Evidence checked. No claim drift found.</small>
          </figcaption>
        </figure>
      </section>

      <div className="marquee" aria-label="Play qualities">
        <div className="marquee-track">
          {[0, 1].map((group) => (
            <div className="marquee-group" aria-hidden={group === 1} key={group}>
              <span>README claims</span><i />
              <span>Repository evidence</span><i />
              <span>Deterministic verdict</span><i />
              <span>Suggested correction</span><i />
            </div>
          ))}
        </div>
      </div>

      <section className="interest chapter" aria-labelledby="interest-title">
        <div className="chapter-heading">
          <p className="eyebrow dark">One narrow promise</p>
          <h2 id="interest-title">If the docs say it, the repo should prove it.</h2>
        </div>
        <div className="bento">
          <article className="bento-card bento-primary">
            <div>
              <p className="card-kicker">Claim parser</p>
              <h3>Reads instructions. Never executes them.</h3>
            </div>
            <div className="claim-stack" aria-hidden="true">
              <span><code>npm run build</code><b>Found</b></span>
              <span><code>make release</code><b>Missing</b></span>
              <span><code>docs/setup.md</code><b>Found</b></span>
            </div>
          </article>
          <article className="bento-card bento-evidence">
            <p className="card-kicker">Evidence ledger</p>
            <h3>Every call has a source and a correction.</h3>
            <p>Links, scripts, Make targets, Just recipes, versions, lockfiles and env templates.</p>
          </article>
          <article className="bento-card bento-verdict">
            <p className="card-kicker">Bounded output</p>
            <strong>3</strong>
            <p>highest-priority findings by default. Signal without the audit dump.</p>
          </article>
        </div>
      </section>

      <section className="proof-chapter chapter" id="proof">
        <div className="proof-heading">
          <p className="eyebrow">How the referee works</p>
          <h2>Claims on one side. Evidence on the other.</h2>
          <p>No LLM judgment. No GitHub token. No repository mutation.</p>
        </div>
        <div className="proof-gallery">
          <article className="proof-card">
            <img
              className="evidence-image"
              src={evidenceEditorial}
              alt="Structured physical archive cards and evidence overlays"
              width="1200"
              height="900"
              loading="lazy"
            />
            <div><span>Parse</span><h3>Extract executable claims from README and runbooks.</h3></div>
          </article>
          <article className="proof-card">
            <img
              className="evidence-image"
              src={heroEditorial}
              alt="Technical specification sheets aligned against measuring tools"
              width="1200"
              height="900"
              loading="lazy"
            />
            <div><span>Compare</span><h3>Match each claim against the repository’s actual contract.</h3></div>
          </article>
          <article className="proof-card proof-card-final">
            <div className="verdict-field">
              <span>Deterministic result</span>
              <strong>CONTRACT<br />BROKEN</strong>
              <p>README.md → docs/missing.md</p>
            </div>
            <div><span>Referee</span><h3>Return evidence, priority and the smallest credible fix.</h3></div>
          </article>
        </div>
      </section>

      <section className="receipts chapter" aria-labelledby="receipts-title">
        <div className="receipt-intro">
          <p className="eyebrow dark">Three honest states</p>
          <h2 id="receipts-title">A verdict that survives inspection.</h2>
        </div>
        <div className={`receipt-panel ${receipt.tone}`} aria-live="polite">
          <div className="receipt-copy">
            <p>{receipt.detail}</p>
            <h3>{receipt.verdict}</h3>
            <blockquote>{receipt.copy}</blockquote>
          </div>
          <div className="receipt-controls" aria-label="Verdict examples">
            {receipts.map((item, index) => (
              <button
                type="button"
                key={item.verdict}
                aria-label={`Show ${item.verdict}`}
                aria-pressed={receiptIndex === index}
                onClick={() => setReceiptIndex(index)}
              >
                {String(index + 1).padStart(2, "0")}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="action chapter">
        <div className="action-copy">
          <h2>Stop shipping instructions that no longer work.</h2>
          <p>One read-only command. Evidence in seconds.</p>
        </div>
        <div className="command-block">
          <code>{RUN_COMMAND}</code>
          <button type="button" onClick={copyCommand}>{copyState}</button>
        </div>
        <p className="copy-status" aria-live="polite">{copyState === "Copied" ? "Command copied to clipboard." : ""}</p>
      </section>

      <footer>
        <a className="brand footer-brand" href="#top">
          <span className="brand-mark">R</span>
          <span>Documentation Contract Referee</span>
        </a>
        <p>Open source. Read-only. Built for Rote Playoffs.</p>
        <div>
          <a href={PLAY_URL} target="_blank" rel="noreferrer">Play</a>
          <a href={SOURCE_URL} target="_blank" rel="noreferrer">GitHub</a>
        </div>
      </footer>
    </main>
  );
}

export default App;
