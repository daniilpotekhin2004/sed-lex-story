import type { Artifact, CharacterPreset, Location, ReferenceImage } from "../shared/types";

export type AssetSourceInfo = {
  origin: "generated" | "uploaded" | "unknown";
  provider?: string;
  providerLabel?: string;
};

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const readSource = (value: unknown): AssetSourceInfo | null => {
  const record = asRecord(value);
  if (!record) return null;
  const origin = typeof record.origin === "string" ? record.origin : typeof record.asset_origin === "string" ? record.asset_origin : null;
  if (!origin) return null;
  const provider = typeof record.provider === "string" ? record.provider : typeof record.asset_provider === "string" ? record.asset_provider : undefined;
  const providerLabel =
    typeof record.provider_label === "string"
      ? record.provider_label
      : typeof record.asset_provider_label === "string"
        ? record.asset_provider_label
        : undefined;
  if (origin === "generated" || origin === "uploaded") {
    return { origin, provider, providerLabel };
  }
  return { origin: "unknown", provider, providerLabel };
};

const readAssetMarker = (container: unknown, assetKey: string): AssetSourceInfo | null => {
  const record = asRecord(container);
  const assetSources = asRecord(record?.asset_sources);
  return readSource(assetSources?.[assetKey]);
};

export const getReferenceAssetSource = (ref: ReferenceImage | null | undefined): AssetSourceInfo | null =>
  readSource(ref?.meta?.asset_source ?? ref?.meta);

export const getCharacterPreviewAssetSource = (character: CharacterPreset | null | undefined): AssetSourceInfo | null => {
  const preview = character?.preview_image_url || character?.preview_thumbnail_url;
  if (!preview) return readAssetMarker(character?.appearance_profile, "preview");
  const matched = (character?.reference_images || []).find((ref) =>
    [ref?.url, ref?.thumb_url].some((value) => value && value === preview),
  );
  return getReferenceAssetSource(matched) || readAssetMarker(character?.appearance_profile, "preview");
};

export const getLocationPreviewAssetSource = (location: Location | null | undefined): AssetSourceInfo | null => {
  const preview = location?.preview_image_url || location?.preview_thumbnail_url;
  if (!preview) return readAssetMarker(location?.location_metadata, "preview");
  const matched = (location?.reference_images || []).find((ref) =>
    [ref?.url, ref?.thumb_url].some((value) => value && value === preview),
  );
  return getReferenceAssetSource(matched) || readAssetMarker(location?.location_metadata, "preview");
};

export const getArtifactPreviewAssetSource = (artifact: Artifact | null | undefined): AssetSourceInfo | null =>
  readAssetMarker(artifact?.artifact_metadata, "preview");

export const formatAssetSourceLabel = (source: AssetSourceInfo | null | undefined): string => {
  if (!source) return "Источник неизвестен";
  if (source.origin === "uploaded") return "Загружен";
  if (source.origin === "generated") {
    return source.providerLabel ? `Сгенерирован · ${source.providerLabel}` : "Сгенерирован";
  }
  return "Источник неизвестен";
};
