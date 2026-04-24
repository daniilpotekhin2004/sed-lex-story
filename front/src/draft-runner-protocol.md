import React from "react";
import { useTaskStore } from "../../hooks/useTaskStore";

type Props = {
  onSelect: (taskId: string) => void;
};

export const TaskHistory: React.FC<Props> = ({ onSelect }) => {
  const tasks = useTaskStore((s) => s.tasks);

  if (!tasks.length) {
    return <div className="card muted">История пуста — запустите первую генерацию.</div>;
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Последние задачи</h3>
        <span className="muted">{tasks.length} шт.</span>
      </div>
      <ul className="task-list">
        {tasks.map((task) => (
          <li key={task.taskId} className="task-item" onClick={() => onSelect(task.taskId)}>
            <div>
              <div className="task-id">{task.taskId}</div>
              <div className="muted small">{new Date(task.createdAt).toLocaleTimeString()}</div>
            </div>
            <div className={`pill ${task.success ? "ok" : ""}`}>
              {task.lastState ?? "ожидание"}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};
