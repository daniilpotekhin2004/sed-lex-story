import { useMemo, useState } from "react";
import "./QuickCreateModal.css";

type ImportItem = {
  id: string;
  name: string;
  description?: string | null;
  detail?: string | null;
  badges?: string[];
};

export default function ImportAssetModal({
  title,
  note,
  items,
  onImport,
  onClose,
}: {
  title: string;
  note?: string;
  items: ImportItem[];
  onImport: (id: string) => Promise<void>;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => item.name.toLowerCase().includes(q));
  }, [items, query]);

  const handleImport = async (id: string) => {
    setBusyId(id);
    try {
      await onImport(id);
      onClose();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="qc-overlay">
      <div className="qc-modal" style={{ maxWidth: 560 }}>
        <div className="qc-header">
          <h2>{title}</h2>
          <button className="qc-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="qc-body" style={{ padding: "16px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          {note ? <div className="muted">{note}</div> : null}
          <input
            className="qc-input"
            placeholder="Поиск..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {filtered.length === 0 ? (
            <div className="muted">Нет совпадений.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {filtered.map((item) => (
                <div
                  key={item.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    padding: "10px 12px",
                    borderRadius: 12,
                    border: "1px solid rgba(148, 163, 184, 0.2)",
                    background: "rgba(15, 23, 42, 0.45)",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <strong>{item.name}</strong>
                    {item.description ? <span className="muted">{item.description}</span> : null}
                    {item.detail ? <span className="muted">{item.detail}</span> : null}
                    {item.badges && item.badges.length > 0 ? (
                      <div className="cvs-chip-row">
                        {item.badges.map((badge) => (
                          <span key={badge} className="cvs-chip">
                            {badge}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <button
                    className="secondary"
                    disabled={busyId === item.id}
                    onClick={() => handleImport(item.id)}
                  >
                    {busyId === item.id ? "Импорт..." : "Импорт"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
