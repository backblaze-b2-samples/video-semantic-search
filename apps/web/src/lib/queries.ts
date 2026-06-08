"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  deleteFile,
  deleteVideo,
  getFiles,
  getFileStats,
  getPreviewUrl,
  getUploadActivity,
  getVideos,
  ingestVideo,
  reindexVideo,
  searchVideos,
} from "@/lib/api-client";
import type { FileMetadata, Video } from "@video-semantic-search/shared";

// Single source of truth for query keys. Keep these tightly scoped so that
// invalidating "files" doesn't blow away unrelated caches, and so an IDE
// "find usages" of `qk.files` reveals every consumer.
export const qk = {
  all: ["b2"] as const,
  files: (prefix?: string, limit?: number) =>
    [...qk.all, "files", prefix ?? "", limit ?? 100] as const,
  stats: () => [...qk.all, "stats"] as const,
  uploadActivity: (days: number) =>
    [...qk.all, "stats", "activity", days] as const,
  preview: (key: string) => [...qk.all, "preview", key] as const,
  videos: () => [...qk.all, "videos"] as const,
  video: (id: string) => [...qk.all, "videos", id] as const,
};

export function useFiles(prefix = "", limit = 100) {
  return useQuery<FileMetadata[], ApiError>({
    queryKey: qk.files(prefix, limit),
    queryFn: () => getFiles(prefix, limit),
  });
}

export function useFileStats() {
  return useQuery({
    queryKey: qk.stats(),
    queryFn: getFileStats,
  });
}

export function useUploadActivity(days = 7) {
  return useQuery({
    queryKey: qk.uploadActivity(days),
    queryFn: () => getUploadActivity(days),
  });
}

// Presigned preview URL — only fetched when `enabled` is true (e.g., when
// the dialog opens for a specific file). Kept short-lived (60s) because
// the URL itself has a presigned expiry and is cheap to regenerate.
export function usePreviewUrl(key: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(key ?? ""),
    queryFn: () => getPreviewUrl(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileKey: string) => deleteFile(fileKey),
    // After delete, blow away every cached file list + stats. Cheap and
    // correct — the dashboard re-fetches lazily as components remount.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}

// --- Video pipeline ---

const PROCESSING: ReadonlySet<string> = new Set([
  "uploading",
  "extracting",
  "transcribing",
  "chunking",
  "embedding",
]);

export function useVideos() {
  return useQuery<Video[], ApiError>({
    queryKey: qk.videos(),
    queryFn: getVideos,
    // Poll while anything is mid-pipeline so the Library reflects progress.
    refetchInterval: (query) =>
      query.state.data?.some((v) => PROCESSING.has(v.status)) ? 4000 : false,
  });
}

export function useIngestVideo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { file: File; onProgress?: (percent: number) => void }) =>
      ingestVideo(vars.file, vars.onProgress),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.videos() }),
  });
}

export function useDeleteVideo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (videoId: string) => deleteVideo(videoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.all }),
  });
}

export function useReindexVideo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (videoId: string) => reindexVideo(videoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.videos() }),
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: (vars: {
      question: string;
      videoId?: string | null;
      topK?: number;
      synthesize?: boolean;
    }) =>
      searchVideos(vars.question, {
        videoId: vars.videoId ?? null,
        topK: vars.topK,
        synthesize: vars.synthesize,
      }),
  });
}
