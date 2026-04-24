import { apiClient } from "./client";

export interface SDModelInfo {
  title: string;
  model_name: string;
  hash?: string;
  sha256?: string;
  filename?: string;
}

export interface SamplerInfo {
  name: string;
  aliases: string[];
}

export interface SchedulerInfo {
  name: string;
  label: string;
}

export interface UpscalerInfo {
  name: string;
  model_name?: string;
  model_path?: string;
  model_url?: string;
  scale?: number;
}

export interface LoraInfo {
  name: string;
  alias?: string;
  path?: string;
}

export interface StyleInfo {
  name: string;
  prompt?: string;
  negative_prompt?: string;
}

export interface AllSDOptions {
  sd_models: SDModelInfo[];
  vae_models: string[];
  samplers: SamplerInfo[];
  schedulers: SchedulerInfo[];
  upscalers: UpscalerInfo[];
  loras: LoraInfo[];
  styles: StyleInfo[];
  controlnet_models: string[];
  controlnet_modules: string[];
  current_model?: string;
  current_vae?: string;
  current_sampler?: string;
  current_scheduler?: string;
}

export interface CurrentSDOptions {
  sd_model_checkpoint?: string;
  sd_vae?: string;
  CLIP_stop_at_last_layers?: number;
  sampler_name?: string;
  scheduler?: string;
}

export interface SetOptionsRequest {
  sd_model_checkpoint?: string;
  sd_vae?: string;
  CLIP_stop_at_last_layers?: number;
  sampler_name?: string;
  scheduler?: string;
}

// Get all available SD options for dropdowns
export async function getAllSDOptions(): Promise<AllSDOptions> {
  const response = await apiClient.get<AllSDOptions>("/v1/sd/options/all");
  return response.data;
}

// Get available SD models
export async function getSDModels(): Promise<{ models: SDModelInfo[]; count: number }> {
  const response = await apiClient.get<{ models: SDModelInfo[]; count: number }>("/v1/sd/options/models");
  return response.data;
}

// Get available VAE models
export async function getVAEModels(): Promise<{ vae_models: string[]; count: number }> {
  const response = await apiClient.get<{ vae_models: string[]; count: number }>("/v1/sd/options/vae");
  return response.data;
}

// Get available samplers
export async function getSamplers(): Promise<{ samplers: SamplerInfo[]; count: number }> {
  const response = await apiClient.get<{ samplers: SamplerInfo[]; count: number }>("/v1/sd/options/samplers");
  return response.data;
}

// Get available schedulers
export async function getSchedulers(): Promise<{ schedulers: SchedulerInfo[]; count: number }> {
  const response = await apiClient.get<{ schedulers: SchedulerInfo[]; count: number }>("/v1/sd/options/schedulers");
  return response.data;
}

// Get available upscalers
export async function getUpscalers(): Promise<{ upscalers: UpscalerInfo[]; count: number }> {
  const response = await apiClient.get<{ upscalers: UpscalerInfo[]; count: number }>("/v1/sd/options/upscalers");
  return response.data;
}

// Get available LoRAs
export async function getLoras(): Promise<{ loras: LoraInfo[]; count: number }> {
  const response = await apiClient.get<{ loras: LoraInfo[]; count: number }>("/v1/sd/options/loras");
  return response.data;
}

// Get available styles
export async function getStyles(): Promise<{ styles: StyleInfo[]; count: number }> {
  const response = await apiClient.get<{ styles: StyleInfo[]; count: number }>("/v1/sd/options/styles");
  return response.data;
}

// Get current SD options
export async function getCurrentOptions(): Promise<CurrentSDOptions> {
  const response = await apiClient.get<CurrentSDOptions>("/v1/sd/options/current");
  return response.data;
}

// Set SD options
export async function setSDOptions(options: SetOptionsRequest): Promise<{ success: boolean; options_set: string[] }> {
  const response = await apiClient.post<{ success: boolean; options_set: string[] }>("/v1/sd/options/set", options);
  return response.data;
}

// Refresh models
export async function refreshModels(): Promise<{ success: boolean }> {
  const response = await apiClient.post<{ success: boolean }>("/v1/sd/refresh/models");
  return response.data;
}

// Refresh VAE
export async function refreshVAE(): Promise<{ success: boolean }> {
  const response = await apiClient.post<{ success: boolean }>("/v1/sd/refresh/vae");
  return response.data;
}

// Refresh LoRAs
export async function refreshLoras(): Promise<{ success: boolean }> {
  const response = await apiClient.post<{ success: boolean }>("/v1/sd/refresh/loras");
  return response.data;
}
