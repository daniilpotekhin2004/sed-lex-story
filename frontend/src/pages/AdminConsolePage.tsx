import { useCallback, useEffect, useMemo, useState } from "react";
import {
  bulkUpdateUserRoles,
  getAdminOverview,
  getAdminUserStats,
  getComfyOverview,
  getErrorFeed,
  getRoleAudit,
  listAdminUsers,
  updateUserCohort,
  updateUserRole,
} from "../api/admin";
import { listServices } from "../api/ops";
import type {
  AdminOverviewResponse,
  AdminUserSummary,
  ComfyOverviewResponse,
  ErrorFeedItem,
  RoleAuditRead,
  ServiceStatus,
  UserStatsResponse,
} from "../shared/types";

const ROLE_OPTIONS = [
  { value: "admin", label: "Админ" },
  { value: "author", label: "Автор" },
  { value: "player", label: "Игрок" },
] as const;

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "0";
  return Intl.NumberFormat("ru-RU").format(value);
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "USD" }).format(value);
}

function roleLabel(role: string) {
  const normalized = role.toLowerCase();
  if (normalized === "admin") return "Админ";
  if (normalized === "author") return "Автор";
  if (normalized === "player") return "Игрок";
  return role;
}

function normalizeCohortCode(value: string | null | undefined) {
  const normalized = (value || "").trim().toUpperCase();
  return normalized || "";
}

export default function AdminConsolePage() {
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [overview, setOverview] = useState<AdminOverviewResponse | null>(null);
  const [comfy, setComfy] = useState<ComfyOverviewResponse | null>(null);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [errorsFeed, setErrorsFeed] = useState<ErrorFeedItem[]>([]);
  const [roleAudit, setRoleAudit] = useState<RoleAuditRead[]>([]);

  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [selectedStats, setSelectedStats] = useState<UserStatsResponse | null>(null);
  const [selectedStatsLoading, setSelectedStatsLoading] = useState(false);

  const [draftRoles, setDraftRoles] = useState<Record<string, string>>({});
  const [draftCohorts, setDraftCohorts] = useState<Record<string, string>>({});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkRole, setBulkRole] = useState("author");
  const [bulkReason, setBulkReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [overviewResp, comfyResp, usersResp, auditResp, errorsResp, servicesResp] = await Promise.all([
        getAdminOverview(),
        getComfyOverview(),
        listAdminUsers({
          page,
          page_size: pageSize,
          search: search.trim() || undefined,
          role: roleFilter || undefined,
        }),
        getRoleAudit({ page: 1, page_size: 40 }),
        getErrorFeed(60),
        listServices(),
      ]);
      setOverview(overviewResp);
      setComfy(comfyResp);
      setUsers(usersResp.items);
      setUsersTotal(usersResp.total);
      setRoleAudit(auditResp.items);
      setErrorsFeed(errorsResp.items);
      setServices(servicesResp.services);
      setDraftRoles((prev) => {
        const next = { ...prev };
        for (const user of usersResp.items) {
          if (!next[user.id]) next[user.id] = user.role;
        }
        return next;
      });
      setDraftCohorts((prev) => {
        const next = { ...prev };
        for (const user of usersResp.items) {
          if (next[user.id] === undefined) next[user.id] = user.cohort_code || "";
        }
        return next;
      });
      if (!selectedUserId && usersResp.items.length > 0) {
        setSelectedUserId(usersResp.items[0].id);
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить данные админ-панели.");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, roleFilter, search, selectedUserId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedUserId) {
      setSelectedStats(null);
      return;
    }
    let cancelled = false;
    const run = async () => {
      setSelectedStatsLoading(true);
      try {
        const stats = await getAdminUserStats(selectedUserId);
        if (!cancelled) setSelectedStats(stats);
      } catch (err: any) {
        if (!cancelled) setError(err?.message || "Не удалось загрузить статистику пользователя.");
      } finally {
        if (!cancelled) setSelectedStatsLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [selectedUserId]);

  const groupedUsers = useMemo(() => {
    const groups: Record<string, AdminUserSummary[]> = { admin: [], author: [], player: [] };
    for (const user of users) {
      const key = user.role.toLowerCase();
      if (!groups[key]) groups[key] = [];
      groups[key].push(user);
    }
    return groups;
  }, [users]);

  const toggleSelected = (userId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  };

  const applySingleRole = async (user: AdminUserSummary) => {
    const targetRole = (draftRoles[user.id] || user.role).toLowerCase();
    const targetCohort = normalizeCohortCode(draftCohorts[user.id] ?? "");
    const currentCohort = normalizeCohortCode(user.cohort_code);
    const roleChanged = targetRole !== user.role.toLowerCase();
    const cohortChanged = targetCohort !== currentCohort;
    if (!roleChanged && !cohortChanged) return;
    const confirmAdmin = targetRole === "admin" ? window.confirm("Назначить пользователю роль Админ?") : true;
    if (roleChanged && !confirmAdmin) return;
    setBusyAction(true);
    setError(null);
    try {
      if (roleChanged) {
        await updateUserRole(user.id, {
          role: targetRole as "admin" | "author" | "player",
          confirm_assign_admin: targetRole === "admin",
        });
      }
      if (cohortChanged) {
        await updateUserCohort(user.id, {
          cohort_code: targetCohort || null,
        });
      }
      await load();
    } catch (err: any) {
      setError(err?.message || "Не удалось обновить пользователя.");
    } finally {
      setBusyAction(false);
    }
  };

  const applyBulkRole = async () => {
    if (!selectedIds.size) return;
    const confirmAdmin = bulkRole === "admin" ? window.confirm("Назначить выбранных пользователей администраторами?") : true;
    if (!confirmAdmin) return;
    setBusyAction(true);
    setError(null);
    try {
      await bulkUpdateUserRoles({
        user_ids: Array.from(selectedIds),
        role: bulkRole as "admin" | "author" | "player",
        reason: bulkReason.trim() || undefined,
        confirm_assign_admin: bulkRole === "admin",
      });
      setSelectedIds(new Set());
      setBulkReason("");
      await load();
    } catch (err: any) {
      setError(err?.message || "Не удалось выполнить массовую смену ролей.");
    } finally {
      setBusyAction(false);
    }
  };

  if (loading) {
    return <div className="admin-shell">Загрузка админ-панели...</div>;
  }

  return (
    <div className="admin-shell">
      <section className="admin-hero">
        <div>
          <div className="admin-kicker">RBAC</div>
          <h1>Администрирование проекта</h1>
          <p>Пользователи, роли, агрегированная статистика, Comfy API, сервисы и аудит в одном месте.</p>
        </div>
        <div className="admin-hero-actions">
          <button className="secondary" onClick={() => void load()} disabled={busyAction}>
            Обновить
          </button>
        </div>
      </section>

      {error && <div className="admin-error">{error}</div>}

      <section className="admin-cards">
        <div className="admin-card">
          <h3>Пользователи</h3>
          <strong>{formatNumber(overview?.users_total)}</strong>
          <small>
            Админы: {formatNumber(overview?.users_by_role?.admin)} | Авторы: {formatNumber(overview?.users_by_role?.author)} | Игроки:{" "}
            {formatNumber(overview?.users_by_role?.player)}
          </small>
        </div>
        <div className="admin-card">
          <h3>Comfy API</h3>
          <strong>{formatNumber(comfy?.total_units)} ед.</strong>
          <small>Оценка расходов: {formatMoney(comfy?.estimated_spend_total_usd)}</small>
        </div>
        <div className="admin-card">
          <h3>Баланс</h3>
          <strong>{formatMoney(comfy?.configured_balance_usd)}</strong>
          <small>Остаток (оценка): {formatMoney(comfy?.estimated_remaining_balance_usd)}</small>
        </div>
      </section>

      <section className="admin-grid">
        <div className="admin-panel">
          <div className="admin-panel-header">
            <h2>Пользователи</h2>
            <div className="admin-inline">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Поиск: username / email / id"
              />
              <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                <option value="">Все роли</option>
                {ROLE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button className="secondary" onClick={() => setPage(1)}>
                Применить
              </button>
            </div>
          </div>
          <div className="admin-inline admin-bulk">
            <select value={bulkRole} onChange={(event) => setBulkRole(event.target.value)}>
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <input
              value={bulkReason}
              onChange={(event) => setBulkReason(event.target.value)}
              placeholder="Причина (опционально)"
            />
            <button className="primary" onClick={applyBulkRole} disabled={busyAction || selectedIds.size === 0}>
              Назначить выбранным ({selectedIds.size})
            </button>
          </div>

          {(["admin", "author", "player"] as const).map((roleKey) => (
            <div key={roleKey} className="admin-group">
              <h3>
                {roleLabel(roleKey)} ({groupedUsers[roleKey]?.length || 0})
              </h3>
              <div className="admin-users-list">
                {(groupedUsers[roleKey] || []).map((user) => (
                  <div key={user.id} className={`admin-user-row ${selectedUserId === user.id ? "active" : ""}`}>
                    <label className="admin-check">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(user.id)}
                        onChange={() => toggleSelected(user.id)}
                      />
                    </label>
                    <button className="admin-user-main" onClick={() => setSelectedUserId(user.id)}>
                      <strong>{user.username}</strong>
                      <span>{user.email}</span>
                      <small>
                        ассеты: {user.assets_total} | квесты: {user.quests_total} | comfy: {user.comfy_units_total} | когорта:{" "}
                        {user.cohort_code || "—"}
                      </small>
                    </button>
                    <select
                      value={draftRoles[user.id] || user.role}
                      onChange={(event) =>
                        setDraftRoles((prev) => ({
                          ...prev,
                          [user.id]: event.target.value,
                        }))
                      }
                    >
                      {ROLE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <input
                      className="input admin-cohort-input"
                      value={draftCohorts[user.id] ?? ""}
                      onChange={(event) =>
                        setDraftCohorts((prev) => ({
                          ...prev,
                          [user.id]: event.target.value,
                        }))
                      }
                      placeholder="Когорта"
                    />
                    <button className="secondary" onClick={() => void applySingleRole(user)} disabled={busyAction}>
                      Сохранить
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}

          <div className="admin-pagination">
            <button className="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              ← Назад
            </button>
            <span>
              Страница {page} / {Math.max(1, Math.ceil(usersTotal / pageSize))}
            </span>
            <button
              className="secondary"
              disabled={page >= Math.ceil(usersTotal / pageSize)}
              onClick={() => setPage((value) => value + 1)}
            >
              Далее →
            </button>
          </div>
        </div>

        <div className="admin-panel">
          <h2>Профиль и статистика</h2>
          {!selectedUserId && <p className="muted">Выберите пользователя.</p>}
          {selectedStatsLoading && <p className="muted">Загрузка...</p>}
          {selectedStats && (
            <div className="admin-stats">
              <h3>
                {selectedStats.user.username} ({roleLabel(selectedStats.user.role)})
              </h3>
              <div className="admin-user-cohort-summary">Когорта: {selectedStats.user.cohort_code || "не задана"}</div>
              <div className="admin-stats-grid">
                <div>
                  <span>Ассеты</span>
                  <strong>{formatNumber(selectedStats.assets.total)}</strong>
                </div>
                <div>
                  <span>Квесты</span>
                  <strong>{formatNumber(selectedStats.quests.total)}</strong>
                </div>
                <div>
                  <span>Время генерации</span>
                  <strong>{formatNumber(selectedStats.time.total_hours)} ч</strong>
                </div>
                <div>
                  <span>Comfy units</span>
                  <strong>{formatNumber(selectedStats.comfy?.units_total ?? 0)}</strong>
                </div>
              </div>
              {selectedStats.comfy && (
                <div className="admin-comfy-mini">
                  <span>Расход (оценка): {formatMoney(selectedStats.comfy.estimated_spend_total_usd)}</span>
                  <span>За период: {formatMoney(selectedStats.comfy.estimated_spend_period_usd)}</span>
                </div>
              )}
              <details>
                <summary>Последние ассеты</summary>
                <ul className="admin-list">
                  {selectedStats.assets.items.slice(0, 12).map((item) => (
                    <li key={`${item.type}-${item.id}`}>
                      <strong>{item.name}</strong> <span>{item.type}</span>
                    </li>
                  ))}
                </ul>
              </details>
              <details>
                <summary>Квесты</summary>
                <ul className="admin-list">
                  {selectedStats.quests.items.slice(0, 12).map((item) => (
                    <li key={item.id}>
                      <strong>{item.title}</strong> <span>{item.project_name || item.project_id}</span>
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}
        </div>
      </section>

      <section className="admin-grid admin-grid-bottom">
        <div className="admin-panel">
          <h2>Сервисы</h2>
          <div className="admin-list-grid">
            {services.map((service) => (
              <div key={service.id} className="admin-service-row">
                <strong>{service.name}</strong>
                <span className={`pill ${service.status === "ok" ? "ok" : service.status === "down" ? "danger" : ""}`}>
                  {service.status}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="admin-panel">
          <h2>Лента ошибок</h2>
          <ul className="admin-list">
            {errorsFeed.slice(0, 20).map((item, idx) => (
              <li key={`${item.source}-${idx}`}>
                <strong>{item.level.toUpperCase()}</strong>
                <span>{item.source}</span>
                <small>{item.message}</small>
              </li>
            ))}
            {errorsFeed.length === 0 && <li className="muted">Нет ошибок</li>}
          </ul>
        </div>
        <div className="admin-panel">
          <h2>Аудит ролей</h2>
          <ul className="admin-list">
            {roleAudit.slice(0, 20).map((item) => (
              <li key={item.id}>
                <strong>
                  {item.user_username || item.user_id}: {item.from_role} → {item.to_role}
                </strong>
                <span>{item.actor_username || item.actor_user_id}</span>
                <small>{new Date(item.created_at).toLocaleString()}</small>
              </li>
            ))}
            {roleAudit.length === 0 && <li className="muted">Аудит пуст</li>}
          </ul>
        </div>
      </section>
    </div>
  );
}
