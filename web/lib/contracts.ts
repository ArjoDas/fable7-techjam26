export type DemoMode = "internals" | "demo";

export type MessageOption = {
  id: string;
  label: string;
  message_preview: string;
  kind: "opening" | "constraint" | "no_preference" | "override" | "intent";
  estimated_remaining: number | null;
  intent: "browse" | "buy" | null;
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
};

export type AgentTrace = {
  catalog: { count: number };
  conversation: {
    protocol_compatible: boolean;
    intent_mode: string;
    override_seen: boolean;
    boundary_seen: boolean;
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
  };
  ranking: {
    linear_count: number;
    linear_head: string[];
    dialogue_match_count: number | null;
    dialogue_head: string[];
  };
  selection: {
    coverage_rotation_used: boolean;
    opening_abstention_used: boolean;
    ambiguity_abstention_used: boolean;
    shown_before: number;
    shown_after: number;
    selected: string[];
  };
};

export type SessionResponse = {
  session_id: string;
  mode: DemoMode;
  turn: number;
  max_turns: number;
  catalog_size: number;
  message_options: MessageOption[];
};

export type TurnResponse = {
  session_id: string;
  mode: DemoMode;
  turn: number;
  max_turns: number;
  assistant: { message: string; ask_attribute: string | null };
  recommendations: ProductCard[];
  message_options: MessageOption[];
  trace: AgentTrace | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};
