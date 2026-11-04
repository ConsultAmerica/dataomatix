"use client";

import { useEffect, useState } from "react";
import { Plus, Settings2, Trash2 } from "lucide-react";

import ContentSection from "@/components/layout/ContentSection";
import ConsoleHeader from "@/components/layout/ConsoleHeader";
import EmptyState from "@/components/ui/empty-state";
import { LoadingState } from "@/components/layout/StatusState";
import {
  DOCUMENT_FAMILY_LABELS,
  documentFamilyLabel,
} from "@/lib/document-families";
import {
  addExtractionField,
  createExtractionModel,
  deleteExtractionField,
  deleteExtractionModel,
  listExtractionModels,
} from "@/lib/extraction-models";
import type {
  ExtractionFieldDataType,
  ExtractionModel,
} from "@/types/document";

const TAGGABLE_DOCUMENT_TYPES = Object.keys(DOCUMENT_FAMILY_LABELS).filter(
  (key) => key !== "*",
);

const DATA_TYPES: ExtractionFieldDataType[] = [
  "text",
  "number",
  "currency",
  "date",
  "boolean",
  "list",
];

export default function ExtractionModelsPage() {
  const [models, setModels] = useState<ExtractionModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [newModelName, setNewModelName] = useState("");
  const [newModelDescription, setNewModelDescription] =
    useState("");
  const [newModelDocumentTypes, setNewModelDocumentTypes] = useState<
    string[]
  >([]);
  const [creatingModel, setCreatingModel] = useState(false);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError("");

      try {
        const result = await listExtractionModels();
        if (active) setModels(result);
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load extraction models.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();

    return () => {
      active = false;
    };
  }, []);

  async function handleCreateModel() {
    if (!newModelName.trim()) return;

    setCreatingModel(true);

    try {
      const model = await createExtractionModel(
        newModelName.trim(),
        newModelDescription.trim(),
        newModelDocumentTypes.length > 0 ? newModelDocumentTypes : ["*"],
      );
      setModels((current) => [model, ...current]);
      setNewModelName("");
      setNewModelDescription("");
      setNewModelDocumentTypes([]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to create the extraction model.",
      );
    } finally {
      setCreatingModel(false);
    }
  }

  async function handleDeleteModel(modelId: number) {
    try {
      await deleteExtractionModel(modelId);
      setModels((current) =>
        current.filter((model) => model.id !== modelId),
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to delete the extraction model.",
      );
    }
  }

  function handleModelUpdated(updated: ExtractionModel) {
    setModels((current) =>
      current.map((model) =>
        model.id === updated.id ? updated : model,
      ),
    );
  }

  return (
    <div className="workspace-page w-full">
      <ConsoleHeader
        icon={Settings2}
        title="Extraction models"
        description="Define reusable field templates for document extraction runs."
      />

      <ContentSection>
      <div className="data-panel p-5">
        <p className="text-sm font-semibold text-foreground">New model</p>

        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_2fr_auto]">
          <input
            type="text"
            placeholder="Model name (e.g. Supplier Agreement)"
            value={newModelName}
            onChange={(event) =>
              setNewModelName(event.target.value)
            }
            className="control"
          />
          <input
            type="text"
            placeholder="Description (optional)"
            value={newModelDescription}
            onChange={(event) =>
              setNewModelDescription(event.target.value)
            }
            className="control"
          />
          <button
            type="button"
            onClick={handleCreateModel}
            disabled={creatingModel || !newModelName.trim()}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Plus className="h-4 w-4" />
            Create
          </button>
        </div>

        <div className="mt-3">
          <p className="text-xs text-text-secondary">
            Document types (leave blank to show for every document type)
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {TAGGABLE_DOCUMENT_TYPES.map((key) => {
              const active = newModelDocumentTypes.includes(key);
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() =>
                    setNewModelDocumentTypes((current) =>
                      active
                        ? current.filter((value) => value !== key)
                        : [...current, key],
                    )
                  }
                  className={[
                    "rounded-full px-2.5 py-1 text-xs font-medium transition",
                    active
                      ? "bg-primary text-white"
                      : "bg-surface-soft text-text-secondary hover:bg-border",
                  ].join(" ")}
                >
                  {documentFamilyLabel(key)}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-danger/20 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </div>
      )}

      <div className="mt-6 space-y-4">
        {loading && (
          <LoadingState
            title="Loading extraction models..."
            description="Retrieving custom enterprise extraction schemas and field rules."
          />
        )}

        {!loading && models.length === 0 && (
          <EmptyState
            icon={Settings2}
            title="No extraction models configured"
            description="Define custom target field groups and schemas to tailor extraction to your organization's contracts."
          />
        )}

        {models.map((model) => (
          <ModelCard
            key={model.id}
            model={model}
            onDeleteModel={() => handleDeleteModel(model.id)}
            onModelUpdated={handleModelUpdated}
          />
        ))}
      </div>
      </ContentSection>
    </div>
  );
}

function ModelCard({
  model,
  onDeleteModel,
  onModelUpdated,
}: {
  model: ExtractionModel;
  onDeleteModel: () => void;
  onModelUpdated: (model: ExtractionModel) => void;
}) {
  const [fieldName, setFieldName] = useState("");
  const [fieldDescription, setFieldDescription] = useState("");
  const [dataType, setDataType] =
    useState<ExtractionFieldDataType>("text");
  const [addingField, setAddingField] = useState(false);
  const [fieldError, setFieldError] = useState("");

  async function handleAddField() {
    if (!fieldName.trim()) return;

    setAddingField(true);
    setFieldError("");

    try {
      const updated = await addExtractionField(
        model.id,
        fieldName.trim(),
        fieldDescription.trim(),
        dataType,
      );
      onModelUpdated(updated);
      setFieldName("");
      setFieldDescription("");
      setDataType("text");
    } catch (err) {
      setFieldError(
        err instanceof Error
          ? err.message
          : "Unable to add the field.",
      );
    } finally {
      setAddingField(false);
    }
  }

  async function handleDeleteField(fieldId: number) {
    try {
      const updated = await deleteExtractionField(
        model.id,
        fieldId,
      );
      onModelUpdated(updated);
    } catch (err) {
      setFieldError(
        err instanceof Error
          ? err.message
          : "Unable to delete the field.",
      );
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">
            {model.name}
          </p>
          {model.description && (
            <p className="mt-0.5 text-xs text-text-secondary">
              {model.description}
            </p>
          )}
          <div className="mt-1.5 flex flex-wrap gap-1">
            {(model.document_types.length > 0
              ? model.document_types
              : ["*"]
            ).map((key) => (
              <span
                key={key}
                className="rounded-full bg-surface-soft px-2 py-0.5 text-[10px] font-medium text-text-secondary"
              >
                {documentFamilyLabel(key)}
              </span>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={onDeleteModel}
          className="rounded-lg p-2 text-text-muted transition hover:bg-red-50 hover:text-red-600"
          aria-label={`Delete ${model.name}`}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {model.fields.length > 0 && (
        <div className="mt-4 space-y-2">
          {model.fields.map((field) => (
            <div
              key={field.id}
              className="flex items-center justify-between gap-2 rounded-xl bg-surface-soft p-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">
                  {field.field_name}
                  <span className="ml-2 rounded-full bg-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
                    {field.data_type}
                  </span>
                </p>
                {field.description && (
                  <p className="mt-0.5 truncate text-xs text-text-secondary">
                    {field.description}
                  </p>
                )}
              </div>

              <button
                type="button"
                onClick={() => handleDeleteField(field.id)}
                className="shrink-0 rounded-lg p-1.5 text-text-muted transition hover:bg-red-50 hover:text-red-600"
                aria-label={`Delete ${field.field_name}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 rounded-xl border border-dashed border-border p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          + Add Field
        </p>

        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <input
            type="text"
            placeholder="Field Name (e.g. Cyber Insurance Limit)"
            value={fieldName}
            onChange={(event) =>
              setFieldName(event.target.value)
            }
            className="rounded-lg border border-border px-2.5 py-1.5 text-sm"
          />

          <select
            value={dataType}
            onChange={(event) =>
              setDataType(
                event.target.value as ExtractionFieldDataType,
              )
            }
            className="rounded-lg border border-border px-2.5 py-1.5 text-sm capitalize"
          >
            {DATA_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <textarea
          placeholder="Description: what should be extracted for this field?"
          value={fieldDescription}
          onChange={(event) =>
            setFieldDescription(event.target.value)
          }
          rows={2}
          className="mt-2 w-full rounded-lg border border-border px-2.5 py-1.5 text-sm"
        />

        <button
          type="button"
          onClick={handleAddField}
          disabled={addingField || !fieldName.trim()}
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Field
        </button>

        {fieldError && (
          <p className="mt-2 text-xs text-danger">
            {fieldError}
          </p>
        )}
      </div>
    </div>
  );
}
