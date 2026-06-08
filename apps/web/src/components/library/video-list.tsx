"use client";

import { RotateCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/library/status-badge";
import { useDeleteVideo, useReindexVideo } from "@/lib/queries";
import { formatDate, formatTimestamp } from "@/lib/utils";
import type { Video } from "@video-semantic-search/shared";

export function VideoList({ videos }: { videos: Video[] }) {
  const reindex = useReindexVideo();
  const remove = useDeleteVideo();

  const onReindex = (video: Video) => {
    reindex.mutate(video.video_id, {
      onSuccess: () => toast.success(`Re-indexing "${video.title}"…`),
      onError: (e) => toast.error(e instanceof Error ? e.message : "Reindex failed"),
    });
  };

  const onDelete = (video: Video) => {
    remove.mutate(video.video_id, {
      onSuccess: (res) =>
        toast.success(`Deleted "${video.title}" (${res.objects} objects).`),
      onError: (e) => toast.error(e instanceof Error ? e.message : "Delete failed"),
    });
  };

  return (
    <Table className="table-fixed">
      <TableHeader>
        <TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="w-[30%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Video
          </TableHead>
          <TableHead className="w-[16%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Status
          </TableHead>
          <TableHead className="w-[11%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Length
          </TableHead>
          <TableHead className="w-[10%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Chunks
          </TableHead>
          <TableHead className="w-[11%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Size
          </TableHead>
          <TableHead className="w-[12%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Added
          </TableHead>
          <TableHead className="w-[10%] text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Actions
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {videos.map((video) => (
          <TableRow key={video.video_id} className="table-row-hover">
            <TableCell className="font-medium">
              <div className="truncate">{video.title}</div>
              {video.error && (
                <div className="truncate text-xs text-muted-foreground">{video.error}</div>
              )}
            </TableCell>
            <TableCell>
              <StatusBadge status={video.status} />
            </TableCell>
            <TableCell className="font-mono text-xs text-muted-foreground tabular-nums whitespace-nowrap">
              {video.duration_seconds ? formatTimestamp(video.duration_seconds) : "—"}
            </TableCell>
            <TableCell className="text-muted-foreground tabular-nums">
              {video.chunk_count ?? "—"}
            </TableCell>
            <TableCell className="font-mono text-xs text-muted-foreground tabular-nums whitespace-nowrap">
              {video.size_human}
            </TableCell>
            <TableCell className="text-muted-foreground whitespace-nowrap">
              {formatDate(video.created_at)}
            </TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                title="Re-index"
                onClick={() => onReindex(video)}
                disabled={reindex.isPending}
              >
                <RotateCw className="h-3.5 w-3.5" />
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive hover:text-destructive"
                    title="Delete"
                    disabled={remove.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete this video?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Permanently removes &ldquo;{video.title}&rdquo; and all of its
                      derived data (audio, transcript, embeddings) from B2. This
                      cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => onDelete(video)}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
