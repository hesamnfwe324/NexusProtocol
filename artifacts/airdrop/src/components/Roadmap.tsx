const MILESTONES = [
  {
    q: "Q1 2024", title: "Protocol Launch",
    done: true,
    items: ["Smart contract deployment on Ethereum mainnet", "CertiK security audit completed", "v1.0 documentation published"],
  },
  {
    q: "Q2 2024", title: "Season 1 Snapshot",
    done: true,
    items: ["Block #19,284,112 snapshot captured", "78,400 eligible wallets identified", "Airdrop portal launched"],
  },
  {
    q: "Q3 2024", title: "Token Distribution",
    done: true,
    items: ["Phase 1 & 2 distributions complete", "Phase 3 live — claim window open", "$48M TVL milestone reached"],
  },
  {
    q: "Q4 2024", title: "Governance Launch",
    done: false, current: true,
    items: ["On-chain governance voting system", "Community treasury activation", "Season 2 snapshot announcement"],
  },
  {
    q: "Q1 2025", title: "Cross-chain Expansion",
    done: false,
    items: ["Arbitrum & Base bridge deployment", "Layer 2 airdrop support", "Mobile app (iOS & Android)"],
  },
];

export function Roadmap() {
  return (
    <div className="roadmap-wrap">
      <div className="section-head">
        <div className="section-tag">🗺️ Roadmap</div>
        <div className="section-title">Project Timeline</div>
      </div>
      <div className="roadmap-list">
        {MILESTONES.map((m, i) => (
          <div key={m.q} className={`rm-item${m.done ? " rm-done" : ""}${m.current ? " rm-current" : ""}`}>
            <div className="rm-left">
              <div className="rm-dot">
                {m.done ? (
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ) : m.current ? (
                  <div className="rm-dot-pulse" />
                ) : null}
              </div>
              {i < MILESTONES.length - 1 && <div className="rm-line" />}
            </div>
            <div className="rm-body">
              <div className="rm-header">
                <span className="rm-q">{m.q}</span>
                <span className="rm-title">{m.title}</span>
                {m.done && <span className="rm-badge rm-badge-done">✓ Complete</span>}
                {m.current && <span className="rm-badge rm-badge-live">● Live</span>}
                {!m.done && !m.current && <span className="rm-badge rm-badge-soon">Upcoming</span>}
              </div>
              <ul className="rm-items">
                {m.items.map(item => (
                  <li key={item} className="rm-item-li">
                    <span className="rm-li-dot" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
