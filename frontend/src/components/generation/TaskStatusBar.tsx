import React from "react";
import { useTaskStatus } from "../../hooks/useTaskStatus";

type Props = {
  taskId: string | null;
};

export const TaskStatusBar: React.FC<Props> = ({ taskId }) => {
  const { data, isFetching, isError, error } = useTaskStatus(taskId);

  if (!taskId) {
    return (
      <div className="status-bar muted">
        Задача не запущена. Сгенерируйте новое изображение, чтобы увидеть статус.
      </div>
    );
  }

  if (isError) {
    return <div className="status-bar error">Ошибка статуса задачи: {(error as Error).message}</div>;
  }

  return (
    <div className="status-bar">
      <div>
        <strong>Задача:</strong> {taskId}
      </div>
      <div>
        <strong>Статус:</strong> {data?.state ?? "—"}
        {isFetching && <span className="muted"> · обновляется...</span>}
      </div>
      {data?.ready && data.success && <div className="ok">Готово</div>}
      {data?.error && <div className="error">{data.error}</div>}
      {data?.result?.image_url && (
        <div>
          <a href={data.result.image_url} target="_blank" rel="noreferrer">
            Открыть изображение
          </a>
        </div>
      )}
    </div>
  );
};
