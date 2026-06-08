from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Backblaze B2 (S3-compatible) ---
    # Standardized B2_* names. This differs from the upstream starter kit,
    # which used B2_KEY_ID and had no region — both corrected here.
    b2_endpoint: str = "https://s3.us-west-004.backblazeb2.com"
    b2_application_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    b2_region: str = "us-west-004"
    b2_public_url: str = ""

    # --- AI providers (video pipeline) ---
    # Empty keys = the video features are disabled and degrade gracefully:
    # the API returns a clear "provider not configured" state instead of
    # crashing, and the generic B2 surfaces (upload, files) keep working.
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    transcription_provider: str = "openai"  # "openai" | "local"
    embedding_model: str = "text-embedding-3-small"
    answer_model: str = "claude-sonnet-4-6"

    # --- Sample namespace + ingest limits ---
    # All of this sample's objects live under this prefix so the bucket can
    # be shared with other samples without collisions.
    video_prefix: str = "video-semantic-search/"
    max_video_size: int = 5 * 1024 * 1024 * 1024  # 5 GB
    multipart_part_size: int = 64 * 1024 * 1024  # 64 MB per multipart part

    # --- API / generic upload ---
    api_port: int = 8000
    # Explicit allowlist by default — covers Next on :3000 and the
    # fallback :3001 it picks if 3000 is busy. Production deploys should
    # override with the exact frontend origin.
    api_cors_origins: str = "http://localhost:3000,http://localhost:3001"
    # Optional dev-only escape hatch: a regex that matches additional
    # allowed origins. Empty by default. NEVER ship this to production.
    api_cors_origin_regex: str = ""

    # Generic /upload cap (small assets proxied through the API). Large video
    # never flows through the API — it uses presigned multipart, browser → B2.
    max_file_size: int = 100 * 1024 * 1024  # 100 MB

    # Small durable counters (plays/downloads, etc). Point at a persistent
    # volume in production if you care about surviving restarts.
    download_count_file: str = "data/download_count.json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",")]


settings = Settings()
