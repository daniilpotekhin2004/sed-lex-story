import { apiClient } from "./client";
import type { Edge, ScenarioGraph, SceneNode, GraphValidationReport, SceneUsageResponse } from "../shared/types";

export async function createGraph(projectId: string, payload: { title: string; description?: string | null }) {
  const response = await apiClient.post<ScenarioGraph>(`/v1/projects/${projectId}/graphs`, {
    project_id: projectId,
    ...payload,
  });
  return response.data;
}

export async function getGraph(graphId: string): Promise<ScenarioGraph> {
  const response = await apiClient.get<ScenarioGraph>(`/v1/graphs/${graphId}`);
  return response.data;
}

export async function updateGraph(
  graphId: string,
  payload: Partial<{ title: string; description?: string | null; root_scene_id?: string | null }>,
): Promise<ScenarioGraph> {
  const response = await apiClient.patch<ScenarioGraph>(`/v1/graphs/${graphId}`, payload);
  return response.data;
}

export async function deleteGraph(graphId: string): Promise<void> {
  await apiClient.delete(`/v1/graphs/${graphId}`);
}

export async function createScene(
  graphId: string,
  payload: {
    title: string;
    content: string;
    synopsis?: string | null;
    scene_type?: "story" | "decision";
    location_id?: string | null;
    location_overrides?: Record<string, unknown> | null;
    artifacts?: { artifact_id: string; state?: string | null; notes?: string | null; importance?: number }[];
  },
): Promise<SceneNode> {
  const response = await apiClient.post<SceneNode>(`/v1/graphs/${graphId}/scenes`, payload);
  return response.data;
}

export async function updateScene(
  sceneId: string,
  payload: Partial<{
    title: string;
    content: string;
    synopsis?: string | null;
    scene_type?: "story" | "decision";
    context?: Record<string, unknown> | null;
    legal_concept_ids?: string[];
    location_id?: string | null;
    location_overrides?: Record<string, unknown> | null;
    order_index?: number | null;
    artifacts?: { artifact_id: string; state?: string | null; notes?: string | null; importance?: number }[];
  }>,
): Promise<SceneNode> {
  const response = await apiClient.patch<SceneNode>(`/v1/scenes/${sceneId}`, payload);
  return response.data;
}

export async function createEdge(
  graphId: string,
  payload: {
    from_scene_id: string;
    to_scene_id: string;
    choice_label?: string | null;
    condition?: string | null;
    edge_metadata?: Record<string, unknown> | null;
  },
): Promise<Edge> {
  const response = await apiClient.post<Edge>(`/v1/graphs/${graphId}/edges`, payload);
  return response.data;
}

export async function updateEdge(
  edgeId: string,
  payload: {
    choice_label?: string | null;
    condition?: string | null;
    edge_metadata?: Record<string, unknown> | null;
  },
): Promise<Edge> {
  const response = await apiClient.patch<Edge>(`/v1/edges/${edgeId}`, payload);
  return response.data;
}

export async function validateGraph(graphId: string): Promise<GraphValidationReport> {
  const response = await apiClient.get<GraphValidationReport>(`/v1/graphs/${graphId}/validate`);
  return response.data;
}

export async function getSceneUsage(
  graphId: string,
  params: { location_id?: string; character_id?: string; artifact_id?: string },
): Promise<SceneUsageResponse> {
  const response = await apiClient.get<SceneUsageResponse>(`/v1/graphs/${graphId}/usage`, { params });
  return response.data;
}
