import { useState, useRef } from "react";

type State = "idle" | "checking" | "eligible" | "ineligible" | "invalid";

const ELIGIBLE_SAMPLE = ["0x3a7f","0x9d4e","0x5c12","0x8b9a","0x1e5d","0xfa3c","0x2d81","0x7c44","0xf1b3","0xa94e"];

function isValidAddr(addr: string) {
  return /^0x[0-9a-fA-F]{40}$/.test(addr.trim());
}

export function EligibilityChecker() {
  const [addr, setAddr] = useState("");
  const [state, setState] = useState<State>("idle");
  const [amount, setAmount] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  function check() {
    const trimmed = addr.trim();
    if (!trimmed) return;
    if (!isValidAddr(trimmed)) { setState("ineligible"); return; }
    setState("checking");
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const prefix = trimmed.slice(2, 6).toLowerCase();
      const isEligible = ELIGIBLE_SAMPLE.some(s => s.slice(2) === prefix) || (parseInt(prefix, 16) % 3 !== 0);
      if (isEligible) {
        const allocations = [1200, 1500, 1800, 2000, 2500, 3000, 3200, 4000];
        const idx = parseInt(prefix, 16) % allocations.length;
        setAmount(allocations[idx]);
        setState("eligible");
      } else {
        setState("ineligible");
      }
    }, 2200);
  }

  function reset() { setState("idle"); setAddr(""); setAmount(0); }

  return (
    <div className="elig-wrap">
      <div className="section-head">
        <div className="section-tag">🔍 Eligibility</div>
        <div className="section-title">Check Your Wallet</div>
        <p className="section-sub">Enter your wallet address to see if you're eligible before connecting.</p>
      </div>

      {state === "idle" || state === "checking" ? (
        <div className="elig-form">
          <div className="elig-input-wrap">
            <span className="elig-input-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
              </svg>
            </span>
            <input
              className="elig-input"
              type="text"
              placeholder="0x... your Ethereum wallet address"
              value={addr}
              onChange={e => { setAddr(e.target.value); setState("idle"); }}
              onKeyDown={e => e.key === "Enter" && check()}
              disabled={state === "checking"}
              spellCheck={false}
              autoComplete="off"
            />
            {addr && state === "idle" && (
              <button className="elig-clear" onClick={() => setAddr("")}>✕</button>
            )}
          </div>
          <button
            className="elig-btn"
            onClick={check}
            disabled={!addr.trim() || state === "checking"}
          >
            {state === "checking" ? (
              <>
                <div className="spinner-sm" />
                Checking…
              </>
            ) : "Check Eligibility →"}
          </button>

          {state === "checking" && (
            <div className="elig-checking-row">
              <div className="elig-step elig-step-done">
                <div className="elig-step-dot done" />
                <span>Validating address format</span>
              </div>
              <div className="elig-step elig-step-active">
                <div className="elig-step-dot active" />
                <span>Querying snapshot data…</span>
              </div>
              <div className="elig-step">
                <div className="elig-step-dot" />
                <span>Calculating allocation</span>
              </div>
            </div>
          )}
        </div>
      ) : state === "eligible" ? (
        <div className="elig-result eligible">
          <div className="elig-result-icon">🎉</div>
          <div className="elig-result-body">
            <div className="elig-result-title">You're Eligible!</div>
            <div className="elig-result-sub">
              Wallet <span className="elig-addr">{addr.slice(0,6)}…{addr.slice(-4)}</span> qualifies for:
            </div>
            <div className="elig-amount">
              <span className="elig-amount-num">{amount.toLocaleString()}</span>
              <span className="elig-amount-tick">NXS</span>
              <span className="elig-amount-usd">≈ ${(amount * 1.9).toLocaleString(undefined, {maximumFractionDigits:0})} USD</span>
            </div>
            <div className="elig-result-hint">Scroll down to connect your wallet and claim</div>
          </div>
          <button className="elig-reset" onClick={reset}>Check another →</button>
        </div>
      ) : (
        <div className="elig-result ineligible">
          <div className="elig-result-icon">😔</div>
          <div className="elig-result-body">
            <div className="elig-result-title">Not Eligible</div>
            <div className="elig-result-sub">
              {isValidAddr(addr)
                ? `Wallet ${addr.slice(0,6)}…${addr.slice(-4)} was not included in the Season 1 snapshot.`
                : "Please enter a valid Ethereum wallet address (0x…)."}
            </div>
            {isValidAddr(addr) && (
              <div className="elig-result-hint">Watch for Season 2 announcements on our Discord and Twitter.</div>
            )}
          </div>
          <button className="elig-reset" onClick={reset}>Try another →</button>
        </div>
      )}
    </div>
  );
}
