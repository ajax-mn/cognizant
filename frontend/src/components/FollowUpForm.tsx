import { useState } from "react";

interface Props {
  onSubmit: (question: string) => void;
  loading: boolean;
}

const FOLLOW_UP_SUGGESTIONS = [
  "Filter only for 2024",
  "Sort by amount descending",
  "Limit to top 10",
  "Only for Kerala",
];

export function FollowUpForm({ onSubmit, loading }: Props) {
  const [question, setQuestion] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (trimmed && !loading) {
      onSubmit(trimmed);
      setQuestion("");
    }
  }

  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <label
          htmlFor="followup-question"
          className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-indigo-900"
        >
          <svg
            className="h-3.5 w-3.5 text-indigo-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
            />
          </svg>
          Ask a Follow-up Question
        </label>
        <span className="text-[11px] font-medium text-indigo-600">
          Refines current SQL query
        </span>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          id="followup-question"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Only for Kerala, or sort by highest revenue, or compare with 2025..."
          disabled={loading}
          className="flex-1 rounded-md border border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-indigo-500 focus:outline-none disabled:bg-neutral-100"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-neutral-300"
        >
          {loading ? "Refining…" : "Refine"}
        </button>
      </form>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-neutral-500">Suggestions:</span>
        {FOLLOW_UP_SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            disabled={loading}
            onClick={() => setQuestion(suggestion)}
            className="rounded-full border border-indigo-200 bg-white px-2.5 py-0.5 text-[11px] text-indigo-700 transition-colors hover:bg-indigo-50 disabled:opacity-50"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
