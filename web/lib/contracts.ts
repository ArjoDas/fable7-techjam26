export type DemoMode = "internals" | "demo";

export type QueryAnnotation = {
  start: number;
  end: number;
  text: string;
  kind: "category" | "constraint" | "intent" | "override" | "boundary" | "exhausted";
};

export type RouteTrace = {
  name: "conjunctive" | "phrase" | "disjunctive" | "popularity";
  weight: number;
  count: number;
  asins: string[];
};

export type FusedEntry = { asin: string; score: number };

export type MergedPoolEntry = {
  asin: string;
  exact: boolean;
  routes: string[];
};

export type LinearScore = { asin: string; score: number };

export type PrefixTrace = {
  category: string;
  values: string[];
  match_count: number;
  matches: string[];
} | null;

export type SemanticCategoryCandidate = {
  category: string;
  lexical: number;
  semantic: number | null;
  score: number;
};

export type SemanticValueCandidate = {
  value: string;
  support: number;
  lexical: number;
  semantic: number | null;
  score: number;
};

export type SemanticTrace = {
  input: string;
  browsing: boolean;
  override: boolean;
  no_preference: boolean;
  buy_switch: boolean;
  encoder_used: boolean;
  encoder_error: string | null;
  category_candidates: SemanticCategoryCandidate[];
  chosen_category: string | null;
  value_candidates: SemanticValueCandidate[];
  chosen_values: string[];
  canonical_message: string | null;
};

export type AgentTrace = {
  message: string;
  input_message?: string;
  agent_message?: string;
  semantic?: SemanticTrace | null;
  query_annotations: QueryAnnotation[];
  catalog: { count: number };
  conversation: {
    protocol_compatible: boolean;
    intent_mode: string;
    override_seen: boolean;
    boundary_seen: boolean;
    exploratory: boolean;
    exhausted: boolean;
    intent_switched: boolean;
  };
  query: {
    category: string;
    category_applied: boolean;
    category_count: number | null;
    terms: string[];
    constraints: string[];
  };
  retrieval: {
    bm25_count: number;
    exact_evidence_count: number;
    merged_count: number;
    candidate_asins: string[];
    routes: RouteTrace[];
    category_dropped: boolean;
    fused: FusedEntry[];
    fused_asins: string[];
    exact_asins: string[];
    merged_pool: MergedPoolEntry[];
  };
  ranking: {
    linear_count: number;
    linear_head: string[];
    linear_ranking: string[];
    linear_scores: LinearScore[];
    dialogue_match_count: number | null;
    dialogue_head: string[];
    dialogue_ranking: string[];
    prefix: PrefixTrace;
  };
  selection: {
    decision: "top_k" | "abstain_1" | "rotation";
    output_k: number;
    coverage_rotation_used: boolean;
    rotation_skipped: string[];
    opening_abstention_used: boolean;
    ambiguity_abstention_used: boolean;
    shown_before: number;
    shown_after: number;
    selected: string[];
  };
};

export type ProductCard = {
  parent_asin: string;
  title: string;
  price: number | null;
  store: string;
  average_rating: number | null;
  rating_number: number | null;
  category: string;
  feature: string;
  features: string[];
  description: string[];
  categories: string[];
  details: Record<string, unknown>;
};

export type SessionResponse = {
  session_id: string;
  mode: DemoMode;
  turn: number;
  max_turns: number;
  catalog_size: number;
};

export type TurnResponse = {
  session_id: string;
  mode: DemoMode;
  turn: number;
  max_turns: number;
  assistant: { message: string; ask_attribute: string | null };
  recommendations: ProductCard[];
  trace: AgentTrace | null;
};

export type ExampleTurn = { structured: string; natural: string };

export type ExampleSession = {
  id: string;
  label: string;
  scenario: "buying" | "browsing" | "rotation" | "override";
  category: string;
  target_asin: string;
  target_title: string;
  turns: ExampleTurn[];
};

export type ReadyResponse = {
  status: "initializing" | "ready" | "error";
  catalog_size: number | null;
  startup_seconds: number | null;
  message: string | null;
};
