"use client";

import { useState } from "react";
import { KeyRound, Search as SearchIcon, Sparkles, Telescope } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ClipCard } from "@/components/search/clip-card";
import { useSearch } from "@/lib/queries";
import type { Clip } from "@video-semantic-search/shared";

export default function SearchPage() {
  const [question, setQuestion] = useState("");
  const [synthesize, setSynthesize] = useState(false);
  const search = useSearch();

  const submit = () => {
    const q = question.trim();
    if (!q) return;
    search.mutate({ question: q, synthesize });
  };

  const data = search.data;

  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Search</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Ask a question in plain language and get back the exact timestamped
          moments that answer it — playable inline.
        </p>
      </div>

      <Card>
        <CardContent className="p-5 space-y-4">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. What did they say about pricing? (⌘/Ctrl + Enter to search)"
            className="min-h-20"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
            }}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Switch
                id="synthesize"
                checked={synthesize}
                onCheckedChange={setSynthesize}
              />
              <Label htmlFor="synthesize" className="text-muted-foreground">
                <Sparkles className="h-3.5 w-3.5" />
                Synthesize an answer (Claude)
              </Label>
            </div>
            <Button onClick={submit} disabled={search.isPending || !question.trim()} size="sm">
              <SearchIcon className="h-3.5 w-3.5" />
              {search.isPending ? "Searching…" : "Search"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {search.isPending && (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-64 w-full" />
          ))}
        </div>
      )}

      {search.error && !search.isPending && (
        <Card>
          <CardContent className="p-0">
            <ErrorState error={search.error} onRetry={submit} />
          </CardContent>
        </Card>
      )}

      {data && !search.isPending && (
        <SearchResults
          providerConfigured={data.provider_configured}
          answer={data.answer}
          clips={data.clips}
        />
      )}
    </div>
  );
}

function SearchResults({
  providerConfigured,
  answer,
  clips,
}: {
  providerConfigured: boolean;
  answer: string | null;
  clips: Clip[];
}) {
  if (!providerConfigured) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={KeyRound}
            title="No embedding provider configured"
            description="Set OPENAI_API_KEY in your .env and restart the API to enable semantic search."
          />
        </CardContent>
      </Card>
    );
  }

  if (clips.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={Telescope}
            title="No matching moments"
            description="Ingest a video on the Library page, wait for it to reach “Ready”, then try a different question."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {answer && (
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              <Sparkles className="h-3.5 w-3.5" />
              Answer
            </div>
            <p className="text-sm whitespace-pre-wrap">{answer}</p>
          </CardContent>
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {clips.map((clip) => (
          <ClipCard key={`${clip.video_id}-${clip.start}`} clip={clip} />
        ))}
      </div>
    </div>
  );
}
