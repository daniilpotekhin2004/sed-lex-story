import type { CSSProperties } from "react";

type Props = {
  label: string;
  busyLabel?: string;
  busy?: boolean;
  disabled?: boolean;
  className?: string;
  accept?: string;
  onSelect: (file: File) => Promise<void> | void;
};

const labelStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
};

export default function UploadButton({
  label,
  busyLabel = "Загрузка...",
  busy = false,
  disabled = false,
  className = "secondary",
  accept = "image/*",
  onSelect,
}: Props) {
  return (
    <label className={className} style={{ ...labelStyle, opacity: disabled ? 0.6 : 1, pointerEvents: disabled ? "none" : "auto" }}>
      <input
        hidden
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={async (event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          await onSelect(file);
        }}
      />
      {busy ? busyLabel : label}
    </label>
  );
}
