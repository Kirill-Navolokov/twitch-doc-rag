import type { Citation } from "./askQuestion";

export type ExchangeStatus = "streaming" | "done" | "fallback" | "error";

export interface Exchange {
  id: number;
  question: string;
  citations: Citation[];
  answer: string;
  status: ExchangeStatus;
  error?: string;
}

export type ConversationAction =
  | { type: "ask"; id: number; question: string }
  | { type: "citations"; id: number; citations: Citation[] }
  | { type: "token"; id: number; text: string }
  | { type: "done"; id: number }
  | { type: "fallback"; id: number; text: string }
  | { type: "error"; id: number; message: string };

function applyToExchange(exchange: Exchange, action: ConversationAction): Exchange {
  switch (action.type) {
    case "citations":
      return { ...exchange, citations: action.citations };
    case "token":
      return { ...exchange, answer: exchange.answer + action.text };
    case "done":
      return { ...exchange, status: "done" };
    case "fallback":
      return { ...exchange, answer: action.text, status: "fallback" };
    case "error":
      // Keeps answer and citations: an error can interrupt an answer that is already part-rendered.
      return { ...exchange, status: "error", error: action.message };
    case "ask":
      return exchange;
  }
}

export function conversationReducer(
  state: Exchange[],
  action: ConversationAction,
): Exchange[] {
  if (action.type === "ask") {
    return [
      ...state,
      { id: action.id, question: action.question, citations: [], answer: "", status: "streaming" },
    ];
  }
  // Addressing the exchange by id means a cancelled stream's late events cannot land on a newer one.
  return state.map((exchange) =>
    exchange.id === action.id ? applyToExchange(exchange, action) : exchange,
  );
}
