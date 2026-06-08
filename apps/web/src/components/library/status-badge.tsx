import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { VideoStatus } from "@video-semantic-search/shared";

const PROCESSING = new Set<VideoStatus>([
  "uploading",
  "extracting",
  "transcribing",
  "chunking",
  "embedding",
]);

const LABELS: Record<VideoStatus, string> = {
  uploading: "Uploading",
  uploaded: "Uploaded",
  extracting: "Extracting audio",
  transcribing: "Transcribing",
  chunking: "Chunking",
  embedding: "Embedding",
  ready: "Ready",
  failed: "Failed",
};

function variantFor(status: VideoStatus): "default" | "secondary" | "destructive" {
  if (status === "ready") return "default";
  if (status === "failed") return "destructive";
  return "secondary";
}

export function StatusBadge({ status }: { status: VideoStatus }) {
  return (
    <Badge variant={variantFor(status)}>
      {PROCESSING.has(status) && <Loader2 className="animate-spin" />}
      {LABELS[status]}
    </Badge>
  );
}
