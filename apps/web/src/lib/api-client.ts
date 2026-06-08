import type {
  CompletedPart,
  DailyUploadCount,
  FileMetadata,
  FileUploadResponse,
  MultipartUpload,
  SearchResponse,
  UploadStats,
  Video,
} from "@video-semantic-search/shared";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Typed API error with HTTP status code for caller-side branching. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True for 408, 429, 500, 502, 503, 504 — worth retrying. */
  get isRetryable(): boolean {
    return [408, 429, 500, 502, 503, 504].includes(this.status);
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    // Network failure (offline, DNS, CORS, etc.)
    throw new ApiError("Network error — check your connection", 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      body.detail || `API error: ${res.status}`,
      res.status,
    );
  }
  return res.json();
}

export async function getHealth() {
  return apiFetch<{ status: string; b2_connected: boolean }>("/health");
}

export async function getFiles(prefix = "", limit = 100) {
  return apiFetch<FileMetadata[]>(
    `/files?prefix=${encodeURIComponent(prefix)}&limit=${limit}`
  );
}

export async function getFileStats() {
  return apiFetch<UploadStats>("/files/stats");
}

export async function getUploadActivity(days = 7) {
  return apiFetch<DailyUploadCount[]>(`/files/stats/activity?days=${days}`);
}

export async function getFile(key: string) {
  return apiFetch<FileMetadata>(`/files/${key}`);
}

export async function getDownloadUrl(key: string) {
  return apiFetch<{ url: string }>(`/files/${key}/download`);
}

/** Preview-only presigned URL — does NOT increment the download counter. */
export async function getPreviewUrl(key: string) {
  return apiFetch<{ url: string }>(`/files/${key}/preview`);
}

export async function deleteFile(key: string) {
  return apiFetch<{ deleted: boolean; key: string }>(`/files/${key}`, {
    method: "DELETE",
  });
}

export function uploadFile(
  file: File,
  onProgress?: (percent: number) => void
): Promise<FileUploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const body = JSON.parse(xhr.responseText);
          reject(new ApiError(body.detail || `Upload failed: ${xhr.status}`, xhr.status));
        } catch {
          reject(new ApiError(`Upload failed: ${xhr.status}`, xhr.status));
        }
      }
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError("Network error — check your connection", 0)),
    );
    xhr.addEventListener("abort", () =>
      reject(new ApiError("Upload aborted", 0)),
    );

    xhr.open("POST", `${API_BASE}/upload`);
    xhr.send(formData);
  });
}

// --- Video pipeline ---------------------------------------------------------

export async function getVideos() {
  return apiFetch<Video[]>("/videos");
}

export async function getVideo(videoId: string) {
  return apiFetch<Video>(`/videos/${videoId}`);
}

export async function getVideoPlayback(videoId: string) {
  return apiFetch<{ url: string }>(`/videos/${videoId}/playback`);
}

export async function deleteVideo(videoId: string) {
  return apiFetch<{ deleted: boolean; video_id: string; objects: number }>(
    `/videos/${videoId}`,
    { method: "DELETE" },
  );
}

export async function reindexVideo(videoId: string) {
  return apiFetch<Video>(`/videos/${videoId}/reindex`, { method: "POST" });
}

export interface SearchOptions {
  videoId?: string | null;
  topK?: number;
  synthesize?: boolean;
}

export async function searchVideos(question: string, opts: SearchOptions = {}) {
  return apiFetch<SearchResponse>("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      video_id: opts.videoId ?? null,
      top_k: opts.topK ?? 5,
      synthesize: opts.synthesize ?? false,
    }),
  });
}

async function createVideoUpload(file: File): Promise<MultipartUpload> {
  return apiFetch<MultipartUpload>("/videos/uploads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      size_bytes: file.size,
      content_type: file.type || "video/mp4",
    }),
  });
}

// PUT one part directly to B2's presigned URL. Returns the part ETag, which
// the browser can only read if the bucket's CORS config exposes the ETag
// header (Access-Control-Expose-Headers: ETag) — see docs/features/video-ingest.md.
function putPart(url: string, blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const etag = xhr.getResponseHeader("ETag");
        if (!etag) {
          reject(
            new ApiError(
              "B2 did not return an ETag — the bucket CORS policy must expose the ETag header.",
              xhr.status,
            ),
          );
          return;
        }
        resolve(etag);
      } else {
        reject(new ApiError(`Part upload failed: ${xhr.status}`, xhr.status));
      }
    });
    xhr.addEventListener("error", () =>
      reject(new ApiError("Network error during part upload", 0)),
    );
    xhr.send(blob);
  });
}

/**
 * Ingest a (potentially multi-GB) video: open a presigned multipart upload,
 * PUT each part straight to B2 from the browser, then tell the API to finalize
 * and kick off the transcription/embedding pipeline. The API never touches the
 * bytes.
 */
export async function ingestVideo(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<Video> {
  const upload = await createVideoUpload(file);
  const completed: CompletedPart[] = [];
  let uploadedBytes = 0;

  for (const part of upload.parts) {
    const start = (part.part_number - 1) * upload.part_size;
    const blob = file.slice(start, Math.min(start + upload.part_size, file.size));
    const etag = await putPart(part.url, blob);
    completed.push({ part_number: part.part_number, etag });
    uploadedBytes += blob.size;
    onProgress?.(Math.round((uploadedBytes / file.size) * 100));
  }

  return apiFetch<Video>("/videos/uploads/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: upload.video_id,
      source_key: upload.source_key,
      upload_id: upload.upload_id,
      title: file.name,
      size_bytes: file.size,
      content_type: file.type || "video/mp4",
      parts: completed,
    }),
  });
}
