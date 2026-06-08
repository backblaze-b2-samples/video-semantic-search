"use client";

import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { Film, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { useIngestVideo } from "@/lib/queries";

export function IngestDialog() {
  const [open, setOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const ingest = useIngestVideo();

  const onDrop = useCallback(
    (accepted: File[]) => {
      const file = accepted[0];
      if (!file) return;
      setProgress(0);
      ingest.mutate(
        { file, onProgress: setProgress },
        {
          onSuccess: (video) => {
            toast.success(`"${video.title}" uploaded — transcription started.`);
            setOpen(false);
            setProgress(0);
          },
          onError: (err) => {
            toast.error(err instanceof Error ? err.message : "Upload failed");
          },
        },
      );
    },
    [ingest],
  );

  const onDropRejected = useCallback((rejections: FileRejection[]) => {
    const rejection = rejections[0];
    if (rejection) {
      toast.error(
        `${rejection.file.name}: ${rejection.errors.map((e) => e.message).join(", ")}`,
      );
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    accept: { "video/*": [] },
    multiple: false,
    disabled: ingest.isPending,
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!ingest.isPending) setOpen(next);
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" className="h-8">
          <Upload className="h-3.5 w-3.5" />
          Add video
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a video</DialogTitle>
          <DialogDescription>
            Uploaded straight to Backblaze B2 in parts (presigned multipart), so
            multi-GB files are fine. Transcription and indexing start
            automatically once the upload completes.
          </DialogDescription>
        </DialogHeader>
        {ingest.isPending ? (
          <div className="space-y-2 py-4">
            <p className="text-sm text-muted-foreground">
              Uploading to B2… {progress}%
            </p>
            <Progress value={progress} />
          </div>
        ) : (
          <div
            {...getRootProps()}
            className={`flex flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed p-10 text-center cursor-pointer transition-colors ${
              isDragActive
                ? "border-primary bg-[var(--accent-subtle)]"
                : "border-border hover:border-primary/60 hover:bg-muted/60"
            }`}
          >
            <input {...getInputProps()} />
            <div className="flex items-center justify-center w-12 h-12 rounded-md bg-muted border border-border">
              <Film className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="text-base font-semibold">
              Drop a video here, or click to browse
            </p>
            <p className="text-xs text-muted-foreground font-mono">
              MP4, MOV, MKV, WebM…
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
