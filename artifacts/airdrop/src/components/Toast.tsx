import { useState, useEffect, useCallback, useRef } from "react";

export type ToastType = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastItemProps {
  toast: Toast;
  onRemove: (id: string) => void;
}

function ToastItem({ toast, onRemove }: ToastItemProps) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t1 = setTimeout(() => setVisible(true), 10);
    const t2 = setTimeout(() => { setVisible(false); setTimeout(() => onRemove(toast.id), 380); }, 4000);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [toast.id, onRemove]);

  const icons: Record<ToastType, string> = {
    success: "✓", error: "✕", info: "ℹ", warning: "⚠"
  };

  return (
    <div className={`toast toast-${toast.type}${visible ? " toast-in" : ""}`}>
      <div className="toast-icon">{icons[toast.type]}</div>
      <div className="toast-body">
        <div className="toast-title">{toast.title}</div>
        {toast.message && <div className="toast-msg">{toast.message}</div>}
      </div>
      <button className="toast-close" onClick={() => { setVisible(false); setTimeout(() => onRemove(toast.id), 380); }}>✕</button>
    </div>
  );
}

let _push: ((t: Omit<Toast, "id">) => void) | null = null;
export function pushToast(t: Omit<Toast, "id">) { _push?.(t); }

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const removeToast = useCallback((id: string) => setToasts(ts => ts.filter(t => t.id !== id)), []);
  useEffect(() => {
    _push = (t) => setToasts(ts => [...ts, { ...t, id: crypto.randomUUID() }]);
    return () => { _push = null; };
  }, []);

  return (
    <div className="toast-container">
      {toasts.map(t => <ToastItem key={t.id} toast={t} onRemove={removeToast} />)}
    </div>
  );
}
