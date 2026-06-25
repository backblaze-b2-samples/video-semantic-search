export type FileStatus = "uploading" | "complete" | "error";

export interface FileMetadata {
  key: string;
  filename: string;
  folder: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
}

export interface FileMetadataDetail {
  filename: string;
  size_bytes: number;
  size_human: string;
  mime_type: string;
  extension: string;
  md5: string;
  sha256: string;
  uploaded_at: string;
  // Image-specific
  image_width: number | null;
  image_height: number | null;
  exif: Record<string, string> | null;
  // PDF-specific
  pdf_pages: number | null;
  pdf_author: string | null;
  pdf_title: string | null;
  // Audio/Video
  duration_seconds: number | null;
  codec: string | null;
  bitrate: number | null;
}

export interface FileUploadResponse {
  key: string;
  filename: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
  metadata: FileMetadataDetail | null;
}

export interface DailyUploadCount {
  date: string;
  uploads: number;
}

export interface UploadStats {
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
  total_downloads: number;
}

// --- Video pipeline ---

export type VideoStatus =
  | "uploading"
  | "uploaded"
  | "extracting"
  | "transcribing"
  | "chunking"
  | "embedding"
  | "ready"
  | "failed";

export interface Video {
  video_id: string;
  title: string;
  status: VideoStatus;
  source_key: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  created_at: string;
  duration_seconds: number | null;
  chunk_count: number | null;
  error: string | null;
}

export interface PresignedPart {
  part_number: number;
  url: string;
}

export interface MultipartUpload {
  video_id: string;
  source_key: string;
  upload_id: string;
  part_size: number;
  parts: PresignedPart[];
}

export interface CompletedPart {
  part_number: number;
  etag: string;
}

export interface Clip {
  video_id: string;
  title: string;
  start: number;
  end: number;
  text: string;
  score: number;
  playback_url: string | null;
}

export interface SearchResponse {
  question: string;
  clips: Clip[];
  answer: string | null;
  provider_configured: boolean;
}
