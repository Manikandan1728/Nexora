import { useForm } from "react-hook-form";
import { Search, ChevronDown } from "lucide-react";
import type { QueryRequest } from "@/types/query";
import type { CollectionInfo } from "@/types/collections";
import { cn } from "@/lib/utils";
import type { QueryFormValues } from "@/schemas/query.schema";

interface Props {
  collections: CollectionInfo[];
  defaultCollection?: string;
  onSubmit: (req: QueryRequest) => void;
  isPending: boolean;
}

export function SearchForm({
  collections,
  defaultCollection,
  onSubmit,
  isPending,
}: Props) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<QueryFormValues>({
    defaultValues: {
      question: "",
      collection_name: defaultCollection ?? collections[0]?.name ?? "",
      top_k: 5,
      use_rag: true,
    },
  });

  const useRag = watch("use_rag");

  function onValid(values: QueryFormValues) {
    onSubmit({
      question: values.question,
      collection_name: values.collection_name,
      top_k: values.top_k,
      use_rag: values.use_rag,
    });
  }

  return (
    <form onSubmit={handleSubmit(onValid)} className="space-y-4" noValidate>
      {/* Collection select */}
      <div className="space-y-1.5">
        <label
          htmlFor="collection_name"
          className="text-xs font-medium text-muted-foreground"
        >
          Collection
        </label>
        <div className="relative">
          <select
            id="collection_name"
            {...register("collection_name", { required: "Select a collection" })}
            disabled={collections.length === 0}
            className={cn(
              "w-full appearance-none rounded-lg border border-border bg-surface",
              "px-3 py-2.5 pr-10 text-sm text-foreground",
              "focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent",
              "transition-colors hover:border-accent/50",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {collections.length === 0 ? (
              <option value="">No collections yet — upload one first</option>
            ) : (
              collections.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.document_count.toLocaleString()} chunks)
                </option>
              ))
            )}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground"
            aria-hidden="true"
          />
        </div>
        {errors.collection_name && (
          <p className="text-xs text-danger">{errors.collection_name.message}</p>
        )}
      </div>

      {/* Question textarea */}
      <div className="space-y-1.5">
        <label
          htmlFor="question"
          className="text-xs font-medium text-muted-foreground"
        >
          Question
        </label>
        <textarea
          id="question"
          {...register("question", {
            required: "Question is required",
            minLength: { value: 3, message: "Question is too short" },
            maxLength: { value: 2000, message: "Question is too long (max 2000 chars)" },
          })}
          rows={3}
          placeholder="What did we discuss about the project deadline?"
          className={cn(
            "w-full resize-none rounded-lg border border-border bg-surface",
            "px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground",
            "focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent",
            "transition-colors hover:border-accent/50",
            errors.question && "border-danger focus:ring-danger"
          )}
          aria-describedby={errors.question ? "question-error" : undefined}
        />
        {errors.question && (
          <p id="question-error" className="text-xs text-danger">
            {errors.question.message}
          </p>
        )}
      </div>

      {/* Options row */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Top-K */}
        <div className="flex items-center gap-2">
          <label
            htmlFor="top_k"
            className="text-xs text-muted-foreground whitespace-nowrap"
          >
            Top results
          </label>
          <input
            id="top_k"
            type="number"
            min={1}
            max={20}
            {...register("top_k", { valueAsNumber: true, min: 1, max: 20 })}
            className={cn(
              "w-16 rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-foreground",
              "focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent text-center"
            )}
          />
        </div>

        {/* Use RAG toggle */}
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <div className="relative h-5 w-9">
            <input
              type="checkbox"
              {...register("use_rag")}
              id="use_rag"
              className="sr-only peer"
            />
            <div
              className={cn(
                "h-5 w-9 rounded-full border transition-colors",
                useRag ? "bg-accent border-accent" : "bg-surface border-border"
              )}
              aria-hidden="true"
            />
            <div
              className={cn(
                "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform",
                useRag ? "translate-x-4" : "translate-x-0.5"
              )}
              aria-hidden="true"
            />
          </div>
          <span className="text-xs text-muted-foreground">
            AI answer {useRag ? "(on)" : "(off)"}
          </span>
        </label>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={isPending || collections.length === 0}
        className={cn(
          "flex w-full items-center justify-center gap-2 rounded-lg",
          "bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground",
          "hover:opacity-90 active:scale-[0.98] transition-all",
          "disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100"
        )}
      >
        {isPending ? (
          <>
            <span className="h-4 w-4 rounded-full border-2 border-accent-foreground/30 border-t-accent-foreground animate-spin" aria-hidden="true" />
            Searching…
          </>
        ) : (
          <>
            <Search className="h-4 w-4" aria-hidden="true" />
            Search
          </>
        )}
      </button>
    </form>
  );
}
