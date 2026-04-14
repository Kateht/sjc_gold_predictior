import { FormEvent, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { askAssistant } from '@/lib/api';
import { RichMessage } from '@/components/RichMessage';

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
  '/': [
    'Dự báo giá vàng SJC trong 7 ngày tới (LSTM)',
    'Dự báo giá vàng SJC 5 ngày tới',
    'Xu hướng giá vàng ngày mai là tăng hay giảm? (Classification)',
  ],
  '/predict': [
    'Dự báo giá vàng SJC trong 7 ngày tới (LSTM)',
    'Dự báo giá vàng SJC 5 ngày tới',
    'Xu hướng giá vàng ngày mai là tăng hay giảm? (Classification)',
  ],
  '/news': ['Tin tức nào đáng chú ý nhất?', 'Nhóm tin nào đang tác động mạnh tới vàng?', 'Có headline nào về lãi suất không?'],
  '/history': ['Xu hướng lịch sử 30 ngày là gì?', 'Tìm điểm đảo chiều gần nhất', 'Xuất CSV lịch sử ra sao?'],
  '/admin': [
    'Kiểm tra trạng thái crawler dữ liệu',
    'Xem các model đang được kích hoạt',
    'Kiểm tra lịch sử đồng bộ dữ liệu',
  ],
  '/login': ['Hỗ trợ đăng nhập', 'Quên mật khẩu thì làm sao?', 'Tôi cần trợ giúp truy cập tài khoản'],
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
      return 'Khu vực dự báo';
    case '/news':
      return 'Tin tức';
    case '/history':
      return 'Lịch sử dự báo';
    case '/admin':
      return 'Khu vực quản trị';
    case '/login':
      return 'Hỗ trợ đăng nhập';
    default:
      return 'Tổng quan thị trường';
  }
}

function createInitialMessage(pathname: string): AssistantMessage {
  return {
    id: 1,
    role: 'assistant',
    content: `Mình có thể hỗ trợ xem giá vàng, dự báo, chọn model, tin tức và lịch sử trên ${getRouteTitle(pathname)}.`,
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
      appendMessage('assistant', error instanceof Error ? error.message : 'Trợ lý hiện đang tạm thời không khả dụng.');
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
        aria-label={isOpen ? 'Đóng trợ lý' : 'Mở trợ lý'}
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="assistant-fab__dot" />
        <span>Trợ lý AI</span>
      </button>

      {isOpen ? (
        <section className="assistant-dock panel">
          <div className="assistant-dock__header">
            <div>
              <p className="eyebrow">Trợ lý chung</p>
              <strong>{getRouteTitle(location.pathname)}</strong>
              <span>Hỏi về giá, dự báo, model, tin tức hoặc lịch sử.</span>
            </div>
            <button type="button" className="button button--ghost assistant-dock__close" onClick={() => setIsOpen(false)}>
              Đóng
            </button>
          </div>

          <div className="assistant-dock__messages" aria-live="polite">
            {messages.map((message) => (
              <article key={message.id} className={`assistant-message assistant-message--${message.role}`}>
                <span className="assistant-message__label">{message.role === 'assistant' ? 'Trợ lý' : 'Bạn'}</span>
                <RichMessage content={message.content} />
              </article>
            ))}
            {isSending ? (
              <article className="assistant-message assistant-message--assistant assistant-message--typing">
                <span className="assistant-message__label">Trợ lý</span>
                <div className="chat-typing" aria-label="Trợ lý đang nhập">
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
              placeholder="Hỏi về SJC, chọn model, tin tức hoặc lịch sử..."
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
                Gửi
              </button>
              <button type="button" className="button button--ghost" onClick={handleClear}>
                Xóa
              </button>
            </div>
            <p className="assistant-dock__hint">Nhấn Ctrl+Enter để gửi nhanh từ bàn phím.</p>
          </form>
        </section>
      ) : null}
    </>
  );
}
