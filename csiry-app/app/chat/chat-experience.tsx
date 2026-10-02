"use client";

import { useState, type FormEvent } from "react";
import { SiteHeader } from "../components/site-header";

type Message = {
  id: string;
  role: "assistant" | "user";
  content: string;
};

const suggestions = [
  "How do I process a vendor onboarding request?",
  "Which searches returned no results this month?",
  "What are the open action items from last week's meetings?",
];

export function ChatExperience() {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);

  function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();

    if (!content) {
      return;
    }

    setMessages((currentMessages) => [
      ...currentMessages,
      { id: crypto.randomUUID(), role: "user", content },
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          "This chat preview isn't connected to an AI service yet. Your message is ready for when one is connected.",
      },
    ]);
    setDraft("");
  }

  return (
    <main className="chat-page">
      <SiteHeader activePage="chat" />

      <section className="chat-workspace" aria-labelledby="chat-title">
        <div className="chat-heading">
          <h1 id="chat-title">Chat with Laplace</h1>
        </div>

        <div className="chat-panel">
          <div className="chat-thread" aria-live="polite">
            {messages.length === 0 ? (
              <div className="chat-welcome">
                <span className="chat-avatar" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                </span>
                <div>
                  <p className="chat-message-label">LAPLACE</p>
                  <p className="chat-message-content">
                    Hi, I&apos;m Laplace. Ask me anything about your
                    company&apos;s knowledge, and I&apos;ll answer with sources.
                  </p>
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <div
                  className={`chat-message chat-message-${message.role}`}
                  key={message.id}
                >
                  {message.role === "assistant" && (
                    <span
                      className="chat-avatar chat-avatar-small"
                      aria-hidden="true"
                    >
                      <span />
                      <span />
                      <span />
                      <span />
                    </span>
                  )}
                  <div className="chat-message-body">
                    <p className="chat-message-label">
                      {message.role === "assistant" ? "LAPLACE" : "YOU"}
                    </p>
                    <p className="chat-message-content">{message.content}</p>
                  </div>
                </div>
              ))
            )}
          </div>

          {messages.length === 0 && (
            <div className="chat-suggestions" aria-label="Suggested prompts">
              {suggestions.map((suggestion) => (
                <button
                  className="chat-suggestion"
                  key={suggestion}
                  onClick={() => setDraft(suggestion)}
                  type="button"
                >
                  {suggestion}
                  <span aria-hidden="true">↗</span>
                </button>
              ))}
            </div>
          )}

          <form className="chat-composer" onSubmit={sendMessage}>
            <label className="visually-hidden" htmlFor="chat-message">
              Write a message
            </label>
            <textarea
              id="chat-message"
              name="message"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Message Laplace..."
              rows={1}
              value={draft}
            />
            <button
              aria-label="Send message"
              className="chat-send"
              disabled={!draft.trim()}
              type="submit"
            >
              <span aria-hidden="true">↑</span>
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
