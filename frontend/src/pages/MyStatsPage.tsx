import { useEffect, useState } from "react";
import { getMyRoleStats } from "../api/admin";
import type { UserStatsResponse } from "../shared/types";
import { useRole } from "../auth/useRole";

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "0";
  return Intl.NumberFormat("ru-RU").format(value);
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "USD" }).format(value);
}

export default function MyStatsPage() {
  const { isPlayer } = useRole();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<UserStatsResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getMyRoleStats();
        if (!cancelled) setStats(data);
      } catch (err: any) {
        if (!cancelled) setError(err?.message || "Не удалось загрузить статистику.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <div className="admin-shell">Загрузка статистики...</div>;
  if (error) return <div className="admin-error">{error}</div>;
  if (!stats) return <div className="admin-shell">Нет данных.</div>;

  return (
    <div className="admin-shell">
      <section className="admin-hero">
        <div>
          <div className="admin-kicker">Профиль</div>
          <h1>Статистика</h1>
          <p>Личные показатели по ассетам, времени генерации и квестам.</p>
        </div>
      </section>

      <section className="admin-cards">
        <div className="admin-card">
          <h3>Ассеты</h3>
          <strong>{formatNumber(stats.assets.total)}</strong>
        </div>
        <div className="admin-card">
          <h3>Квесты</h3>
          <strong>{formatNumber(stats.quests.total)}</strong>
        </div>
        <div className="admin-card">
          <h3>Время генерации</h3>
          <strong>{formatNumber(stats.time.total_hours)} ч</strong>
        </div>
        {!isPlayer && stats.comfy && (
          <div className="admin-card">
            <h3>Comfy API (оценка)</h3>
            <strong>{formatMoney(stats.comfy.estimated_spend_total_usd)}</strong>
            <small>Units: {formatNumber(stats.comfy.units_total)}</small>
          </div>
        )}
      </section>

      <section className="admin-grid admin-grid-bottom">
        <div className="admin-panel">
          <h2>Последние ассеты</h2>
          <ul className="admin-list">
            {stats.assets.items.slice(0, 20).map((item) => (
              <li key={`${item.type}-${item.id}`}>
                <strong>{item.name}</strong>
                <span>{item.type}</span>
              </li>
            ))}
            {stats.assets.items.length === 0 && <li className="muted">Ассетов пока нет</li>}
          </ul>
        </div>
        <div className="admin-panel">
          <h2>Квесты</h2>
          <ul className="admin-list">
            {stats.quests.items.slice(0, 20).map((item) => (
              <li key={item.id}>
                <strong>{item.title}</strong>
                <span>{item.project_name || item.project_id}</span>
              </li>
            ))}
            {stats.quests.items.length === 0 && <li className="muted">Квестов пока нет</li>}
          </ul>
        </div>
        <div className="admin-panel">
          <h2>Недельная динамика</h2>
          <ul className="admin-list">
            {stats.assets.weekly.slice(-12).reverse().map((point) => (
              <li key={point.week}>
                <strong>{point.week}</strong>
                <span>Ассеты: {formatNumber(point.value)}</span>
              </li>
            ))}
            {stats.assets.weekly.length === 0 && <li className="muted">Нет данных</li>}
          </ul>
        </div>
      </section>
    </div>
  );
}
