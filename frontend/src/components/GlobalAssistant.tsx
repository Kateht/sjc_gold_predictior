import { FormEvent, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { askAssistant } from '@/lib/api';

type AssistantRole = 'assistant' | 'user';

type AssistantMessage = {
  id: number;
  role: AssistantRole;
  content: string;
};

const defaultSuggestions = [
  'Bạn là ai?',
  'Tóm tắt xu hướng SJC hôm nay',
  'Model nào đang phù hợp cho dự báo 7 ngày?',
  'Bạn có thể hỗ trợ những gì?',
];

const routeSuggestions: Record<string, string[]> = {
  '/': ['Bạn là ai?', 'So sánh các model đang active', 'Chart 30 ngày đang nói gì?'],
  '/predict': ['Dự báo 7 ngày tới cho SJC', 'So sánh model price và trend', 'Giải thích kết quả dự báo gần nhất'],
  '/news': ['Tin tức nào đáng chú ý nhất?', 'Nhóm tin nào đang tác động mạnh tới vàng?', 'Có headline nào về lãi suất không?'],
  '/history': ['Xu hướng lịch sử 30 ngày là gì?', 'Tìm điểm đảo chiều gần nhất', 'Xuất CSV lịch sử ra sao?'],
  '/admin': ['Model nào đang active?', 'Cách đổi default model là gì?', 'Crawler gần nhất chạy thế nào?'],
  '/login': ['Hệ thống này hỗ trợ những gì?', 'Tôi có thể xem forecast gì sau khi đăng nhập?', 'App đang theo dõi dữ liệu nào?'],
};

function getRouteKey(pathname: string): string {
  if (pathname.startsWith('/predict')) {
    return '/predict';
  }
  if (pathname.startsWith('/news')) {
    return '/news';
  }
  if (pathname.startsWith('/history')) {
    return '/history';
  }
  if (pathname.startsWith('/admin')) {
    return '/admin';
  }
  if (pathname.startsWith('/login')) {
    return '/login';
  }
  return '/';
}

function getRouteTitle(pathname: string): string {
  switch (getRouteKey(pathname)) {
    case '/predict':
      return 'Prediction workspace';
    case '/news':
      return 'News context';
    case '/history':
      return 'Prediction history';
    case '/admin':
      return 'Admin operations';
    case '/login':
      return 'Authentication help';
    default:
      return 'Market overview';
  }
}

function createInitialMessage(pathname: string): AssistantMessage {
  return {
    id: 1,
    role: 'assistant',
    content: `I can help with gold prices, forecasts, model selection, news, history, and admin flows on ${getRouteTitle(pathname)}.`,
  };
}

export function GlobalAssistant() {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<AssistantMessage[]>([createInitialMessage(location.pathname)]);
  const [isSending, setIsSending] = useState(false);
  const nextIdRef = useRef(2);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const routeKey = getRouteKey(location.pathname);
  const suggestions = routeSuggestions[routeKey] ?? defaultSuggestions;

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [isOpen, messages]);

  useEffect(() => {
    setMessages((current) => {
      if (current.length !== 1 || current[0]?.role !== 'assistant') {
        return current;
      }
      return [createInitialMessage(location.pathname)];
    });
  }, [location.pathname]);

  function appendMessage(role: AssistantRole, content: string) {
    setMessages((current) => [...current, { id: nextIdRef.current++, role, content }]);
  }

  async function submitQuestion(rawQuestion: string) {
    const trimmed = rawQuestion.trim();
    if (!trimmed || isSending) {
      return;
    }

    setIsOpen(true);
    appendMessage('user', trimmed);
    setQuestion('');
    setIsSending(true);

    try {
      const response = await askAssistant(trimmed);
      appendMessage('assistant', response.answer);
    } catch (error) {
      appendMessage('assistant', error instanceof Error ? error.message : 'Assistant is temporarily unavailable.');
    } finally {
      setIsSending(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitQuestion(question);
  }

  function handleClear() {
    setMessages([createInitialMessage(location.pathname)]);
    setQuestion('');
  }

  return (
    <>
      <button
        type="button"
        className="assistant-fab"
        aria-label={isOpen ? 'Close assistant' : 'Open assistant'}
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="assistant-fab__dot" />
        <span>AI Support</span>
      </button>

      {isOpen ? (
        <section className="assistant-dock panel">
          <div className="assistant-dock__header">
            <div>
              <p className="eyebrow">Global assistant</p>
              <strong>{getRouteTitle(location.pathname)}</strong>
              <span>Ask about price, forecast, model lineup, news, history, or admin flows.</span>
            </div>
            <button type="button" className="button button--ghost assistant-dock__close" onClick={() => setIsOpen(false)}>
              Close
            </button>
          </div>

          <div className="assistant-dock__messages" aria-live="polite">
            {messages.map((message) => (
              <article key={message.id} className={`assistant-message assistant-message--${message.role}`}>
                <span className="assistant-message__label">{message.role === 'assistant' ? 'Assistant' : 'You'}</span>
                <p>{message.content}</p>
              </article>
            ))}
            {isSending ? (
              <article className="assistant-message assistant-message--assistant assistant-message--typing">
                <span className="assistant-message__label">Assistant</span>
                <div className="chat-typing" aria-label="Assistant is typing">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            ) : null}
            <div ref={messagesEndRef} />
          </div>

          <div className="assistant-dock__suggestions">
            {suggestions.map((suggestion) => (
              <button key={suggestion} type="button" className="assistant-chip" onClick={() => void submitQuestion(suggestion)}>
                {suggestion}
              </button>
            ))}
          </div>

          <form className="assistant-dock__composer" onSubmit={handleSubmit}>
            <textarea
              className="textarea textarea--chat"
              placeholder="Ask about SJC, model choice, news, or history..."
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void submitQuestion(question);
                }
              }}
            />
            <div className="assistant-dock__actions">
              <button type="submit" className="button button--primary" disabled={isSending || !question.trim()}>
                Send
              </button>
              <button type="button" className="button button--ghost" onClick={handleClear}>
                Reset
              </button>
            </div>
            <p className="assistant-dock__hint">Use Ctrl+Enter to send from the keyboard.</p>
          </form>
        </section>
      ) : null}
    </>
  );
}
