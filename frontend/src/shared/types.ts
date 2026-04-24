export type GenerationParams = {
  prompt: string;
  negative_prompt?: string | null;
  style?: string;
  cfg_scale?: number;
  steps?: number;
  num_variants?: number;
  width?: number;
  height?: number;
  character_preset?: string | null;
  lora_preset?: string | null;
};

export type GenerationResponse = {
  task_id: string;
  status?: string;
};

export type TaskStatus = {
  task_id: string;
  state: string;
  ready: boolean;
  success?: boolean | null;
  image_urls?: string[] | null;
  result?: {
    scene_id?: string;
    paths?: string[];
    image_url?: string;
    image_urls?: string[];
  } | null;
  error?: string | null;
};

export type TaskSummary = {
  taskId: string;
  prompt: string;
  createdAt: number;
  lastState?: string;
  success?: boolean | null;
  error?: string | null;
  outputs?: string[];
};

export type TaskListItem = {
  task_id: string;
  status: "queued" | "running" | "done" | "failed";
  image_url: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  prompt: string;
};

export type TaskListResponse = {
  items: TaskListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type ReferenceImage = {
  id?: string;
  kind: string;
  url: string;
  thumb_url?: string;
  label?: string;
  meta?: Record<string, unknown>;
};

export type User = {
  id: string;
  username: string;
  roles?: string[];
  role?: string;
  email?: string;
  is_active?: boolean;
  full_name?: string | null;
  cohort_code?: string | null;
  created_at?: string;
};

export type AdminUserSummary = {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  cohort_code?: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  assets_total: number;
  quests_total: number;
  completed_jobs_total: number;
  comfy_units_total: number;
};

export type AdminUserListResponse = {
  items: AdminUserSummary[];
  total: number;
  page: number;
  page_size: number;
  grouped_counts: Record<string, number>;
};

export type RoleUpdateRequest = {
  role: "admin" | "author" | "player";
  reason?: string;
  confirm_assign_admin?: boolean;
};

export type RoleUpdateResult = {
  user_id: string;
  previous_role: string;
  new_role: string;
  changed: boolean;
};

export type CohortUpdateRequest = {
  cohort_code?: string | null;
};

export type CohortUpdateResult = {
  user_id: string;
  previous_cohort_code?: string | null;
  cohort_code?: string | null;
  changed: boolean;
};

export type RoleBulkUpdateRequest = {
  user_ids: string[];
  role: "admin" | "author" | "player";
  reason?: string;
  confirm_assign_admin?: boolean;
};

export type RoleBulkUpdateResponse = {
  updated: number;
  skipped: number;
  batch_id?: string | null;
  results: RoleUpdateResult[];
};

export type WeeklyMetric = {
  week: string;
  value: number;
};

export type AssetListItem = {
  id: string;
  type: string;
  name: string;
  project_id?: string | null;
  created_at: string;
};

export type QuestListItem = {
  id: string;
  title: string;
  project_id: string;
  project_name?: string | null;
  created_at: string;
};

export type UserAssetStats = {
  total: number;
  by_type: Record<string, number>;
  weekly: WeeklyMetric[];
  items: AssetListItem[];
};

export type UserTimeStats = {
  total_seconds: number;
  total_hours: number;
  completed_jobs_total: number;
  weekly_seconds: WeeklyMetric[];
};

export type UserQuestStats = {
  total: number;
  weekly: WeeklyMetric[];
  items: QuestListItem[];
};

export type UserComfyStats = {
  units_total: number;
  units_period: number;
  cost_per_unit_usd?: number | null;
  estimated_spend_total_usd?: number | null;
  estimated_spend_period_usd?: number | null;
  configured_balance_usd?: number | null;
  estimated_remaining_balance_usd?: number | null;
  is_estimated: boolean;
};

export type UserStatsResponse = {
  user: AdminUserSummary;
  assets: UserAssetStats;
  time: UserTimeStats;
  quests: UserQuestStats;
  comfy?: UserComfyStats | null;
};

export type RoleAggregateStats = {
  users: number;
  assets_total: number;
  quests_total: number;
  time_seconds_total: number;
  comfy_units_total: number;
  estimated_spend_usd_total?: number | null;
};

export type AdminOverviewResponse = {
  users_total: number;
  users_by_role: Record<string, number>;
  aggregates_by_role: Record<string, RoleAggregateStats>;
  generated_at: string;
};

export type ComfySpendByUser = {
  user_id: string;
  username: string;
  units: number;
  estimated_spend_usd?: number | null;
};

export type ComfyOverviewResponse = {
  total_units: number;
  cost_per_unit_usd?: number | null;
  estimated_spend_total_usd?: number | null;
  configured_balance_usd?: number | null;
  estimated_remaining_balance_usd?: number | null;
  users: ComfySpendByUser[];
  is_estimated: boolean;
};

export type RoleAuditRead = {
  id: string;
  user_id: string;
  actor_user_id: string;
  from_role: string;
  to_role: string;
  reason?: string | null;
  batch_id?: string | null;
  created_at: string;
  user_username?: string | null;
  actor_username?: string | null;
};

export type RoleAuditListResponse = {
  items: RoleAuditRead[];
  total: number;
  page: number;
  page_size: number;
};

export type ErrorFeedItem = {
  source: string;
  level: string;
  message: string;
  timestamp?: string | null;
};

export type ErrorFeedResponse = {
  items: ErrorFeedItem[];
};

export type PresetList = {
  characters: { id: string; name: string; description?: string }[];
  loras: { id: string; name: string; description?: string }[];
};

export type PresetOption = {
  id: string;
  name: string;
  description?: string;
  preview_thumbnail_url?: string | null;
};

export type CharacterPreset = {
  id: string;
  name: string;
  description?: string | null;
  character_type: string;
  appearance_prompt: string;
  negative_prompt?: string | null;
  anchor_token?: string | null;
  appearance_profile?: Record<string, unknown> | null;
  reference_images?: ReferenceImage[] | null;
  preview_image_url?: string | null;
  preview_thumbnail_url?: string | null;
  lora_models?: { name: string; weight: number }[] | null;
  embeddings?: string[] | null;
  style_tags?: string[] | null;
  default_pose?: string | null;
  voice_profile?: string | null;
  motivation?: string | null;
  legal_status?: string | null;
  competencies?: string[] | null;
  relationships?: Record<string, unknown>[] | null;
  artifact_refs?: string[] | null;
  project_id?: string | null;
  source_preset_id?: string | null;
  source_version?: number | null;
  version?: number;
  is_public: boolean;
  author_id?: string;
  usage_count?: number;
  created_at?: string;
  updated_at?: string;
};

// Stage 4/5 domain types
export type StyleProfile = {
  id: string;
  project_id: string;
  name: string;
  description?: string | null;
  base_prompt?: string | null;
  negative_prompt?: string | null;
  model_checkpoint?: string | null;
  lora_refs?: Record<string, unknown>[] | null;
  aspect_ratio?: string | null;
  resolution?: { width?: number; height?: number } | null;
  sampler?: string | null;
  steps?: number | null;
  cfg_scale?: number | null;
  seed_policy?: string | null;
  palette?: string[] | null;
  forbidden?: string[] | null;
  style_metadata?: Record<string, unknown> | null;
};

export type StyleBible = {
  id: string;
  project_id: string;
  tone?: string | null;
  glossary?: Record<string, unknown> | null;
  constraints?: unknown[] | null;
  dialogue_format?: Record<string, unknown> | null;
  document_format?: Record<string, unknown> | null;
  ui_theme?: Record<string, unknown> | null;
  narrative_rules?: string | null;
};

export type Location = {
  id: string;
  project_id?: string | null;
  owner_id?: string | null;
  is_public?: boolean;
  version?: number;
  source_location_id?: string | null;
  source_version?: number | null;
  name: string;
  description?: string | null;
  visual_reference?: string | null;
  anchor_token?: string | null;
  negative_prompt?: string | null;
  reference_images?: ReferenceImage[] | null;
  preview_image_url?: string | null;
  preview_thumbnail_url?: string | null;
  atmosphere_rules?: Record<string, unknown> | null;
  tags?: unknown[] | null;
  location_metadata?: Record<string, unknown> | null;
};

export type Artifact = {
  id: string;
  project_id?: string | null;
  owner_id?: string | null;
  is_public?: boolean;
  version?: number;
  source_artifact_id?: string | null;
  source_version?: number | null;
  name: string;
  description?: string | null;
  artifact_type?: string | null;
  legal_significance?: string | null;
  status?: string | null;
  preview_image_url?: string | null;
  preview_thumbnail_url?: string | null;
  artifact_metadata?: Record<string, unknown> | null;
  tags?: unknown[] | null;
};

export type DocumentTemplate = {
  id: string;
  project_id?: string | null;
  owner_id?: string | null;
  is_public?: boolean;
  version?: number;
  source_template_id?: string | null;
  source_version?: number | null;
  name: string;
  template_type?: string | null;
  template_body?: string | null;
  placeholders?: Record<string, unknown> | null;
  formatting?: Record<string, unknown> | null;
  tags?: unknown[] | null;
};

export type Project = {
  id: string;
  name: string;
  description?: string;
  style_profile?: StyleProfile | null;
  graphs?: ScenarioGraph[];
};

export type ReleaseAssignedUser = {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
};

export type ProjectRelease = {
  id: string;
  project_id: string;
  graph_id: string;
  version: number;
  status: string;
  package_version: string;
  notes?: string | null;
  published_at: string;
  archived_at?: string | null;
  manifest: {
    project_id: string;
    project_name: string;
    project_description?: string | null;
    graph_id: string;
    graph_title: string;
    graph_description?: string | null;
    root_scene_id?: string | null;
    scene_count: number;
    choice_count: number;
    package_version: string;
    updated_at: string;
  };
  assigned_users: ReleaseAssignedUser[];
  assigned_cohorts: string[];
};

export type ScenarioGraph = {
  id: string;
  project_id: string;
  title: string;
  description?: string;
  root_scene_id?: string | null;
  scenes: SceneNode[];
  edges: Edge[];
};

export type SceneDialogueLine = {
  id?: string;
  speaker?: string;
  character_id?: string;
  text: string;
};

export type SlideVariant = {
  id: string;
  url: string;
  thumbnail_url?: string | null;
};

export type SceneSlide = {
  id: string;
  title?: string;
  image_url?: string;
  image_variant_id?: string;
  variants?: SlideVariant[];
  user_prompt?: string;
  composition_prompt?: string; // Qwen-generated composition prompt for img2img
  cast_ids?: string[];
  framing?: "full" | "half" | "portrait";
  pipeline?: {
    mode?: "standard" | "controlnet";
    pose_image_url?: string;
    identity_mode?: "reference" | "ip_adapter";
    location_ref_mode?: "auto" | "none" | "selected";
    location_ref_url?: string;
    character_slot_ids?: string[];
  };
  exposition?: string;
  thought?: string;
  dialogue?: SceneDialogueLine[];
  animation?: string;
};

export type SceneSequence = {
  slides: SceneSlide[];
  choice_key?: string;
  choice_prompt?: string;
};

export type ProjectVoiceoverVariant = {
  id: string;
  audio_url: string;
  content_type?: string | null;
  language?: string | null;
  voice_profile?: string | null;
  created_at?: string | null;
};

export type ProjectVoiceoverKind = "scene_narration" | "exposition" | "thought" | "dialogue";

export type ProjectVoiceoverLine = {
  id: string;
  scene_id: string;
  scene_title: string;
  scene_order: number;
  slide_index?: number | null;
  slide_title?: string | null;
  kind: ProjectVoiceoverKind;
  speaker?: string | null;
  character_id?: string | null;
  dialogue_id?: string | null;
  dialogue_index?: number | null;
  voice_profile?: string | null;
  text: string;
  order: number;
  variants: ProjectVoiceoverVariant[];
  approved_variant_id?: string | null;
  approved_audio_url?: string | null;
};

export type ProjectVoiceoverSummary = {
  total_lines: number;
  generated_lines: number;
  approved_lines: number;
  total_variants: number;
};

export type ProjectVoiceoverRolePrompts = {
  narrator?: string | null;
  inner_voice?: string | null;
  interlocutor?: string | null;
};

export type ProjectVoiceoverSettings = {
  language?: string | null;
  voice_profile?: string | null;
  role_prompts?: ProjectVoiceoverRolePrompts | null;
  character_prompts?: Record<string, string> | null;
  speaker_prompts?: Record<string, string> | null;
};

export type ProjectVoiceoverRead = {
  project_id: string;
  graph_id: string;
  lines: ProjectVoiceoverLine[];
  summary: ProjectVoiceoverSummary;
  settings?: ProjectVoiceoverSettings;
  suggested_role_prompts?: ProjectVoiceoverRolePrompts;
  updated_at?: string | null;
};

export type SceneVoiceoverData = {
  lines?: ProjectVoiceoverLine[];
  updated_at?: string;
  settings?: ProjectVoiceoverSettings;
};

export type SceneContext = {
  shot?: string;
  sequence?: SceneSequence;
  voiceover?: SceneVoiceoverData;
  [key: string]: unknown;
};

export type SceneNode = {
  id: string;
  graph_id: string;
  location_id?: string | null;
  location_material_set_id?: string | null;
  title: string;
  content: string;
  synopsis?: string | null;
  scene_type: "story" | "decision";
  order_index?: number | null;
  context?: SceneContext | null;
  location_overrides?: Record<string, unknown> | null;
  location?: Location | null;
  artifacts?: SceneArtifact[];
  legal_concepts?: LegalConcept[];
};

export type Edge = {
  id: string;
  graph_id: string;
  from_scene_id: string;
  to_scene_id: string;
  condition?: string | null;
  choice_label?: string | null;
  edge_metadata?: Record<string, unknown> | null;
};

export type GraphValidationIssue = {
  code: string;
  severity: string;
  message: string;
  scene_id?: string | null;
  edge_id?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type GraphValidationReport = {
  graph_id: string;
  issues: GraphValidationIssue[];
  summary: Record<string, unknown>;
};

export type SceneUsageItem = {
  scene_id: string;
  title: string;
  scene_type: string;
  reason: string;
};

export type SceneUsageResponse = {
  items: SceneUsageItem[];
};

export type ServiceStatus = {
  id: string;
  name: string;
  status: string;
  url?: string | null;
  host?: string | null;
  port?: number | null;
  details?: Record<string, unknown> | null;
  actions: string[];
  controllable: boolean;
  last_checked_at: string;
};

export type OpsStatusResponse = {
  services: ServiceStatus[];
  compose_available: boolean;
  project_root?: string | null;
};

export type ServiceControlResult = {
  success: boolean;
  command: string;
  output?: string | null;
  service?: ServiceStatus | null;
  error?: string | null;
};

export type LegalConcept = {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  difficulty?: number | null;
  tags?: string[] | null;
};

export type PromptBundle = {
  prompt: string;
  negative_prompt?: string | null;
  config: Record<string, unknown>;
};

export type SDPromptResponse = {
  prompt: string;
  negative_prompt: string;
  lora_models: Record<string, unknown>[];
  embeddings: string[];
  characters: string[];
};

export type SceneNodeCharacter = {
  id: string;
  scene_id: string;
  character_preset_id: string;
  scene_context?: string | null;
  position?: string | null;
  importance: number;
  seed_override?: string | null;
  in_frame?: boolean;
  material_set_id?: string | null;
};

export type SceneArtifact = {
  id: string;
  scene_id: string;
  artifact_id: string;
  state?: string | null;
  notes?: string | null;
  importance: number;
  artifact?: Artifact | null;
};

export type ImageVariant = {
  id: string;
  job_id: string;
  project_id: string;
  scene_id: string;
  url: string;
  thumbnail_url?: string | null;
  image_metadata?: Record<string, unknown> | null;
  is_approved: boolean;
  created_at: string;
  updated_at: string;
};

export type MaterialSet = {
  id: string;
  project_id: string;
  asset_type: "character" | "location";
  asset_id: string;
  label: string;
  reference_images?: ReferenceImage[] | null;
  material_metadata?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
};

// ----------------------------
// Character library (filesystem)
// ----------------------------

export type LibraryCharacter = {
  id: string;
  name: string;
  description?: string | null;
  appearance_prompt: string;
  negative_prompt?: string | null;
  style_tags?: string[] | null;
  is_public?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type CharacterLibList = {
  items: LibraryCharacter[];
  total: number;
  page: number;
  page_size: number;
};

// ----------------------------
// Unified generation jobs
// ----------------------------

export type GenerationTaskTypeString =
  | "scene_generate"
  | "character_sheet"
  | "character_sketch"
  | "character_reference"
  | "character_render"
  | "location_sheet"
  | "location_sketch"
  | "artifact_sketch";

export const GenerationTaskType = {
  SCENE_GENERATE: "scene_generate",
  CHARACTER_SHEET: "character_sheet",
  CHARACTER_SKETCH: "character_sketch",
  CHARACTER_REFERENCE: "character_reference",
  CHARACTER_RENDER: "character_render",
  LOCATION_SHEET: "location_sheet",
  LOCATION_SKETCH: "location_sketch",
  ARTIFACT_SKETCH: "artifact_sketch",
} as const;

export type GenerationJobStartRequest = {
  task_type: GenerationTaskTypeString;
  entity_type: string;
  entity_id: string;
  project_id?: string | null;
  style_profile_id?: string | null;
  kind?: string | null;
  overrides?: GenerationOverrides | null;
  payload?: Record<string, unknown> | null;
  num_variants?: number;
};

export type GenerationJob = {
  id: string;
  task_id?: string | null;
  user_id?: string | null;

  // Scene jobs
  project_id?: string | null;
  scene_id?: string | null;
  style_profile_id?: string | null;

  // Unified routing (assets + scenes)
  task_type?: string;
  entity_type?: string;
  entity_id?: string;
  status: string;
  stage?: string | null;
  progress?: number | null;

  prompt?: string | null;
  negative_prompt?: string | null;
  config?: Record<string, unknown> | null;
  results?: Record<string, unknown> | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  variants?: ImageVariant[];
};

export type SceneExport = {
  scene: SceneNode;
  characters: SceneNodeCharacter[];
  approved_image?: ImageVariant | null;
  artifacts?: SceneArtifact[];
  location?: Location | null;
};

export type ProjectExport = {
  project: Project;
  graph: {
    id: string;
    scenes: SceneNode[];
    edges: Edge[];
    root_scene_id?: string | null;
  };
  legal_concepts: LegalConcept[];
  scenes: SceneExport[];
  style_profile?: StyleProfile | null;
  style_bible?: StyleBible | null;
  locations?: Location[];
  artifacts?: Artifact[];
  document_templates?: DocumentTemplate[];
};

// --- Advanced generation / user presets ---

export type LoraRef = {
  name: string;
  weight: number;
};

export type GenerationOverrides = {
  negative_prompt?: string | null;
  width?: number | null;
  height?: number | null;
  steps?: number | null;
  cfg_scale?: number | null;
  seed?: number | null;

  sampler?: string | null;
  scheduler?: string | null;
  model_id?: string | null;
  vae_id?: string | null;
  loras?: LoraRef[] | null;

  pipeline_profile_id?: string | null;
  pipeline_profile_version?: number | null;
};

export type UserGenerationPreset = {
  id: string;
  user_id: string;
  name: string;
  description?: string | null;
  negative_prompt?: string | null;
  cfg_scale: number;
  steps: number;
  width: number;
  height: number;
  style?: string | null;
  sampler?: string | null;
  scheduler?: string | null;
  model_id?: string | null;
  vae_id?: string | null;
  seed?: number | null;
  pipeline_profile_id?: string | null;
  pipeline_profile_version?: number | null;
  lora_models?: LoraRef[] | null;
  is_favorite: boolean;
  usage_count: number;
  created_at: string;
  updated_at: string;
};

export type UserPresetListResponse = {
  items: UserGenerationPreset[];
  total: number;
};

export type UserPresetCreate = {
  name: string;
  description?: string | null;
  negative_prompt?: string | null;
  cfg_scale?: number;
  steps?: number;
  width?: number;
  height?: number;
  style?: string | null;
  sampler?: string | null;
  scheduler?: string | null;
  model_id?: string | null;
  vae_id?: string | null;
  seed?: number | null;
  pipeline_profile_id?: string | null;
  pipeline_profile_version?: number | null;
  lora_models?: LoraRef[] | null;
  is_favorite?: boolean;
};

export type UserPresetUpdate = Partial<UserPresetCreate>;

// ----------------------------
// Wizard (story master)
// ----------------------------

export type WizardMode = "draft" | "final";
export type WizardMetaStatus = "ok" | "warning" | "error";
export type WizardIssue = {
  code: string;
  message: string;
  field?: string;
  severity?: "low" | "medium" | "high";
  hint?: string;
};

export type WizardMeta = {
  step: number;
  mode: WizardMode;
  status: WizardMetaStatus;
  warnings?: WizardIssue[];
  errors?: WizardIssue[];
  usage?: Record<string, unknown> | null;
  trace_id?: string | null;
  generated_at?: string | null;
};

export type WizardStoryInput = {
  input_type: "short_brief" | "full_story" | "structured";
  story_text: string;
  project_context?: {
    genre?: string | null;
    tone?: string | null;
    style_refs?: string[];
    constraints?: string[];
    target_audience?: string | null;
  } | null;
  legal_topics?: {
    required?: string[];
    optional?: string[];
    auto_generate_if_empty?: boolean;
  } | null;
  existing_assets?: {
    characters?: string[];
    locations?: string[];
  } | null;
  preferences?: {
    language?: string;
    max_scenes?: number | null;
    branching?: boolean;
  } | null;
};

export type WizardSession = {
  id: string;
  project_id?: string | null;
  owner_id?: string | null;
  status: string;
  current_step: number;
  input_payload?: WizardStoryInput | Record<string, unknown> | null;
  drafts?: Record<string, unknown> | null;
  approvals?: Record<string, unknown> | null;
  meta?: Record<string, WizardMeta | Record<string, unknown>> | null;
  last_error?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type WizardStepResponse = {
  data: Record<string, unknown>;
  meta?: WizardMeta | null;
  approval?: Record<string, unknown> | null;
};

export type WizardStepRunRequest = {
  language?: string;
  detail_level?: "narrow" | "standard" | "detailed";
  strict?: boolean;
  force?: boolean;
};

export type WizardStep7DeployOverride = {
  enabled: boolean;
  reason?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
  unresolved_blockers?: number;
  blocker_titles?: string[];
  critic_generated_at?: string | null;
  project_description_file?: string | null;
};

export type WizardCriticCheck = {
  id: string;
  title: string;
  status: "pass" | "warn" | "fail";
  note: string;
};

export type WizardCriticIssue = {
  id: string;
  severity: "low" | "medium" | "high";
  title: string;
  description: string;
  recommendation: string;
  affected_steps?: number[];
  affected_ids?: string[];
  evidence?: string | null;
  blocking?: boolean;
  resolved?: boolean;
  resolution_note?: string | null;
};

export type WizardStep7Data = {
  overall_summary: string;
  verdict: "pass" | "revise";
  continuity_score: number;
  checks?: WizardCriticCheck[];
  issues?: WizardCriticIssue[];
};

export type WizardDeployResponse = {
  graph_id: string;
  graph_title: string;
  scenes_created: number;
  edges_created: number;
  characters_created: number;
  characters_imported?: number;
  characters_reused?: number;
  locations_created: number;
  locations_imported?: number;
  locations_reused?: number;
  warnings?: WizardIssue[];
  report?: WizardDeployReport;
};

export type WizardDeployReportItem = {
  id: string;
  name: string;
  action: "reused" | "imported" | "created" | "skipped" | "missing";
  asset_id?: string | null;
  source?: "project" | "library" | "wizard" | "unknown" | null;
  note?: string | null;
};

export type WizardDeployReport = {
  characters: WizardDeployReportItem[];
  locations: WizardDeployReportItem[];
};

export type WizardExportPackage = {
  session_id: string;
  project_id?: string | null;
  generated_at?: string | null;
  story_input?: WizardStoryInput | null;
  steps: Record<string, unknown>;
  meta?: Record<string, unknown> | null;
  approvals?: Record<string, unknown> | null;
  summary?: Record<string, unknown> | null;
};
