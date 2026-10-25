"use client";

import ChatBot, { useMessages, type Flow, type Params, type Settings, type Styles } from "react-chatbotify";
import { useCallback, useEffect, useMemo } from "react";
import { ApiError, post } from "@/lib/api";
import type { AssistantAnswer } from "@/lib/types";
import "./assistant-widget.css";

const EXAMPLES = [
  "whats FEFO",
  "How much stock of SKU0001 is at Store 001?",
  "Which stores will run out of stock in the North region?",
  "How does the optimized plan compare with the baseline?",
  "What is the forecast accuracy?",
  "How do I approve a plan?",
];

const INTENT_WORDS: Record<string, string> = {
  glossary: "term explanation",
  stock: "stock lookup",
  stockout_risk: "stockout risk",
  forecast: "forecast lookup",
  accuracy: "forecast accuracy",
  compare: "baseline comparison",
  plan: "plan status",
  howto: "how-to help",
  greeting: "greeting",
  about: "about VebStock",
};

function intentWords(intent: string | null): string {
  if (!intent) return "";
  return INTENT_WORDS[intent] ?? intent.replace(/_/g, " ");
}

type Api = Pick<Params, "injectMessage" | "removeMessage">;
type Send = (q: string, opts?: { echo?: boolean }) => void;

let reportLabel: (l: string) => void = () => {};

/** Ask the backend and write the exchange into the chat. Shared by typed input, chips and Retry. */
async function run(q: string, api: Api, echo: boolean) {
  if (echo) await api.injectMessage(q, "USER");
  const thinking = await api.injectMessage(<Thinking />);
  try {
    const a = await post<AssistantAnswer>("/assistant", { question: q.slice(0, 300) });
    if (thinking) await api.removeMessage(thinking.id);
    reportLabel(a.label);
    await api.injectMessage(<AnswerView a={a} />);
  } catch (e) {
    if (thinking) await api.removeMessage(thinking.id);
    const err = e instanceof ApiError ? e : new ApiError(String(e), 0);
    await api.injectMessage(<ErrorView err={err} q={q} />);
  }
}

/** Sends a question from inside a rendered message (chips, Retry) using the live chat hooks. */
function useSend(): Send {
  const m = useMessages();
  const inject = m.injectMessage;
  const remove = m.removeMessage;
  return useCallback<Send>((q, opts) => void run(q, { injectMessage: inject, removeMessage: remove }, opts?.echo ?? true), [inject, remove]);
}

function ErrorView({ err, q }: { err: ApiError; q: string }) {
  const send = useSend();
  return (
    <div role="alert" data-testid="assistant-error" className="vs-bubble">
      <div className="font-semibold">{err.unreachable ? "The backend is unreachable or waking up." : "That did not work."}</div>
      <div className="mt-1">{err.message}</div>
      <button type="button" className="vs-chip mt-2" data-testid="assistant-retry" onClick={() => send(q, { echo: false })}>
        Retry
      </button>
    </div>
  );
}

function Chips({ items }: { items: string[] }) {
  const send = useSend();
  return (
    <div className="mt-3" data-testid="assistant-chips">
      {items.map((s) => (
        <button key={s} type="button" className="vs-chip" onClick={() => send(s)}>
          {s}
        </button>
      ))}
    </div>
  );
}

function AnswerView({ a }: { a: AssistantAnswer }) {
  const pct = Math.round(a.confidence * 100);
  return (
    <div className="answer-text vs-bubble" data-testid="assistant-answer">
      <div className="whitespace-pre-wrap">{a.answer}</div>
      <div className="vs-meta">
        {a.intent ? `Understood as: ${intentWords(a.intent)} (${pct}%)` : `No matching topic found (best match ${pct}%)`}
      </div>
      {a.sources.length ? (
        <details className="mt-2">
          <summary>Sources ({a.sources.length})</summary>
          <ul className="mt-1">
            {a.sources.map((s, i) => (
              <li key={i} className="vs-meta break-words">
                {s.tool} · {Object.entries(s.args).map(([k, v]) => `${k}=${String(v)}`).join(", ")} · {s.rows} row{s.rows === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {a.suggestions.length ? (
        <div className="mt-3">
          <div className="vs-meta">{a.in_scope ? "You could also ask:" : "Try one of these:"}</div>
          <Chips items={a.suggestions} />
        </div>
      ) : null}
    </div>
  );
}

function Thinking() {
  return (
    <div role="status" aria-label="Thinking" data-testid="assistant-thinking" className="vs-bubble vs-thinking">
      <span className="vs-dot" />
      <span className="vs-dot" />
      <span className="vs-dot" />
    </div>
  );
}

const SETTINGS: Settings = {
  general: {
    embedded: true,
    flowStartTrigger: "ON_LOAD",
    showHeader: false,
    showFooter: false,
    primaryColor: "var(--ink)",
    secondaryColor: "var(--ink)",
    fontFamily: "var(--font-sans)",
  },
  chatWindow: { defaultOpen: true, showTypingIndicator: true, autoJumpToBottom: true },
  chatHistory: { disabled: true },
  tooltip: { mode: "NEVER" },
  notification: { disabled: true },
  audio: { disabled: true },
  voice: { disabled: true },
  emoji: { disabled: true },
  fileAttachment: { disabled: true },
  userBubble: { showAvatar: false, animate: false, simulateStream: false },
  botBubble: { showAvatar: false, animate: false, simulateStream: false },
  chatInput: {
    characterLimit: 300,
    showCharacterCount: true,
    enabledPlaceholderText: "Ask about stock, forecasts, risk or a plan",
    allowNewline: false,
    botDelay: 0,
  },
  ariaLabel: { inputTextArea: "Ask the VebStock assistant a question", sendButton: "Send question" },
};

const STYLES: Styles = {
  chatWindowStyle: { width: "100%", height: "100%", borderRadius: 0 },
  bodyStyle: { background: "var(--paper)" },
  botBubbleStyle: { borderRadius: 2, background: "var(--paper)", color: "var(--ink)" },
  userBubbleStyle: { borderRadius: 2, background: "var(--ink)", color: "var(--paper)" },
  sendButtonStyle: { borderRadius: 0, background: "var(--ink)" },
};

/** react-chatbotify wired to POST /assistant. Loaded lazily the first time the panel opens. */
export default function AssistantWidget({ onLabel, active }: { onLabel: (l: string) => void; active: boolean }) {
  useEffect(() => {
    reportLabel = onLabel;
    return () => {
      reportLabel = () => {};
    };
  }, [onLabel]);

  const flow = useMemo<Flow>(
    () => ({
      // The library re-processes `start` for the very first user input, so `start` must also answer it
      // (and must not repeat the intro in that case).
      start: {
        component: (p: Params) =>
          p.userInput?.trim() ? undefined : (
            <div data-testid="assistant-intro" className="vs-intro vs-bubble">
              <div>
                Hi, I am the VebStock assistant. Ask in your own words about stock, forecasts, stockout risk, plans, the baseline comparison or how VebStock works. Spelling slips are fine.
              </div>
              <div className="vs-meta mt-2">Try:</div>
              <Chips items={EXAMPLES} />
            </div>
          ),
        function: async (p) => {
          if (p.userInput?.trim()) await run(p.userInput, p, false);
        },
        chatDisabled: false,
        path: "ask",
      },
      ask: {
        function: async (p) => {
          await run(p.userInput, p, false);
        },
        chatDisabled: false,
        path: "ask",
      },
    }),
    [],
  );

  // Focus the text box once the widget has mounted (it loads lazily).
  useEffect(() => {
    if (!active) return;
    let tries = 0;
    const id = window.setInterval(() => {
      const ta = document.querySelector<HTMLTextAreaElement>("#assistant-panel .rcb-chat-input-textarea");
      if (ta) {
        ta.focus();
        window.clearInterval(id);
      } else if (++tries > 30) window.clearInterval(id);
    }, 100);
    return () => window.clearInterval(id);
  }, [active]);

  return (
    <div className="vs-chat" data-testid="assistant-widget">
      <ChatBot id="vebstock-assistant" flow={flow} settings={SETTINGS} styles={STYLES} />
    </div>
  );
}
