import type { ExampleSession, TurnResponse } from "./contracts";

export type QueryMode = "structured" | "natural";
export type RecordedTurn = { turn: number; input: string; response: TurnResponse };
export type RecordedSession = {
  schema_version: 1;
  example_id: string;
  mode: QueryMode;
  turns: RecordedTurn[];
};
export type RecordedExample = ExampleSession & {
  engine_example_id: string;
  recordings: Record<QueryMode, { file: string; matching: ("protocol" | "literal" | "minilm")[] }>;
};
export type DemoManifest = {
  schema_version: 1;
  provenance: {
    recorded_at: string;
    source_repository: string;
    source_commit: string;
    runtime_source_sha256: string;
    catalog_sha256: string;
    catalog_size: number;
    model: { repository: string; revision: string; files: Record<string, string> };
  };
  examples: RecordedExample[];
};

const recordings = new Map<string, RecordedSession>();

async function readJson(path: string, signal: AbortSignal) {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error("The recording could not be loaded. Please try again.");
  return response.json();
}

export async function loadManifest(signal: AbortSignal): Promise<DemoManifest> {
  const manifest: DemoManifest = await readJson("/recordings/manifest.json", signal);
  if (manifest.schema_version !== 1 || !manifest.examples?.length || !manifest.provenance?.source_commit) {
    throw new Error("The recording index is invalid. Please reload the page.");
  }
  return manifest;
}

export async function loadRecording(example: RecordedExample, mode: QueryMode, signal: AbortSignal): Promise<RecordedSession> {
  const file = example.recordings[mode].file;
  if (recordings.has(file)) return recordings.get(file)!;
  const recording: RecordedSession = await readJson(`/recordings/${encodeURIComponent(file)}`, signal);
  if (recording.schema_version !== 1 || recording.example_id !== example.id || recording.mode !== mode ||
      recording.turns?.length !== example.turns.length ||
      !recording.turns.every((turn, index) => turn.turn === index + 1 &&
        turn.input === example.turns[index][mode] && turn.response?.trace &&
        Array.isArray(turn.response.recommendations))) {
    throw new Error("This recording is incomplete or incompatible. Please reload the page.");
  }
  recordings.set(file, recording);
  return recording;
}
