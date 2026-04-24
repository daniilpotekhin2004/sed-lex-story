import React, { useState } from "react";
import { useTasks } from "../hooks/useTasks";
import { TaskStatusBar } from "../components/generation/TaskStatusBar";

export const HistoryPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error } = useTasks({ page, page_size: 10 });
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className="stack">
      <div className="card">
        <div className="card-header">
          <h2>История задач</h2>
          <span className="muted">
            Всего: {data?.total ?? "—"} · Страница {data?.page ?? page}
          </span>
        </div>
        {isLoading && <div className="muted">Загрузка...</div>}
        {isError && <div className="error">Ошибка: {(error as Error).message}</div>}
        {data && data.items.length === 0 && <div className="muted">Задач пока нет.</div>}
        {data && data.items.length > 0 && (
          <ul className="task-list">
            {data.items.map((task) => (
              <li
                key={task.task_id}
                className="task-item"
                onClick={() => setSelected(task.task_id)}
                style={{ cursor: "pointer" }}
              >
                <div>
                  <div className="task-id">{task.task_id}</div>
                  <div className="muted small">{task.status}</div>
                </div>
                <div className="muted small">
                  {task.created_at}
                  {task.image_url && (
                    <div>
                      <a href={task.image_url} target="_blank" rel="noreferrer">
                        открыть
                      </a>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="pagination">
          <button
            className="secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ← Назад
          </button>
          <button
            className="secondary"
            disabled={Boolean(data && data.items.length < (data.page_size ?? 10))}
            onClick={() => setPage((p) => p + 1)}
          >
            Вперёд →
          </button>
        </div>
      </div>
      <TaskStatusBar taskId={selected} />
    </div>
  );
};
