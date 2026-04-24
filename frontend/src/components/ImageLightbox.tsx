import React from "react";

type Props = {
  url: string;
  title?: string;
  subtitle?: string;
  onClose: () => void;
};

export function ImageLightbox({ url, title, subtitle, onClose }: Props) {
  if (!url) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 1000 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            {title ? <h3 style={{ margin: 0 }}>{title}</h3> : null}
            {subtitle ? <div className="muted" style={{ marginTop: 4 }}>{subtitle}</div> : null}
          </div>
          <button className="secondary" onClick={onClose}>Закрыть</button>
        </div>

        <div style={{ marginTop: 12 }}>
          <a href={url} target="_blank" rel="noreferrer" className="link">
            Открыть в полном разрешении
          </a>
        </div>

        <div style={{ marginTop: 12 }}>
          <img src={url} alt={title ?? "изображение"} style={{ width: "100%", height: "70vh", objectFit: "contain" }} />
        </div>
      </div>
    </div>
  );
}
