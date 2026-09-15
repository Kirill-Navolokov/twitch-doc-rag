"use client";

import { useState } from "react";

import type { FormEvent } from "react";

interface MessageInputProps {
  disabled: boolean;
  onSubmit: (question: string) => void;
}

export function MessageInput({ disabled, onSubmit }: MessageInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = value.trim();
    if (disabled || question === "") return;
    setValue("");
    onSubmit(question);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 rounded-lg border border-line bg-surface p-2 focus-within:border-violet"
    >
      <input
        type="text"
        aria-label="Your question"
        placeholder="Ask about the Twitch API"
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-[0.9375rem] placeholder:text-muted/70 focus:outline-none disabled:text-muted"
      />
      <button
        type="submit"
        disabled={disabled || value.trim() === ""}
        className="shrink-0 rounded-md bg-violet px-4 py-1.5 text-sm font-medium text-white disabled:bg-line disabled:text-muted"
      >
        {disabled ? "Asking" : "Ask"}
      </button>
    </form>
  );
}
