import React from "react";

type Props = {
  outputs?: string[];
};

export const ResultsGrid: React.FC<Props> = ({ outputs }) => {
  if (!outputs || outputs.length === 0) {
    return <div className="card muted">Результаты появятся после завершения задачи.</div>;
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Сгенерированные варианты</h3>
        <span className="muted">{outputs.length} шт.</span>
      </div>
      <div className="grid results-grid">
        {outputs.map((src, idx) => (
          <figure key={src + idx} className="result-card">
            <div className="result-thumb">
              <img src={src} alt={`вариант-${idx + 1}`} />
            </div>
            <figcaption className="muted small">{src}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
};
