import { useState } from "react";
import { PageHeader } from "@/components/common/PageHeader";
import { Dropzone } from "./Dropzone";
import { UploadProgress } from "./UploadProgress";
import { UploadSummary } from "./UploadSummary";
import { useUpload } from "@/hooks/useUpload";
import { Info } from "lucide-react";

export default function UploadPage() {
  const { mutate, isPending, isSuccess, data, progress, reset } = useUpload();
  const [fileName, setFileName] = useState<string | undefined>();

  function handleFile(file: File) {
    setFileName(file.name);
    mutate(file);
  }

  function handleReset() {
    reset();
    setFileName(undefined);
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <PageHeader
        title="Upload Knowledge"
        description="Import a WhatsApp chat export to build a searchable collection."
      />

      {/* Instructions */}
      <div className="flex items-start gap-3 rounded-xl border border-border bg-surface p-4 text-sm">
        <Info className="h-4 w-4 text-accent shrink-0 mt-0.5" aria-hidden="true" />
        <div className="space-y-1 text-muted-foreground">
          <p>
            Export a WhatsApp chat via{" "}
            <strong className="text-foreground">More → Export Chat → Without Media</strong>.
            The downloaded <code className="text-accent font-mono text-xs">.zip</code> file
            can be uploaded directly here.
          </p>
          <p>Max size: 200 MB. Only ZIP archives are accepted.</p>
        </div>
      </div>

      {/* Main upload area */}
      {!isSuccess && (
        <>
          <Dropzone onFile={handleFile} disabled={isPending} />
          <UploadProgress
            progress={progress}
            fileName={fileName}
            isPending={isPending}
          />
        </>
      )}

      {/* Success summary */}
      {isSuccess && data && (
        <UploadSummary result={data} onReset={handleReset} />
      )}
    </div>
  );
}
