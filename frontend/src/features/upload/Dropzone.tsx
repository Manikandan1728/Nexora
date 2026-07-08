import { useCallback, useRef, useState } from "react";
import { Upload, FileArchive, X, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/format";
import { MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
}

const ACCEPTED = ".zip,application/zip,application/x-zip-compressed";

export function Dropzone({ onFile, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  function validateAndSubmit(file: File) {
    setValidationError(null);

    if (!file.name.endsWith(".zip") && file.type !== "application/zip") {
      setValidationError("Only .zip files are accepted.");
      return;
    }
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setValidationError(
        `File is too large (${formatBytes(file.size)}). Maximum is ${formatBytes(MAX_UPLOAD_SIZE_BYTES)}.`
      );
      return;
    }
    onFile(file);
  }

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) validateAndSubmit(file);
    },
    [disabled] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) validateAndSubmit(file);
    // Reset input so the same file can be re-selected after an error
    e.target.value = "";
  }

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Drop zone — click or drag a ZIP file here"
        aria-disabled={disabled}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled)
            inputRef.current?.click();
        }}
        className={cn(
          "relative flex flex-col items-center justify-center gap-4 rounded-xl",
          "border-2 border-dashed p-12 text-center transition-all duration-200 cursor-pointer",
          isDragging
            ? "border-accent bg-accent/5 scale-[1.01]"
            : "border-border hover:border-accent/50 hover:bg-surface-hover",
          disabled && "pointer-events-none opacity-50 cursor-not-allowed"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          onChange={handleInputChange}
          disabled={disabled}
          aria-hidden="true"
        />

        <div
          className={cn(
            "flex h-16 w-16 items-center justify-center rounded-2xl transition-colors",
            isDragging ? "bg-accent/20 text-accent" : "bg-surface text-muted-foreground"
          )}
        >
          {isDragging ? (
            <FileArchive className="h-8 w-8" aria-hidden="true" />
          ) : (
            <Upload className="h-8 w-8" aria-hidden="true" />
          )}
        </div>

        <div className="space-y-1.5">
          <p className="text-sm font-semibold text-foreground">
            {isDragging ? "Drop to upload" : "Drop your ZIP file here"}
          </p>
          <p className="text-xs text-muted-foreground">
            or{" "}
            <span className="text-accent underline underline-offset-2">
              click to browse
            </span>
          </p>
          <p className="text-xs text-muted-foreground">
            WhatsApp export ZIP · max {formatBytes(MAX_UPLOAD_SIZE_BYTES)}
          </p>
        </div>
      </div>

      {validationError && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-xs text-danger"
        >
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>{validationError}</span>
          <button
            type="button"
            className="ml-auto shrink-0"
            onClick={() => setValidationError(null)}
            aria-label="Dismiss error"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
