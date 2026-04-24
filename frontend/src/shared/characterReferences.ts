export type CharacterReferenceSlot = {
  kind: string;
  label: string;
  note?: string;
  group?: "view" | "pose";
  required?: boolean;
};

export const CHARACTER_REFERENCE_SLOTS: CharacterReferenceSlot[] = [
  { kind: "sketch", label: "Эскиз", note: "base", group: "view", required: false },
  { kind: "complex", label: "Комплексный", note: "blend", group: "view", required: false },
  { kind: "portrait", label: "Портрет", note: "portrait", group: "view", required: true },
  { kind: "full_front", label: "Полный рост", note: "front", group: "view", required: true },
  { kind: "full_side", label: "Рост 45°", note: "45deg", group: "view", required: true },
  { kind: "full_back", label: "Полный рост", note: "back", group: "view", required: true },
];

export const REQUIRED_CHARACTER_REFERENCE_KINDS = CHARACTER_REFERENCE_SLOTS.filter(
  (slot) => slot.required !== false,
).map((slot) => slot.kind);

export const VIEW_REFERENCE_KINDS = CHARACTER_REFERENCE_SLOTS.filter((slot) => slot.group !== "pose").map(
  (slot) => slot.kind,
);

export const POSE_REFERENCE_KINDS = CHARACTER_REFERENCE_SLOTS.filter((slot) => slot.group === "pose").map(
  (slot) => slot.kind,
);

export const CREATIVE_CHARACTER_REFERENCE_KINDS = ["portrait", "full_front"] as const;
