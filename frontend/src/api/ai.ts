import { apiClient } from "./client";

export type AIDescriptionResponse = {
  description: string;
  model?: string;
  usage?: Record<string, unknown> | null;
  request_id?: string | null;
};

export type AIFieldSpec = {
  key: string;
  label?: string;
  type?: "string" | "number" | "integer" | "boolean" | "array" | "object";
  options?: string[];
  description?: string;
};

export type AIFormFillResponse = {
  values: Record<string, unknown>;
  model?: string;
  usage?: Record<string, unknown> | null;
  request_id?: string | null;
};

export type VoicePreviewResponse = {
  data: ArrayBuffer;
  contentType: string;
};

export async function generateDescription(payload: {
  entity_type: string;
  name: string;
  context?: string;
  language?: string;
  tone?: string;
}): Promise<AIDescriptionResponse> {
  const response = await apiClient.post<AIDescriptionResponse>("/ai/description", payload);
  return response.data;
}

export async function generateFormFill(payload: {
  form_type: string;
  fields: AIFieldSpec[];
  current_values?: Record<string, unknown>;
  context?: string;
  extra_context?: string;
  language?: string;
  detail_level?: "narrow" | "standard" | "detailed";
  fill_only_empty?: boolean;
}): Promise<AIFormFillResponse> {
  const response = await apiClient.post<AIFormFillResponse>("/ai/form-fill", payload);
  return response.data;
}

export async function generateVoicePreview(payload: {
  text: string;
  voice_profile?: string | null;
  language?: string;
}): Promise<VoicePreviewResponse> {
  const response = await apiClient.post<ArrayBuffer>("/ai/voice-preview", payload, {
    responseType: "arraybuffer",
  });
  const contentType = typeof response.headers["content-type"] === "string"
    ? response.headers["content-type"]
    : "audio/mpeg";
  return { data: response.data, contentType };
}
