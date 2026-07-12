import { useEffect, useRef, useState } from "react";

const FEED_DATA = [
  { addr:"0x3a7f…b12c", amount:"1,800", time:"just now",    chain:"ETH" },
  { addr:"0x9d4e…f03a", amount:"2,500", time:"1m ago",      chain:"ETH" },
  { addr:"0x5c12…77de", amount:"3,200", time:"2m ago",      chain:"ETH" },
  { addr:"0x8b9a…c44f", amount:"1,200", time:"3m ago",      chain:"ETH" },
  { addr:"0x1e5d…9b21", amount:"4,000", time:"5m ago",      chain:"ETH" },
  { addr:"0xfa3c…6e80", amount:"2,500", time:"6m ago",      chain:"ETH" },
  { addr:"0x2d81…a39e", amount:"1,500", time:"8m ago",      chain:"ETH" },
  { addr:"0x7c44…b88d", amount:"3,800", time:"9m ago",      chain:"ETH" },
  { addr:"0xf1b3…209c", amount:"2,000", time:"11m ago",     chain:"ETH" },
  { addr:"0xa94e…5f2b", amount:"1,200", time:"13m ago",     chain:"ETH" },
  { addr:"0xc38d…77a1", amount:"3,000", time:"15m ago",     chain:"ETH" },
  { addr:"0xbb21…e840", amount:"2,500", time:"17m ago",     chain:"ETH" },
];

export function LiveFeed() {
  const [items, setItems] = useState(FEED_DATA.slice(0, 6));
  const tickRef = useRef(0);

  useEffect(() => {
    const t = setInterval(() => {
      tickRef.current = (tickRef.current + 1) % FEED_DATA.length;
      const newItem = { ...FEED_DATA[tickRef.current], time: "just now" };
      setItems(prev => {
        const updated = prev.map(i => ({
          ...i,
          time: i.time === "just now" ? "1m ago" : i.time === "1m ago" ? "2m ago" : i.time
        }));
        return [newItem, ...updated.slice(0, 5)];
      });
    }, 7000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="livefeed-wrap">
      <div className="section-head">
        <div className="section-tag">
          <div className="live-dot" style={{width:6,height:6}} />
          Live Activity
        </div>
        <div className="section-title">Recent Claims</div>
      </div>
      <div className="livefeed-list">
        {items.map((item, i) => (
          <div key={`${item.addr}-${i}`} className={`livefeed-row${i === 0 ? " livefeed-new" : ""}`}>
            <div className="livefeed-avatar">{item.addr.slice(2, 4).toUpperCase()}</div>
            <div className="livefeed-info">
              <div className="livefeed-addr">{item.addr}</div>
              <div className="livefeed-time">{item.time}</div>
            </div>
            <div className="livefeed-right">
              <div className="livefeed-amount">+{item.amount} NXS</div>
              <div className="livefeed-chain">{item.chain}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="livefeed-footer">
        Showing live on-chain activity · Updated in real-time
      </div>
    </div>
  );
}
