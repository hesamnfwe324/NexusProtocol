import { useEffect, useRef } from "react";

const COLORS = ["#2563eb","#3b82f6","#0ea5e9","#60a5fa","#1d4ed8","#38bdf8","#6366f1","#93c5fd"];

export function ConfettiEffect({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const pieces = Array.from({ length: 120 }, () => ({
      x: Math.random() * canvas.width,
      y: -20 - Math.random() * 200,
      w: 6 + Math.random() * 8,
      h: 8 + Math.random() * 12,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      rot: Math.random() * Math.PI * 2,
      rotSpd: (Math.random() - 0.5) * 0.12,
      vx: (Math.random() - 0.5) * 4,
      vy: 2 + Math.random() * 4,
      gravity: 0.06 + Math.random() * 0.04,
      opacity: 1,
    }));

    let start = 0;
    function draw(ts: number) {
      if (!start) start = ts;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      let alive = false;
      for (const p of pieces) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += p.gravity;
        p.rot += p.rotSpd;
        if (p.y > canvas.height * 0.7) p.opacity = Math.max(0, p.opacity - 0.015);
        if (p.opacity > 0 && p.y < canvas.height + 40) alive = true;
        ctx.save();
        ctx.globalAlpha = p.opacity;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      if (alive) frameRef.current = requestAnimationFrame(draw);
    }
    frameRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frameRef.current);
  }, [active]);

  if (!active) return null;
  return <canvas ref={canvasRef} style={{ position:"fixed",inset:0,zIndex:9999,pointerEvents:"none" }} />;
}
