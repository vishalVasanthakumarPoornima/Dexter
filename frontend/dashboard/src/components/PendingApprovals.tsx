import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { getPending, approveCommand, denyCommand } from "../api/permissionsApi";

export default function PendingApprovals() {
  const [pending, setPending] = useState<string[]>([]);

  async function refresh() {
    const data = await getPending();
    setPending(data.pending ?? []);
  }

  async function approve(cmd: string) {
    await approveCommand(cmd);
    refresh();
  }

  async function deny(cmd: string) {
    await denyCommand(cmd);
    refresh();
  }

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);
    const interval = setInterval(refresh, 5000);
    return () => {
      window.clearTimeout(timer);
      clearInterval(interval);
    };
  }, []);

  if (pending.length === 0) return null;

  return (
    <section className="mini-panel pending-approvals">
      <h3>Pending Commands</h3>
      <ul>
        {pending.map((cmd) => (
          <li key={cmd} className="pending-row">
            <span>{cmd}</span>
            <div className="actions">
              <button onClick={() => approve(cmd)}><Check size={16} /></button>
              <button onClick={() => deny(cmd)}><X size={16} /></button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
