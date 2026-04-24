import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import SceneEditorPanel from "../components/SceneEditorPanel";
import type { SceneNode } from "../shared/types";

const mockLegal = vi.hoisted(() => [{ id: "lc1", code: "LC1", title: "Contract", description: "", difficulty: 1 }]);

const mockUpdate = vi.fn().mockResolvedValue({
  id: "s1",
  graph_id: "g1",
  title: "Updated",
  content: "Updated content",
  synopsis: "",
  scene_type: "story",
  legal_concepts: mockLegal,
});

vi.mock("../components/CharacterSelector", () => ({
  default: () => <div data-testid="character-selector" />,
}));

vi.mock("../api/legal", () => ({
  listLegalConcepts: vi.fn().mockResolvedValue(mockLegal),
}));

vi.mock("../api/scenario", () => ({
  updateScene: (...args: unknown[]) => mockUpdate(...args),
}));

vi.mock("../api/generation", () => ({
  previewScenePrompt: vi.fn().mockResolvedValue({ prompt: "p", negative_prompt: null, config: {} }),
  generateSceneImage: vi.fn().mockResolvedValue({ id: "job1", status: "queued" }),
  getSceneImages: vi.fn().mockResolvedValue([]),
  getGenerationJob: vi.fn().mockResolvedValue({ status: "done" }),
}));

const baseScene: SceneNode = {
  id: "s1",
  graph_id: "g1",
  title: "Scene 1",
  content: "Courtroom content",
  synopsis: "",
  scene_type: "story",
  legal_concepts: [],
};

describe("SceneEditorPanel", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders legal concepts and calls update on save", async () => {
    const onSceneUpdated = vi.fn();

    render(<SceneEditorPanel scene={baseScene} onSceneUpdated={onSceneUpdated} />);

    await waitFor(() => expect(screen.getByText("Legal concepts")).toBeInTheDocument());
    const checkbox = screen.getByLabelText(/Contract/);
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByText(/Save scene/i));

    await waitFor(() => expect(onSceneUpdated).toHaveBeenCalled());
    expect(mockUpdate).toHaveBeenCalledWith(
      baseScene.id,
      expect.objectContaining({ legal_concept_ids: ["lc1"] })
    );
  });

  it("starts generation and shows job status", async () => {
    render(<SceneEditorPanel scene={baseScene} />);

    await waitFor(() => expect(screen.getByText("Legal concepts")).toBeInTheDocument());

    fireEvent.click(screen.getByText(/Generate/i));

    await waitFor(() => expect(screen.getByText(/Job:/i)).toBeInTheDocument());
  });
});
