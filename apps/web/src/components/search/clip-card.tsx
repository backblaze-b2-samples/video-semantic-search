import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { formatTimestamp } from "@/lib/utils";
import type { Clip } from "@video-semantic-search/shared";

export function ClipCard({ clip }: { clip: Clip }) {
  // Media fragment (#t=start,end) tells the browser to play exactly this
  // moment — no clip file is generated; we seek the source video in B2.
  const src = clip.playback_url
    ? `${clip.playback_url}#t=${clip.start.toFixed(2)},${clip.end.toFixed(2)}`
    : null;

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium truncate">{clip.title}</span>
          <Badge variant="secondary" className="font-mono tabular-nums">
            {formatTimestamp(clip.start)}–{formatTimestamp(clip.end)}
          </Badge>
        </div>
        {src ? (
          <video
            controls
            preload="metadata"
            className="w-full rounded-md border border-border bg-black aspect-video"
            src={src}
          />
        ) : (
          <p className="text-xs text-muted-foreground">Playback URL unavailable.</p>
        )}
        <p className="text-sm text-muted-foreground line-clamp-4">{clip.text}</p>
      </CardContent>
    </Card>
  );
}
