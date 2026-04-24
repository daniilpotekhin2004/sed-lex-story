import { useCallback, useEffect, useMemo, useState } from "react";
import { controlService, listServices } from "../api/ops";
import type { ServiceStatus } from "../shared/types";

const STATUS_LABELS: Record<string, string> = {
  ok: "Онлайн",
  down: "Оффлайн",
  degraded: "Деградирует",
  unknown: "Неизвестно",
};

const ACTION_LABELS: Record<string, string> = {
  start: "Запуск",
  restart: "Перезапуск",
  stop: "Остановить",
};

export default function OpsConsolePage() {
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<Record<string, string | null>>({});
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [composeAvailable, setComposeAvailable] = useState(false);
  const [projectRoot, setProjectRoot] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listServices();
      setServices(data.services);
      setComposeAvailable(data.compose_available);
      setProjectRoot(data.project_root || null);
      setLastUpdated(new Date().toLocaleTimeString());
      setError(null);
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить статус сервисов.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = useMemo(() => {
    return services.reduce(
      (acc, service) => {
        acc[service.status] = (acc[service.status] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>,
    );
  }, [services]);

  async function handleAction(serviceId: string, action: "start" | "restart" | "stop") {
    try {
      setActionState((prev) => ({ ...prev, [serviceId]: action }));
      setError(null); // Clear previous errors
      
      const result = await controlService(serviceId, action);
      
      if (!result.success) {
        const errorMsg = result.error || result.output || "Команда завершилась с ошибкой.";
        setError(`${ACTION_LABELS[action]} ${serviceId}: ${errorMsg}`);
        console.error(`Service control failed:`, result);
      } else {
        // Success - update service status
        if (result.service) {
          setServices((prev) => prev.map((item) => (item.id === serviceId ? result.service! : item)));
        } else {
          // Reload all services if specific service not returned
          await load();
        }
        // Show success message briefly
        const successMsg = `${ACTION_LABELS[action]} ${serviceId} выполнен успешно`;
        console.log(successMsg, result.output);
      }
    } catch (err: any) {
      const errorMsg = err?.message || "Не удалось выполнить команду.";
      setError(`${ACTION_LABELS[action]} ${serviceId}: ${errorMsg}`);
      console.error(`Service control error:`, err);
    } finally {
      setActionState((prev) => ({ ...prev, [serviceId]: null }));
    }
  }

  if (loading) {
    return <div className="ops-shell">Загрузка статусов сервисов...</div>;
  }

  return (
    <div className="ops-shell">
      <div className="ops-hero">
        <div>
          <div className="ops-kicker">Операции</div>
          <h1>Центр управления сервисами</h1>
          <p>Отслеживайте состояние стека и перезапускайте сервисы, не выходя из приложения.</p>
          {lastUpdated && <span className="ops-muted">Обновлено {lastUpdated}</span>}
        </div>
        <div className="ops-summary">
          <div>
            <strong>{summary.ok || 0}</strong>
            <span>Онлайн</span>
          </div>
          <div>
            <strong>{summary.degraded || 0}</strong>
            <span>Деградирует</span>
          </div>
          <div>
            <strong>{summary.down || 0}</strong>
            <span>Оффлайн</span>
          </div>
        </div>
        <div className="ops-actions">
          <button className="secondary" onClick={load}>Обновить</button>
        </div>
      </div>

      {error && <div className="ops-error">{error}</div>}

      <div className="ops-grid">
        {services.map((service) => (
          <div key={service.id} className={`ops-card status-${service.status}`}>
            <div className="ops-card-header">
              <div>
                <h2>{service.name}</h2>
                <span className={`ops-pill ${service.status}`}>{STATUS_LABELS[service.status] || service.status}</span>
              </div>
              <div className="ops-meta">
                {service.url && <span>{service.url}</span>}
                {!service.url && service.host && service.port && (
                  <span>
                    {service.host}:{service.port}
                  </span>
                )}
              </div>
            </div>
            <div className="ops-details">
              {service.details && (
                <pre>{JSON.stringify(service.details, null, 2)}</pre>
              )}
              {!service.details && <span className="ops-muted">Нет подробностей</span>}
            </div>
            <div className="ops-card-actions">
              {service.controllable ? (
                service.actions.map((action) => (
                  <button
                    key={action}
                    className={action === "restart" ? "primary" : "secondary"}
                    onClick={() => handleAction(service.id, action as "start" | "restart" | "stop")}
                    disabled={Boolean(actionState[service.id])}
                  >
                    {actionState[service.id] === action ? "Выполняется..." : ACTION_LABELS[action] || action}
                  </button>
                ))
              ) : (
                <span className="ops-muted">Управление недоступно</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {!composeAvailable && (
        <div className="ops-note">
          Docker Compose не найден. Управление сервисами недоступно.
        </div>
      )}
      {composeAvailable && projectRoot && (
        <div className="ops-note">Корень Compose: {projectRoot}</div>
      )}
    </div>
  );
}
