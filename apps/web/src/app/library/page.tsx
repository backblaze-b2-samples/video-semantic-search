"use client";

import { Film } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { IngestDialog } from "@/components/library/ingest-dialog";
import { VideoList } from "@/components/library/video-list";
import { useVideos } from "@/lib/queries";

export default function LibraryPage() {
  const { data: videos = [], isLoading, error, refetch } = useVideos();

  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Library</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Videos ingested into this sample&apos;s B2 namespace, with their
            transcription &amp; indexing status.
          </p>
        </div>
        <IngestDialog />
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : error ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : videos.length === 0 ? (
            <EmptyState
              icon={Film}
              title="No videos yet"
              description="Add a video to transcribe it and make it searchable. It's stored entirely in Backblaze B2."
            />
          ) : (
            <VideoList videos={videos} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
