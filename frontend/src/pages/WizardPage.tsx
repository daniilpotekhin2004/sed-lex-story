import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  createWizardSession,
  deleteWizardSession,
  getWizardSession,
  getLatestWizardSession,
  deployWizardSession,
  exportWizardSession,
  resetWizardProject,
  runWizardStep,
  saveWizardStep,
  setWizardStep7DeployOverride,
  updateWizardSession,
} from "../api/wizard";
import { getProject } from "../api/projects";
import type {
  WizardCriticIssue,
  WizardStep7DeployOverride,
  WizardMeta,
  WizardSession,
  WizardStepRunRequest,
  WizardStoryInput,
  WizardDeployResponse,
} from "../shared/types";

const WIZARD_STEPS = [
  { id: 1, title: "Каркас истории", note: "Ключевые персонажи, сцены, локации и правовые темы" },
  { id: 2, title: "Портреты мира", note: "Глубокие описания персонажей, ролей и мест действия" },
  { id: 3, title: "Сценарные слайды", note: "Кадры, реплики и визуальные ориентиры для постановки" },
  { id: 4, title: "План производства", note: "Список ассетов: что создать, обновить или переиспользовать" },
  { id: 5, title: "Вариативность", note: "Точки выбора, альтернативы и условия переходов" },
  { id: 6, title: "Карта связей", note: "Согласование сцен, кадров, ассетов и зависимостей" },
  { id: 7, title: "Критический аудит", note: "Проверка целостности сюжета и корректности сценария" },
];

const REQUIRED_STEPS: Record<number, number[]> = {
  2: [1],
  3: [1],
  4: [2],
  5: [1],
  6: [3],
  7: [1, 2, 3, 4, 5, 6],
};

const DETAIL_LEVELS: { value: WizardStepRunRequest["detail_level"]; label: string }[] = [
  { value: "narrow", label: "Кратко" },
  { value: "standard", label: "Сбалансировано" },
  { value: "detailed", label: "Подробно" },
];

const INPUT_TYPES: WizardStoryInput["input_type"][] = ["short_brief", "full_story", "structured"];

const statusLabels: Record<string, string> = {
  ok: "Готово",
  warning: "Внимание",
  error: "Ошибка",
  idle: "Нет данных",
};

const deployActionLabels: Record<string, string> = {
  reused: "использован",
  imported: "импортирован",
  created: "создан",
  skipped: "пропущен",
  missing: "ошибка",
};

const SESSION_KEY_PREFIX = "lwq_wizard_session";

function parseList(raw: string) {
  return raw
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinList(items?: string[] | null) {
  if (!items || items.length === 0) return "";
  return items.join(", ");
}

function toWizardMeta(raw: unknown): WizardMeta | null {
  if (!raw || typeof raw !== "object") return null;
  return raw as WizardMeta;
}

function toCriticIssues(raw: unknown): WizardCriticIssue[] {
  if (!raw || typeof raw !== "object") return [];
  const issues = (raw as { issues?: unknown }).issues;
  if (!Array.isArray(issues)) return [];
  return issues
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item, index) => ({
      id: String(item.id ?? `issue_${index + 1}`),
      severity: item.severity === "high" || item.severity === "medium" || item.severity === "low"
        ? item.severity
        : "medium",
      title: String(item.title ?? "Замечание"),
      description: String(item.description ?? ""),
      recommendation: String(item.recommendation ?? ""),
      affected_steps: Array.isArray(item.affected_steps)
        ? item.affected_steps.filter((step): step is number => typeof step === "number")
        : [],
      affected_ids: Array.isArray(item.affected_ids)
        ? item.affected_ids.filter((id): id is string => typeof id === "string")
        : [],
      evidence: typeof item.evidence === "string" ? item.evidence : null,
      blocking: Boolean(item.blocking),
      resolved: Boolean(item.resolved),
      resolution_note: typeof item.resolution_note === "string" ? item.resolution_note : null,
    }));
}

function toStep7Override(raw: unknown): WizardStep7DeployOverride {
  if (!raw || typeof raw !== "object") return { enabled: false };
  const value = raw as Record<string, unknown>;
  return {
    enabled: Boolean(value.enabled),
    reason: typeof value.reason === "string" ? value.reason : null,
    updated_at: typeof value.updated_at === "string" ? value.updated_at : null,
    updated_by: typeof value.updated_by === "string" ? value.updated_by : null,
    unresolved_blockers:
      typeof value.unresolved_blockers === "number" ? value.unresolved_blockers : undefined,
    blocker_titles: Array.isArray(value.blocker_titles)
      ? value.blocker_titles.filter((item): item is string => typeof item === "string")
      : undefined,
    critic_generated_at:
      typeof value.critic_generated_at === "string" ? value.critic_generated_at : null,
    project_description_file:
      typeof value.project_description_file === "string" ? value.project_description_file : null,
  };
}

function toRecordArray(raw: unknown): Record<string, unknown>[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"));
}

function toEntityLabelMap(drafts: Record<string, unknown>): Record<string, string> {
  const map: Record<string, string> = {};
  const step1 = ((drafts["1"] as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
  const step2 = ((drafts["2"] as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
  const step3 = ((drafts["3"] as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
  const step5 = ((drafts["5"] as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;

  toRecordArray(step1.characters).forEach((ch) => {
    const id = typeof ch.id === "string" ? ch.id.trim().toLowerCase() : "";
    const name = typeof ch.name === "string" ? ch.name.trim() : "";
    if (id) map[id] = name ? `персонаж «${name}»` : `персонаж ${id}`;
  });
  toRecordArray(step2.characters).forEach((ch) => {
    const id = typeof ch.id === "string" ? ch.id.trim().toLowerCase() : "";
    const name = typeof ch.name === "string" ? ch.name.trim() : "";
    if (id) map[id] = name ? `персонаж «${name}»` : `персонаж ${id}`;
  });
  toRecordArray(step1.locations).forEach((loc) => {
    const id = typeof loc.id === "string" ? loc.id.trim().toLowerCase() : "";
    const name = typeof loc.name === "string" ? loc.name.trim() : "";
    if (id) map[id] = name ? `локация «${name}»` : `локация ${id}`;
  });
  toRecordArray(step1.scenes).forEach((scene) => {
    const id = typeof scene.id === "string" ? scene.id.trim().toLowerCase() : "";
    const title = typeof scene.title === "string" ? scene.title.trim() : "";
    if (id) map[id] = title ? `сцена «${title}»` : `сцена ${id}`;
  });
  toRecordArray(step3.scenes).forEach((sceneGroup) => {
    const sceneId = typeof sceneGroup.scene_id === "string" ? sceneGroup.scene_id.trim().toLowerCase() : "";
    if (sceneId && !map[sceneId]) map[sceneId] = `сцена ${sceneId}`;
    toRecordArray(sceneGroup.slides).forEach((slide) => {
      const id = typeof slide.id === "string" ? slide.id.trim().toLowerCase() : "";
      const title = typeof slide.title === "string" ? slide.title.trim() : "";
      if (id) map[id] = title ? `слайд «${title}»` : `слайд ${id}`;
    });
  });
  toRecordArray(step5.branches).forEach((branch) => {
    const id = typeof branch.id === "string" ? branch.id.trim().toLowerCase() : "";
    const prompt = typeof branch.choice_prompt === "string" ? branch.choice_prompt.trim() : "";
    if (id) map[id] = prompt ? `ветка «${prompt}»` : `ветка ${id}`;
    toRecordArray(branch.options).forEach((option) => {
      const optionId = typeof option.id === "string" ? option.id.trim().toLowerCase() : "";
      const label = typeof option.label === "string" ? option.label.trim() : "";
      if (optionId) map[optionId] = label ? `вариант «${label}»` : `вариант ${optionId}`;
    });
  });
  return map;
}

function extractDomainIds(value: string): string[] {
  const matches = value.toLowerCase().match(/\b[cslb][a-z0-9_:-]*\b/g);
  return matches ?? [];
}

function explainCriticIssueForAuthor(
  issue: WizardCriticIssue,
  labels: Record<string, string>,
): string {
  const title = issue.title.toLowerCase();
  const ids: string[] = [];
  (issue.affected_ids || []).forEach((id) => {
    const token = id.trim().toLowerCase();
    if (token && !ids.includes(token)) ids.push(token);
  });
  [...extractDomainIds(issue.title), ...extractDomainIds(issue.description)].forEach((token) => {
    if (!ids.includes(token)) ids.push(token);
  });

  const charLabels = ids.filter((id) => id.startsWith("c")).map((id) => labels[id] || id);
  const sceneLabels = ids.filter((id) => id.startsWith("s")).map((id) => labels[id] || id);
  const branchLabels = ids.filter((id) => id.startsWith("b")).map((id) => labels[id] || id);
  const affectedLabels = ids.map((id) => labels[id]).filter((v): v is string => Boolean(v));

  if (title.includes("конфликт рол") && charLabels.length > 0) {
    return `${charLabels[0]} ведёт себя как разные роли в разных эпизодах. Уточните функцию персонажа в сюжете и мотивацию.`;
  }
  if (title.includes("дублирование") && title.includes("сцен")) {
    const target = sceneLabels.slice(0, 2).join(", ") || "сцены";
    return `В структуре истории повторяются ID (${target}). Переходы могут вести не в тот эпизод.`;
  }
  if (title.includes("дублирование") && title.includes("вет")) {
    const target = branchLabels.slice(0, 2).join(", ") || "ветки выбора";
    return `Ветвления пересекаются по идентификаторам (${target}). Игрок может увидеть некорректные варианты выбора.`;
  }
  if (affectedLabels.length > 0) {
    return `Проблема затрагивает: ${affectedLabels.slice(0, 3).join(", ")}. ${issue.recommendation}`;
  }
  return issue.description || issue.recommendation || issue.title;
}

export default function WizardPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const sessionStorageKey = projectId ? `${SESSION_KEY_PREFIX}_${projectId}` : SESSION_KEY_PREFIX;

  const [projectName, setProjectName] = useState<string | null>(null);
  const [session, setSession] = useState<WizardSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState(1);
  const [runningStep, setRunningStep] = useState<number | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [savingStep, setSavingStep] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [deployError, setDeployError] = useState<string | null>(null);
  const [deployReport, setDeployReport] = useState<WizardDeployResponse | null>(null);
  const [exporting, setExporting] = useState(false);
  const [resettingProject, setResettingProject] = useState(false);
  const [resetProjectError, setResetProjectError] = useState<string | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideBusy, setOverrideBusy] = useState(false);

  const [inputType, setInputType] = useState<WizardStoryInput["input_type"]>("short_brief");
  const [storyText, setStoryText] = useState("");
  const [maxScenes, setMaxScenes] = useState<string>("");
  const [branching, setBranching] = useState(true);
  const [language, setLanguage] = useState("ru");
  const [requiredTopics, setRequiredTopics] = useState("");
  const [optionalTopics, setOptionalTopics] = useState("");
  const [autoGenerateLegal, setAutoGenerateLegal] = useState(true);
  const [existingCharacters, setExistingCharacters] = useState("");
  const [existingLocations, setExistingLocations] = useState("");

  const [detailLevel, setDetailLevel] = useState<WizardStepRunRequest["detail_level"]>("standard");
  const [strictMode, setStrictMode] = useState(false);
  const [autoRunStep1, setAutoRunStep1] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    getProject(projectId)
      .then((project) => setProjectName(project.name))
      .catch(() => setProjectName(null));
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    const stored = localStorage.getItem(sessionStorageKey);
    if (!stored) {
      setLoading(true);
      getLatestWizardSession(projectId)
        .then((data) => {
          setSession(data);
          localStorage.setItem(sessionStorageKey, data.id);
          setActiveStep(data.current_step || 1);
        })
        .catch(() => {
          // no previous session
        })
        .finally(() => setLoading(false));
      return;
    }
    setLoading(true);
    getWizardSession(stored)
      .then((data) => {
        setSession(data);
        setActiveStep(data.current_step || 1);
      })
      .catch(() => {
        localStorage.removeItem(sessionStorageKey);
      })
      .finally(() => setLoading(false));
  }, [projectId, sessionStorageKey]);

  useEffect(() => {
    if (!session?.input_payload) return;
    const input = session.input_payload as WizardStoryInput;
    setInputType(input.input_type ?? "short_brief");
    setStoryText(input.story_text ?? "");
    setLanguage(input.preferences?.language ?? "ru");
    setMaxScenes(
      typeof input.preferences?.max_scenes === "number" ? String(input.preferences?.max_scenes) : "",
    );
    setBranching(input.preferences?.branching ?? true);
    setRequiredTopics(joinList(input.legal_topics?.required));
    setOptionalTopics(joinList(input.legal_topics?.optional));
    setAutoGenerateLegal(input.legal_topics?.auto_generate_if_empty ?? true);
    setExistingCharacters(joinList(input.existing_assets?.characters));
    setExistingLocations(joinList(input.existing_assets?.locations));
  }, [session?.id]);

  const stepKey = String(activeStep);
  const drafts = session?.drafts ?? {};
  const stepData = drafts ? (drafts as Record<string, unknown>)[stepKey] : null;
  const stepMeta = toWizardMeta(session?.meta?.[stepKey]);
  const criticStepData = (drafts as Record<string, unknown>)["7"];
  const criticIssues = useMemo(() => toCriticIssues(criticStepData), [criticStepData]);
  const entityLabelMap = useMemo(() => toEntityLabelMap(drafts as Record<string, unknown>), [drafts]);
  const step7Override = useMemo(
    () => toStep7Override((session?.meta as Record<string, unknown> | undefined)?.step7_deploy_override),
    [session?.meta],
  );
  const unresolvedBlockingCriticIssues = useMemo(
    () =>
      criticIssues.filter((issue) => !issue.resolved && (issue.severity === "high" || issue.blocking)),
    [criticIssues],
  );
  const step7GeneratedAt = useMemo(() => {
    const raw = (session?.meta as Record<string, unknown> | undefined)?.["7"];
    if (!raw || typeof raw !== "object") return null;
    const generated = (raw as Record<string, unknown>).generated_at;
    return typeof generated === "string" ? generated : null;
  }, [session?.meta]);
  const overrideMatchesCurrentCritic =
    !step7GeneratedAt ||
    (step7Override.critic_generated_at ? step7Override.critic_generated_at === step7GeneratedAt : false);
  const step7OverrideActive = Boolean(step7Override.enabled && overrideMatchesCurrentCritic);
  const deployBlockedByCritic = unresolvedBlockingCriticIssues.length > 0 && !step7OverrideActive;
  const unresolvedBlockingIssueExplanations = useMemo(
    () =>
      unresolvedBlockingCriticIssues.map((issue) => ({
        issue,
        explanation: explainCriticIssueForAuthor(issue, entityLabelMap),
      })),
    [entityLabelMap, unresolvedBlockingCriticIssues],
  );

  useEffect(() => {
    setOverrideReason(step7Override.reason || "");
  }, [step7Override.reason, session?.id]);
  const allCoreStepsReady = useMemo(
    () => [1, 2, 3, 4, 5, 6].every((id) => Boolean((drafts as Record<string, unknown>)[String(id)])),
    [drafts],
  );
  const criticStepReady = Boolean((drafts as Record<string, unknown>)["7"]);
  const readyForDeploy = allCoreStepsReady && criticStepReady;
  const missingDeploySteps = useMemo(
    () =>
      [1, 2, 3, 4, 5, 6, 7].filter(
        (id) => !Boolean((drafts as Record<string, unknown>)[String(id)]),
      ),
    [drafts],
  );

  useEffect(() => {
    setEditMode(false);
    setEditError(null);
    if (stepData) {
      try {
        setEditText(JSON.stringify(stepData, null, 2));
      } catch {
        setEditText("");
      }
    } else {
      setEditText("");
    }
  }, [activeStep, stepData]);

  const stepStatus = useMemo(() => {
    if (stepMeta?.status) return stepMeta.status;
    if (stepData) return "ok";
    return "idle";
  }, [stepData, stepMeta?.status]);

  const missingDependencies = useMemo(() => {
    const required = REQUIRED_STEPS[activeStep] ?? [];
    if (!required.length) return [];
    return required.filter((id) => !(drafts as Record<string, unknown>)[String(id)]);
  }, [activeStep, drafts]);

  function buildStoryInput(): WizardStoryInput {
    const legalRequired = parseList(requiredTopics);
    const legalOptional = parseList(optionalTopics);
    const existingChars = parseList(existingCharacters);
    const existingLocs = parseList(existingLocations);
    const parsedMaxScenes = maxScenes ? Number(maxScenes) : undefined;
    const normalizedMaxScenes =
      typeof parsedMaxScenes === "number" && parsedMaxScenes > 0 ? parsedMaxScenes : undefined;

    const input: WizardStoryInput = {
      input_type: inputType,
      story_text: storyText.trim(),
      preferences: {
        language: (language || "ru").trim() || "ru",
        branching,
        max_scenes: normalizedMaxScenes,
      },
    };

    if (legalRequired.length || legalOptional.length || !autoGenerateLegal) {
      input.legal_topics = {
        required: legalRequired,
        optional: legalOptional,
        auto_generate_if_empty: autoGenerateLegal,
      };
    }

    if (existingChars.length || existingLocs.length) {
      input.existing_assets = {
        characters: existingChars,
        locations: existingLocs,
      };
    }

    return input;
  }

  async function handleCreateSession() {
    if (!projectId) return;
    setError(null);
    const payload = buildStoryInput();
    if (!payload.story_text || payload.story_text.length < 20) {
      setError("Сюжет слишком короткий. Добавьте хотя бы пару предложений.");
      return;
    }
    setLoading(true);
    try {
      const created = await createWizardSession({
        project_id: projectId,
        story_input: payload,
        auto_run_step1: autoRunStep1,
      });
      setSession(created);
      localStorage.setItem(sessionStorageKey, created.id);
      setActiveStep(1);
      if (autoRunStep1) {
        await handleRunStep(1, created.id);
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось создать сессию мастера.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveInput() {
    if (!session) return;
    setError(null);
    const payload = buildStoryInput();
    if (!payload.story_text || payload.story_text.length < 20) {
      setError("Сюжет слишком короткий. Добавьте хотя бы пару предложений.");
      return;
    }
    setLoading(true);
    try {
      const updated = await updateWizardSession(session.id, { story_input: payload });
      setSession(updated);
    } catch (err: any) {
      setError(err?.message || "Не удалось сохранить ввод.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResetSession() {
    if (session) {
      try {
        await deleteWizardSession(session.id);
      } catch {
        // ignore
      }
    }
    localStorage.removeItem(sessionStorageKey);
    setSession(null);
    setActiveStep(1);
    setDeployReport(null);
  }

  async function handleResetProject() {
    if (!session || !projectId) return;
    if (
      !window.confirm(
        "Удалить текущий проект и пересоздать его из этой сессии? Все данные проекта будут удалены.",
      )
    ) {
      return;
    }
    setResetProjectError(null);
    setResettingProject(true);
    setDeployError(null);
    setError(null);
    try {
      const project = await resetWizardProject(session.id);
      localStorage.removeItem(sessionStorageKey);
      const nextKey = `${SESSION_KEY_PREFIX}_${project.id}`;
      localStorage.setItem(nextKey, session.id);
      setDeployReport(null);
      setSession((prev) => (prev ? { ...prev, project_id: project.id } : prev));
      navigate(`/projects/${project.id}/wizard`, { replace: true });
    } catch (err: any) {
      setResetProjectError(err?.message || "Не удалось пересоздать проект.");
    } finally {
      setResettingProject(false);
    }
  }

  async function handleRunStep(stepId: number, sessionOverride?: string, force?: boolean) {
    const currentSession = sessionOverride ?? session?.id;
    if (!currentSession) return;
    if (!storyText.trim()) {
      setError("Перед запуском шага заполните ввод сюжета.");
      return;
    }
    const required = REQUIRED_STEPS[stepId] ?? [];
    const missing = required.filter((id) => !(drafts as Record<string, unknown>)[String(id)]);
    if (missing.length) {
      setError(`Для шага ${stepId} нужно выполнить шаги: ${missing.join(", ")}`);
      return;
    }
    setError(null);
    setRunningStep(stepId);
    try {
      const result = await runWizardStep(currentSession, stepId, {
        language: (language || "ru").trim() || "ru",
        detail_level: detailLevel || "standard",
        strict: strictMode,
        force,
      });
      setSession((prev) => {
        if (!prev) return prev;
        const stepKey = String(stepId);
        const nextDrafts = { ...(prev.drafts ?? {}), [stepKey]: result.data };
        const nextMeta = result.meta
          ? { ...(prev.meta ?? {}), [stepKey]: result.meta }
          : prev.meta ?? null;
        return {
          ...prev,
          drafts: nextDrafts,
          meta: nextMeta,
          current_step: Math.max(prev.current_step || 1, stepId),
        };
      });
      const refreshed = await getWizardSession(currentSession);
      setSession(refreshed);
      setActiveStep(stepId);
    } catch (err: any) {
      setError(err?.message || "Ошибка запуска шага.");
    } finally {
      setRunningStep(null);
    }
  }

  async function handleSaveStepEdits() {
    if (!session) return;
    setEditError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(editText || "");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("JSON должен быть объектом.");
      }
    } catch (err: any) {
      setEditError(err?.message || "Некорректный JSON.");
      return;
    }
    setSavingStep(true);
    const now = new Date().toISOString();
    const baseMeta: WizardMeta = stepMeta ?? {
      step: activeStep,
      mode: "draft",
      status: "warning",
      warnings: [],
      errors: [],
      generated_at: now,
    };
    const warnings = [...(baseMeta.warnings ?? [])];
    if (!warnings.find((item) => item.code === "manual_edit")) {
      warnings.push({
        code: "manual_edit",
        message: "Результат шага изменён вручную.",
        severity: "low",
      });
    }
    const nextMeta: WizardMeta = {
      ...baseMeta,
      step: activeStep,
      mode: baseMeta.mode ?? "draft",
      status: baseMeta.errors && baseMeta.errors.length > 0 ? "error" : "warning",
      warnings,
      generated_at: now,
    };

    try {
      await saveWizardStep(session.id, activeStep, {
        data: parsed,
        meta: nextMeta,
      });
      const refreshed = await getWizardSession(session.id);
      setSession(refreshed);
      setEditMode(false);
    } catch (err: any) {
      setEditError(err?.message || "Не удалось сохранить правки.");
    } finally {
      setSavingStep(false);
    }
  }

  const renderMeta = () => {
    if (!stepMeta) return null;
    const warnings = stepMeta.warnings ?? [];
    const errors = stepMeta.errors ?? [];
    const hasCriticBlockersError = errors.some((item) => item.code === "critic_blockers");
    return (
      <div className="stack">
        {errors.length > 0 && (
          <div className="wizard-alert error">
            <strong>Ошибки:</strong>
            {errors.map((item, idx) => (
              <div key={`error-${idx}`}>
                {item.code}: {item.message}
              </div>
            ))}
          </div>
        )}
        {hasCriticBlockersError && unresolvedBlockingIssueExplanations.length > 0 && (
          <div className="wizard-alert warn">
            <strong>Расшифровка для автора:</strong>
            {unresolvedBlockingIssueExplanations.slice(0, 4).map(({ issue, explanation }) => (
              <div key={`author-issue-${issue.id}`}>
                {issue.title}: {explanation}
              </div>
            ))}
          </div>
        )}
        {warnings.length > 0 && (
          <div className="wizard-alert warn">
            <strong>Предупреждения:</strong>
            {warnings.map((item, idx) => (
              <div key={`warn-${idx}`}>
                {item.code}: {item.message}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  async function handleStep7OverrideToggle(enabled: boolean) {
    if (!session) return;
    if (!criticStepReady) {
      setDeployError("Сначала выполните шаг 7, затем можно управлять ручной блокировкой.");
      return;
    }
    setOverrideBusy(true);
    setDeployError(null);
    try {
      await setWizardStep7DeployOverride(session.id, {
        enabled,
        reason: overrideReason.trim() || null,
      });
      const refreshed = await getWizardSession(session.id);
      setSession(refreshed);
    } catch (err: any) {
      setDeployError(err?.message || "Не удалось изменить статус ручной блокировки.");
    } finally {
      setOverrideBusy(false);
    }
  }

  async function handleDeploy() {
    if (!session || !projectId) return;
    setDeployError(null);
    setDeployReport(null);
    setDeploying(true);
    try {
      const result: WizardDeployResponse = await deployWizardSession(session.id);
      setDeployReport(result);
      if (result.warnings && result.warnings.length > 0) {
        setDeployError(`Развернуто с предупреждениями: ${result.warnings.map((w) => w.message).join("; ")}`);
      }
    } catch (err: any) {
      setDeployError(err?.message || "Не удалось развернуть проект.");
    } finally {
      setDeploying(false);
    }
  }

  async function handleExport() {
    if (!session) return;
    setExporting(true);
    try {
      const pkg = await exportWizardSession(session.id);
      const content = JSON.stringify(pkg, null, 2);
      const blob = new Blob([content], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `wizard_${session.id}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setDeployError(err?.message || "Не удалось экспортировать пакет.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="page wizard-shell">
      <div className="topbar">
        <div>
          <div className="muted">Проект</div>
          <h1>Мастер сюжета {projectName ? `— ${projectName}` : ""}</h1>
          <div className="muted">Создайте сессию и прогоните шаги по очереди.</div>
        </div>
        <div className="actions" style={{ gap: "10px", display: "flex" }}>
          <button className="secondary" onClick={() => navigate(`/projects/${projectId}`)}>
            Назад к проекту
          </button>
          {session && (
            <button className="danger" onClick={handleResetProject} disabled={resettingProject}>
              {resettingProject ? "Пересоздание..." : "Пересоздать проект"}
            </button>
          )}
          <button className="ghost" onClick={handleResetSession}>
            Новая сессия
          </button>
        </div>
      </div>

      {error && <div className="card error">{error}</div>}
      {resetProjectError && <div className="card error">{resetProjectError}</div>}
      {deployReport && (
        <div className="card">
          <div className="card-header">
            <h2>Отчет развертывания</h2>
            <div className="actions" style={{ gap: "10px", display: "flex" }}>
              <button
                className="secondary"
                onClick={() => navigate(`/projects/${projectId}/graphs/${deployReport.graph_id}`)}
              >
                Открыть граф
              </button>
            </div>
          </div>
          <div className="muted" style={{ marginBottom: "12px" }}>
            Граф: {deployReport.graph_title}
          </div>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "16px" }}>
            <span className="pill">Сцены: {deployReport.scenes_created}</span>
            <span className="pill">Связи: {deployReport.edges_created}</span>
            <span className="pill">Персонажи (создано): {deployReport.characters_created}</span>
            {typeof deployReport.characters_imported === "number" && (
              <span className="pill">Импортировано: {deployReport.characters_imported}</span>
            )}
            {typeof deployReport.characters_reused === "number" && (
              <span className="pill">Переисп.: {deployReport.characters_reused}</span>
            )}
            <span className="pill">Локации (создано): {deployReport.locations_created}</span>
            {typeof deployReport.locations_imported === "number" && (
              <span className="pill">Импортировано: {deployReport.locations_imported}</span>
            )}
            {typeof deployReport.locations_reused === "number" && (
              <span className="pill">Переисп.: {deployReport.locations_reused}</span>
            )}
          </div>

          <div style={{ display: "grid", gap: "14px" }}>
            <div>
              <strong>Персонажи</strong>
              <div style={{ marginTop: "8px", display: "grid", gap: "6px" }}>
                {(deployReport.report?.characters ?? []).length === 0 && (
                  <div className="muted">Нет данных.</div>
                )}
                {(deployReport.report?.characters ?? []).map((item) => (
                  <div key={`deploy-ch-${item.id}`} className="muted">
                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{item.name}</span>{" "}
                    — {deployActionLabels[item.action] ?? item.action}
                    {item.note ? ` (${item.note})` : ""}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <strong>Локации</strong>
              <div style={{ marginTop: "8px", display: "grid", gap: "6px" }}>
                {(deployReport.report?.locations ?? []).length === 0 && (
                  <div className="muted">Нет данных.</div>
                )}
                {(deployReport.report?.locations ?? []).map((item) => (
                  <div key={`deploy-loc-${item.id}`} className="muted">
                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{item.name}</span>{" "}
                    — {deployActionLabels[item.action] ?? item.action}
                    {item.note ? ` (${item.note})` : ""}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="wizard-layout">
        <div className="stack">
          <div className="card">
            <div className="card-header">
              <h2>Ввод сюжета</h2>
              {session && <span className="pill">Сессия активна</span>}
            </div>

            <label className="field">
              <span>Тип входа</span>
              <select
                className="input"
                value={inputType}
                onChange={(event) => setInputType(event.target.value as WizardStoryInput["input_type"])}
              >
                {INPUT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Сюжет</span>
              <textarea
                className="input"
                rows={6}
                placeholder="Опишите сюжет или задачу для мастера..."
                value={storyText}
                onChange={(event) => setStoryText(event.target.value)}
              />
            </label>

            <div className="field two-cols">
              <label className="field" style={{ marginBottom: 0, flex: 1 }}>
                <span>Максимум сцен</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={50}
                  placeholder="Авто"
                  value={maxScenes}
                  onChange={(event) => setMaxScenes(event.target.value)}
                />
              </label>
              <label className="field wizard-checkbox" style={{ marginBottom: 0 }}>
                <span>Ветвления</span>
                <input
                  type="checkbox"
                  checked={branching}
                  onChange={(event) => setBranching(event.target.checked)}
                />
              </label>
            </div>

            <details className="cvs-advanced" open>
              <summary>Дополнительно</summary>
              <div className="cvs-advanced-body">
                <label className="field">
                  <span>Язык ответов</span>
                  <input
                    className="input"
                    value={language}
                    onChange={(event) => setLanguage(event.target.value)}
                  />
                </label>

                <label className="field">
                  <span>Правовые темы (обязательные)</span>
                  <textarea
                    className="input"
                    rows={2}
                    placeholder="Напр.: право собственности, защита потребителя"
                    value={requiredTopics}
                    onChange={(event) => setRequiredTopics(event.target.value)}
                  />
                </label>

                <label className="field">
                  <span>Правовые темы (опциональные)</span>
                  <textarea
                    className="input"
                    rows={2}
                    placeholder="Дополнительные темы через запятую или с новой строки"
                    value={optionalTopics}
                    onChange={(event) => setOptionalTopics(event.target.value)}
                  />
                </label>

                <label className="field wizard-checkbox">
                  <span>Автогенерация правовых тем</span>
                  <input
                    type="checkbox"
                    checked={autoGenerateLegal}
                    onChange={(event) => setAutoGenerateLegal(event.target.checked)}
                  />
                </label>

                <label className="field">
                  <span>Персонажи из библиотеки (имена)</span>
                  <textarea
                    className="input"
                    rows={2}
                    placeholder="Напр.: Антон, Мария"
                    value={existingCharacters}
                    onChange={(event) => setExistingCharacters(event.target.value)}
                  />
                </label>

                <label className="field">
                  <span>Локации из библиотеки (имена)</span>
                  <textarea
                    className="input"
                    rows={2}
                    placeholder="Напр.: Суд, Школа"
                    value={existingLocations}
                    onChange={(event) => setExistingLocations(event.target.value)}
                  />
                </label>

                <label className="field wizard-checkbox">
                  <span>Авто запуск шага 1</span>
                  <input
                    type="checkbox"
                    checked={autoRunStep1}
                    onChange={(event) => setAutoRunStep1(event.target.checked)}
                  />
                </label>
              </div>
            </details>

            <div className="actions" style={{ gap: "10px" }}>
              {session ? (
                <button className="primary" onClick={handleSaveInput} disabled={loading}>
                  {loading ? "Сохранение..." : "Сохранить ввод"}
                </button>
              ) : (
                <button className="primary" onClick={handleCreateSession} disabled={loading}>
                  {loading ? "Создание..." : "Создать сессию"}
                </button>
              )}
            </div>
          </div>

            <div className="card">
            <div className="card-header">
              <h2>Шаги</h2>
              <span className="pill">{session?.current_step ?? 1}/7</span>
            </div>
            <div className="wizard-step-list">
              {WIZARD_STEPS.map((step) => {
                const key = String(step.id);
                const meta = toWizardMeta(session?.meta?.[key]);
                const hasDraft = Boolean((drafts as Record<string, unknown>)[key]);
                const status = meta?.status ?? (hasDraft ? "ok" : "idle");
                const warningsCount = meta?.warnings?.length ?? 0;
                return (
                  <button
                    key={step.id}
                    className={`wizard-step ${activeStep === step.id ? "active" : ""}`}
                    onClick={() => setActiveStep(step.id)}
                  >
                    <strong>
                      Шаг {step.id}. {step.title}
                    </strong>
                    <div className="wizard-step-meta">
                      <span className={`wizard-badge ${status}`}>{statusLabels[status] || status}</span>
                      {warningsCount > 0 && (
                        <span className="wizard-badge warning">Предупр.: {warningsCount}</span>
                      )}
                    </div>
                    <div className="muted" style={{ marginTop: "6px", fontSize: "12px" }}>
                      {step.note}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-header">
              <h2>Результат шага {activeStep}</h2>
              <span className={`wizard-badge ${stepStatus}`}>{statusLabels[stepStatus]}</span>
            </div>

            <div className="field two-cols" style={{ alignItems: "flex-end" }}>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Детализация</span>
                <select
                  className="input"
                  value={detailLevel}
                  onChange={(event) =>
                    setDetailLevel(event.target.value as WizardStepRunRequest["detail_level"])
                  }
                >
                  {DETAIL_LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {level.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field wizard-checkbox" style={{ marginBottom: 0 }}>
                <span>Строгий режим</span>
                <input
                  type="checkbox"
                  checked={strictMode}
                  onChange={(event) => setStrictMode(event.target.checked)}
                />
              </label>
            </div>

            {missingDependencies.length > 0 && (
              <div className="wizard-alert warn" style={{ marginBottom: "12px" }}>
                Для этого шага нужны: {missingDependencies.join(", ")}
              </div>
            )}
            {session && allCoreStepsReady && missingDeploySteps.length > 0 && (
              <div className="wizard-alert warn" style={{ marginBottom: "12px" }}>
                Для развёртывания выполните шаги: {missingDeploySteps.join(", ")}
              </div>
            )}

            <div className="actions" style={{ gap: "10px", marginBottom: "12px" }}>
              <button
                className="primary"
                onClick={() => handleRunStep(activeStep)}
                disabled={runningStep === activeStep || loading || missingDependencies.length > 0 || !session}
              >
                {runningStep === activeStep ? "Выполняется..." : "Запустить шаг"}
              </button>
              {stepData && (
                <button
                  className="secondary"
                  onClick={() => handleRunStep(activeStep, undefined, true)}
                  disabled={runningStep === activeStep || loading || missingDependencies.length > 0 || !session}
                >
                  Пересчитать шаг
                </button>
              )}
              {allCoreStepsReady && session && (
                <button
                  className="secondary"
                  onClick={handleExport}
                  disabled={exporting}
                >
                  {exporting ? "Экспорт..." : "Экспорт JSON"}
                </button>
              )}
              {readyForDeploy && session && (
                <button
                  className="primary"
                  onClick={handleDeploy}
                  disabled={deploying || deployBlockedByCritic}
                >
                  {deploying ? "Разворачиваем..." : "Развернуть в проект"}
                </button>
              )}
              {!session && (
                <button className="secondary" onClick={handleCreateSession}>
                  Сначала создать сессию
                </button>
              )}
            </div>

            {readyForDeploy && unresolvedBlockingIssueExplanations.length > 0 && (
              <div className={`wizard-alert ${deployBlockedByCritic ? "error" : "warn"}`} style={{ marginBottom: "12px" }}>
                {deployBlockedByCritic ? (
                  <strong>
                    Шаг 7 содержит существенные нерешённые замечания ({unresolvedBlockingIssueExplanations.length}).
                    Развёртывание заблокировано до исправления, повторной критики или ручного снятия блокировки.
                  </strong>
                ) : (
                  <strong>
                    Блокировка шага 7 снята вручную. Развёртывание разрешено, но риски целостности сюжета остаются.
                  </strong>
                )}
                {unresolvedBlockingIssueExplanations.slice(0, 4).map(({ issue, explanation }) => (
                  <div key={`blocker-${issue.id}`} style={{ marginTop: "6px" }}>
                    {issue.title}
                    <div className="muted" style={{ marginTop: "2px" }}>
                      {explanation}
                    </div>
                  </div>
                ))}
                {!overrideMatchesCurrentCritic && step7Override.enabled && (
                  <div style={{ marginTop: "8px" }}>
                    Предыдущее ручное снятие блокировки устарело после нового прогона шага 7.
                  </div>
                )}
                <div style={{ marginTop: "10px" }}>
                  <label className="field" style={{ marginBottom: "8px" }}>
                    <span>Обоснование ручного снятия блокировки (фиксируется в файле описания проекта)</span>
                    <textarea
                      className="input"
                      rows={3}
                      value={overrideReason}
                      onChange={(event) => setOverrideReason(event.target.value)}
                      placeholder="Почему команда принимает риски и кто берёт ответственность."
                    />
                  </label>
                  <div className="actions" style={{ gap: "10px" }}>
                    <button
                      className="secondary"
                      disabled={overrideBusy || !criticStepReady || step7OverrideActive}
                      onClick={() => handleStep7OverrideToggle(true)}
                    >
                      {overrideBusy ? "Сохраняем..." : "Снять блокировку вручную"}
                    </button>
                    <button
                      className="ghost"
                      disabled={overrideBusy || !step7Override.enabled}
                      onClick={() => handleStep7OverrideToggle(false)}
                    >
                      Отменить ручное снятие
                    </button>
                  </div>
                  {step7Override.project_description_file && (
                    <div className="muted" style={{ marginTop: "6px" }}>
                      Фиксация: {step7Override.project_description_file}
                    </div>
                  )}
                </div>
              </div>
            )}

            {deployError && <div className="wizard-alert warn">{deployError}</div>}

            {renderMeta()}

            <div style={{ marginTop: "12px" }}>
              {stepData ? (
                <>
                  <div className="actions" style={{ gap: "10px", marginBottom: "8px" }}>
                    {!editMode ? (
                      <button className="secondary" onClick={() => setEditMode(true)}>
                        Редактировать JSON
                      </button>
                    ) : (
                      <>
                        <button
                          className="primary"
                          onClick={handleSaveStepEdits}
                          disabled={savingStep}
                        >
                          {savingStep ? "Сохранение..." : "Сохранить правки"}
                        </button>
                        <button
                          className="secondary"
                          onClick={() => {
                            setEditMode(false);
                            setEditError(null);
                            setEditText(JSON.stringify(stepData, null, 2));
                          }}
                        >
                          Отмена
                        </button>
                      </>
                    )}
                  </div>

                  {editError && <div className="wizard-alert error">{editError}</div>}

                  {editMode ? (
                    <textarea
                      className="wizard-json wizard-json-edit"
                      rows={18}
                      value={editText}
                      onChange={(event) => setEditText(event.target.value)}
                    />
                  ) : (
                    <pre className="wizard-json">{JSON.stringify(stepData, null, 2)}</pre>
                  )}
                </>
              ) : (
                <div className="muted">Данных для этого шага пока нет.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
