"use client";

import Link from "next/link";
import { ArrowRight, Film } from "lucide-react";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { StatusBadge } from "@/components/library/status-badge";
import { useVideos } from "@/lib/queries";
import { formatDate, formatTimestamp } from "@/lib/utils";

export function RecentVideosTable() {
  const { data: videos = [], isLoading, error, refetch } = useVideos();
  const recent = videos.slice(0, 8);

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Recent Videos</CardTitle>
        <CardAction className="self-center">
          <Link
            href="/library"
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            View library
            <ArrowRight className="h-3 w-3" />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : recent.length === 0 ? (
          <EmptyState
            icon={Film}
            title="No videos yet"
            description="Add a video on the Library page to start indexing."
          />
        ) : (
          <Table className="table-fixed">
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="w-[46%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Video
                </TableHead>
                <TableHead className="w-[24%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Status
                </TableHead>
                <TableHead className="w-[14%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Length
                </TableHead>
                <TableHead className="w-[16%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Added
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recent.map((video) => (
                <TableRow key={video.video_id} className="table-row-hover">
                  <TableCell className="font-medium">
                    <div className="truncate">{video.title}</div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={video.status} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                    {video.duration_seconds ? formatTimestamp(video.duration_seconds) : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {formatDate(video.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
