import { useEffect, useRef, useState } from "react";

const SEGMENTS = [
  { label: "Community Airdrop", pct: 30, color: "#ffffff", desc: "Distributed to eligible wallets via Season 1-3" },
  { label: "Ecosystem Growth",  pct: 25, color: "#cccccc", desc: "Grants, incentives, and protocol integrations" },
  { label: "Treasury",          pct: 20, color: "#999999", desc: "DAO-controlled reserve for future development" },
  { label: "Team & Advisors",   pct: 15, color: "#666666", desc: "4-year vesting with 1-year cliff" },
  { label: "Liquidity",         pct: 10, color: "#404040", desc: "DEX liquidity pools and market making" },
];

function useVisible(ref: React.RefObject<HTMLElement | null>) {
  const [vis, setVis] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVis(true); }, { threshold: 0.3 });
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, [ref]);
  return vis;
}

function DonutChart({ visible }: { visible: boolean }) {
  const r = 60, cx = 80, cy = 80, stroke = 26;
  const circ = 2 * Math.PI * r;
  let offset = 0;

  return (
    <svg width="160" height="160" className="donut-svg">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,.04)" strokeWidth={stroke} />
      {SEGMENTS.map((seg, i) => {
        const dash = (seg.pct / 100) * circ;
        const gap = circ - dash;
        const el = (
          <circle
            key={seg.label}
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={seg.color}
            strokeWidth={stroke}
            strokeDasharray={`${visible ? dash : 0} ${circ}`}
            strokeDashoffset={-offset}
            strokeLinecap="butt"
            style={{
              transition: `stroke-dasharray 1.2s cubic-bezier(.16,1,.3,1) ${i * 0.12}s`,
              filter: `drop-shadow(0 0 8px ${seg.color}60)`,
              transformOrigin: `${cx}px ${cy}px`,
              transform: "rotate(-90deg)",
            }}
          />
        );
        offset += dash;
        return el;
      })}
      <text x={cx} y={cy - 6} textAnchor="middle" fill="#ffffff" fontSize="18" fontWeight="800" fontFamily="Space Grotesk, sans-serif">1B</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#9a9a9a" fontSize="10" fontFamily="Inter, sans-serif">Total Supply</text>
    </svg>
  );
}

export function Tokenomics() {
  const ref = useRef<HTMLDivElement>(null);
  const visible = useVisible(ref);
  const [active, setActive] = useState<number | null>(null);

  return (
    <div className="tokenomics-wrap" ref={ref}>
      <div className="section-head">
        <div className="section-tag">📊 Tokenomics</div>
        <div className="section-title">Token Distribution</div>
        <p className="section-sub">Total supply of 1,000,000,000 NXS distributed across five allocation pools.</p>
      </div>
      <div className="tokenomics-inner">
        <div className="tokenomics-chart">
          <DonutChart visible={visible} />
        </div>
        <div className="tokenomics-legend">
          {SEGMENTS.map((seg, i) => (
            <div
              key={seg.label}
              className={`tok-row${active === i ? " tok-row-active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
            >
              <div className="tok-color" style={{ background: seg.color, boxShadow: `0 0 10px ${seg.color}60` }} />
              <div className="tok-info">
                <div className="tok-label">{seg.label}</div>
                <div className="tok-desc">{seg.desc}</div>
              </div>
              <div className="tok-pct" style={{ color: seg.color }}>{seg.pct}%</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
