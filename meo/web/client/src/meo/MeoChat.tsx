import { useBrowserPreferences } from './browserPreferences';
import { FormEvent, isValidElement, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import remarkGfm from 'remark-gfm';
import ReactMarkdown from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import type { MeoConsent } from './MeoConsentDialog';
import MeoConsentDialog from './MeoConsentDialog';
import { useMeoSession } from './session';
import { ChatMarkdownImage, ChatMarkdownTable } from './ChatRichContent';
import { tokenizeCode } from './codeHighlight.mjs';
import { MESSAGE_WINDOW_SIZE, transcriptWindow } from './transcriptWindow.mjs';
import { chatDraftKey, readChatDraft, writeChatDraft } from './chatDrafts.mjs';

type Connection = {
  id: string;
  provider: string;
  displayName: string;
  defaultModel: string;
  secretHint: string;
};
type Model = { id: string; name: string; description?: string };
type SkillPlugin = { id: string; name: string; enabled: boolean; skills: Array<{ id: string; name: string; description: string }> };
type Message = { role: 'user' | 'assistant'; content: string };
type Conversation = { id: string; title: string; createdAt: string; updatedAt: string };
type ApiConversation = {
  id: string;
  title?: string;
  createdAt?: string;
  updatedAt?: string;
  created_at?: string;
  updated_at?: string;
};
type ApiMessage = {
  role?: string;
  text?: string;
  content?: unknown;
};

function normalizeConversation(value: ApiConversation): Conversation {
  return {
    id: value.id,
    title: value.title ?? '',
    createdAt: value.createdAt ?? value.created_at ?? '',
    updatedAt: value.updatedAt ?? value.updated_at ?? '',
  };
}

function messageText(value: ApiMessage): string {
  if (typeof value.text === 'string') return value.text;
  if (typeof value.content === 'string') return value.content;
  if (!Array.isArray(value.content)) return '';
  return value.content
    .flatMap((part) => {
      if (!part || typeof part !== 'object' || Array.isArray(part)) return [];
      const block = part as Record<string, unknown>;
      return block.type === 'text' && typeof block.text === 'string' ? [block.text] : [];
    })
    .join('\n');
}

function requestError(value: unknown, status: number): string {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if (typeof record.error === 'string') return record.error;
    if (record.error && typeof record.error === 'object' && !Array.isArray(record.error)) {
      const nested = record.error as Record<string, unknown>;
      if (typeof nested.message === 'string') return nested.message;
      if (typeof nested.code === 'string') return nested.code;
    }
  }
  return `Request failed (${status})`;
}

function draftStorage(): Storage | null {
  try { return window.sessionStorage; } catch { return null; }
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body != null && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json');
  const response = await fetch(url, {
    ...init,
    credentials: 'same-origin',
    headers,
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(requestError(value, response.status));
  return value as T;
}

/** ReactMarkdown owns parsing and URL safety. Keep copied output plain text. */
function MarkdownCodeBlock({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const [wrapLines, setWrapLines] = useState(false);
  useEffect(() => { setCopied(false); setCopyFailed(false); }, [children]);
  const codeElement = isValidElement<{ className?: string; children?: ReactNode }>(children) ? children : null;
  const childClass = codeElement?.props.className ?? '';
  const language = childClass.match(/(?:^|\s)language-([\w+#.-]+)/)?.[1];
  const rawCode = codeElement?.props.children;
  const highlightedCode = useMemo(
    () => typeof rawCode === 'string' ? tokenizeCode(rawCode, language) : null,
    [rawCode, language],
  );

  const copyCode = async () => {
    const code = preRef.current?.textContent;
    if (!code) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setCopyFailed(false);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  };

  return (
    <div className="meo-chat-code-block">
      <div className="meo-chat-code-toolbar">
        <span>{language ?? t('meo_web_code')}</span>
        <div className="meo-chat-code-actions">
          <button type="button" onClick={() => setWrapLines((current) => !current)}
            aria-pressed={wrapLines} aria-label={t('meo_web_toggle_code_wrap')}>
            {wrapLines ? t('meo_web_code_no_wrap') : t('meo_web_code_wrap')}
          </button>
          <button type="button" onClick={copyCode} aria-label={t('meo_web_copy_code')}>
            {copied ? t('meo_web_copied') : t('meo_web_copy')}
          </button>
        </div>
      </div>
      {copyFailed && <span role="alert" className="meo-chat-copy-error">{t('meo_web_copy_failed')}</span>}
      <pre ref={preRef} className={wrapLines ? 'is-wrapped' : undefined}>
        {highlightedCode ? (
          <code className={childClass}>
            {highlightedCode.map((token, index) =>
              token.kind === 'plain'
                ? token.text
                : <span className={`meo-code-token-${token.kind}`} key={index}>{token.text}</span>,
            )}
          </code>
        ) : children}
      </pre>
    </div>
  );
}

function CopyMessageButton({ content, role = 'assistant' }: { content: string; role?: 'assistant' | 'user' }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  useEffect(() => { setCopied(false); setCopyFailed(false); }, [content]);

  const copyMessage = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setCopyFailed(false);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  };

  return (
    <div className="meo-chat-message-actions">
      <button className="meo-chat-copy-message" type="button" onClick={copyMessage}
        aria-label={t(role === 'user' ? 'meo_web_copy_user_message' : 'meo_web_copy_response')}
        title={t(role === 'user' ? 'meo_web_copy_user_message' : 'meo_web_copy_response')}>
        {copied ? t('meo_web_copied') : t('meo_web_copy')}
      </button>
      {copyFailed && <span role="alert" className="meo-chat-copy-error">{t('meo_web_copy_failed')}</span>}
    </div>
  );
}

const ChatMessage = memo(function ChatMessage({ message, waiting, onDelegateToWork }: {
  message: Message;
  waiting: boolean;
  onDelegateToWork: (text: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <article className={`meo-chat-message ${message.role === 'user' ? 'meo-chat-message-user' : 'meo-chat-message-assistant'}`}>
      {message.role === 'assistant' ? (
        message.content ? <>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={chatMarkdownComponents}>{message.content}</ReactMarkdown>
          <CopyMessageButton content={message.content} />
        </> : (waiting ? <ChatMessageWaiting /> : null)
      ) : (
        <>
          <p className="whitespace-pre-wrap">{message.content}</p>
          <CopyMessageButton content={message.content} role="user" />
          <button type="button" className="meo-chat-delegate-message"
            title={t('meo.work.delegateMessage')}
            onClick={() => onDelegateToWork(message.content)}>
            {t('meo.work.delegateMessage')}
          </button>
        </>
      )}
    </article>
  );
});

function ChatMessageWaiting() {
  const { t } = useTranslation();
  return <span className="meo-chat-streaming-indicator" role="status">{t('meo_web_thinking')}</span>;
}

const chatMarkdownComponents = {
  pre: MarkdownCodeBlock,
  table: ChatMarkdownTable,
  img: ChatMarkdownImage,
};

type MeoChatProps = {
  historyTarget: HTMLDivElement | null;
  newChatRequest: number;
  searchRequest: number;
  onBusyChange: (busy: boolean) => void;
  onSelectConversation: () => void;
  onDelegateToWork: (text: string, conversationId: string) => void;
  active: boolean;
};

export default function MeoChat({ historyTarget, newChatRequest, searchRequest, onBusyChange, onSelectConversation, onDelegateToWork, active }: MeoChatProps) {
  const preferences = useBrowserPreferences();
  const { t } = useTranslation();
  const { user } = useMeoSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedConnection = searchParams.get('connection') ?? '';
  const requestedModel = searchParams.get('model') ?? '';
  const selectedConversationKey = `meo-ai-web:selected:${user?.id ?? 'anonymous'}`;
  const [history, setHistory] = useState<Conversation[]>([]);
  const [historyQuery, setHistoryQuery] = useState('');
  const [activeConversationId, setActiveConversationId] = useState('');
  const draftKey = chatDraftKey(user?.id, activeConversationId);
  const [draftState, setDraftState] = useState(() => ({
    key: draftKey,
    text: readChatDraft(draftStorage(), user?.id, activeConversationId),
  }));
  const draft = draftState.key === draftKey
    ? draftState.text
    : readChatDraft(draftStorage(), user?.id, activeConversationId);
  const setDraft = (text: string) => {
    setDraftState({ key: draftKey, text });
    writeChatDraft(draftStorage(), user?.id, activeConversationId, text);
  };
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const historySearchRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<HTMLElement>(null);
  const followOutputRef = useRef(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const lastNewChatRequestRef = useRef(newChatRequest);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [credentialId, setCredentialId] = useState(requestedConnection);
  const [model, setModel] = useState(requestedModel);
  const modelRef = useRef(model);
  modelRef.current = model;
  const [models, setModels] = useState<Model[]>([]);
  const [modelDiscovery, setModelDiscovery] = useState<'idle' | 'unsupported' | 'ready'>('idle');
  const [skillPlugins, setSkillPlugins] = useState<SkillPlugin[]>([]);
  const [selectedSkillId, setSelectedSkillId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [windowState, setWindowState] = useState({ conversationId: '', count: MESSAGE_WINDOW_SIZE });
  const visibleCount = windowState.conversationId === activeConversationId ? windowState.count : MESSAGE_WINDOW_SIZE;
  const visibleRange = transcriptWindow(messages.length, visibleCount);
  const pendingOlderScrollRef = useRef<{ height: number; top: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [requestPhase, setRequestPhase] = useState<'idle' | 'preparing' | 'approval' | 'connecting' | 'streaming' | 'saving'>('idle');
  const [streamingActive, setStreamingActive] = useState(false);
  const [stopNotice, setStopNotice] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingConsent, setPendingConsent] = useState<MeoConsent | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const historyGenerationRef = useRef(0);
  const skipHistoryLoadRef = useRef('');
  const consentDecisionRef = useRef<((approved: boolean) => void) | null>(null);
  const filteredHistory = useMemo(() => history.filter((item) => item.title.toLocaleLowerCase().includes(historyQuery.trim().toLocaleLowerCase())), [history, historyQuery]);

  useEffect(() => onBusyChange(busy), [busy, onBusyChange]);

  useEffect(() => {
    if (!historyTarget || searchRequest === 0) return;
    // The sidebar and React portal may be created by the same navigation action.
    const frame = window.requestAnimationFrame(() => historySearchRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [historyTarget, searchRequest]);

  // Expand as the user types (including IME/paste) without growing beyond the viewport.
  useEffect(() => {
    const field = textareaRef.current;
    if (!field) return;
    field.style.height = 'auto';
    const idealHeight = field.scrollHeight;
    field.style.height = `${Math.min(Math.max(idealHeight, 43), 180)}px`;
    field.style.overflowY = idealHeight > 180 ? 'auto' : 'hidden';
  }, [draft]);

  // Stream follow only while the user is near the latest message.
  // Reading earlier content must not be interrupted by incoming tokens.
  useEffect(() => {
    if (!followOutputRef.current) return;
    const container = streamRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
      setShowScrollToBottom(false);
    }
  }, [messages]);

  useLayoutEffect(() => {
    const anchor = pendingOlderScrollRef.current;
    const container = streamRef.current;
    if (!anchor || !container) return;
    pendingOlderScrollRef.current = null;
    container.scrollTop = anchor.top + container.scrollHeight - anchor.height;
  }, [visibleCount, activeConversationId]);

  const showEarlierMessages = () => {
    const container = streamRef.current;
    if (container) pendingOlderScrollRef.current = { height: container.scrollHeight, top: container.scrollTop };
    followOutputRef.current = false;
    setWindowState({
      conversationId: activeConversationId,
      count: visibleCount + MESSAGE_WINDOW_SIZE,
    });
  };

  const goToLatest = () => {
    followOutputRef.current = true;
    const container = streamRef.current;
    if (container) container.scrollTop = container.scrollHeight;
    setShowScrollToBottom(false);
  };

  useEffect(
    () => () => {
      streamAbortRef.current?.abort();
      consentDecisionRef.current?.(false);
    },
    [user?.id],
  );

  const requestConsent = (consent: MeoConsent) =>
    new Promise<boolean>((resolve) => {
      consentDecisionRef.current = resolve;
      setPendingConsent(consent);
    });

  const resolveConsent = (approved: boolean) => {
    const resolve = consentDecisionRef.current;
    consentDecisionRef.current = null;
    setPendingConsent(null);
    resolve?.(approved);
  };

  const updateDeepLink = useCallback(
    (connection: string, selectedModel: string) => {
      const next = new URLSearchParams();
      if (connection) next.set('connection', connection);
      if (selectedModel) next.set('model', selectedModel);
      setSearchParams(next, { replace: true });
    },
    [setSearchParams],
  );

  useEffect(() => {
    if (!active) return;
    let live = true;
    json<{ plugins: SkillPlugin[] }>('/api/meo/ai/plugins')
      .then(({ plugins }) => {
        if (!live) return;
        const enabled = (plugins || []).filter((plugin) => plugin.enabled);
        setSkillPlugins(enabled);
        setSelectedSkillId((previous) =>
          previous && !enabled.some((plugin) => plugin.skills?.some((skill) => skill.id === previous))
            ? '' : previous,
        );
      })
      .catch(() => { if (live) setSkillPlugins([]); });
    return () => { live = false; };
  }, [active]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    json<{ credentials: Connection[] }>('/api/meo/connections')
      .then(({ credentials: result }) => {
        if (!active) return;
        setConnections(result);
        const requested = result.find((item) => item.id === requestedConnection);
        const selected = requested ?? result[0];
        if (!selected) {
          setCredentialId('');
          setModel('');
          return;
        }
        setCredentialId(selected.id);
        if (!requested && requestedConnection) {
          setError(t('meo_web_invalid_connection_fallback'));
          setModel(selected.defaultModel);
          updateDeepLink(selected.id, selected.defaultModel);
        } else if (!requestedModel) {
          setModel(selected.defaultModel);
        }
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [requestedConnection, requestedModel, t, updateDeepLink]);

  useEffect(() => {
    let active = true;
    historyGenerationRef.current += 1;
    setLoadingMore(false);
    setHistoryLoading(true);
    json<{ conversations: ApiConversation[]; nextCursor: string | null }>('/api/meo/conversations')
      .then(({ conversations: result, nextCursor }) => {
        if (!active) return;
        const normalized = result.map(normalizeConversation);
        setHistory(normalized);
        setHistoryCursor(nextCursor);
        const savedId = localStorage.getItem(selectedConversationKey) ?? '';
        const initial = normalized.find((item) => item.id === savedId) ?? normalized[0];
        setActiveConversationId(initial?.id ?? '');
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setHistoryLoading(false));
    return () => {
      active = false;
    };
  }, [selectedConversationKey]);

  useEffect(() => {
    if (!credentialId) {
      setModels([]);
      setModelDiscovery('idle');
      return;
    }
    let active = true;
    setModelDiscovery('idle');
    json<{ supported: boolean; models: Model[] }>(
      `/api/meo/connections/${encodeURIComponent(credentialId)}/models`,
    )
      .then((result) => {
        if (!active) return;
        setModels(result.models);
        setModelDiscovery(result.supported ? 'ready' : 'unsupported');
        if (result.supported && result.models.length > 0) {
          const found = result.models.find((item) => item.id === modelRef.current);
          const fallback =
            result.models.find(
              (item) => item.id === connections.find((c) => c.id === credentialId)?.defaultModel,
            ) ?? result.models[0];
          if (!found) {
            if (requestedModel) setError(t('meo_web_invalid_model_fallback'));
            setModel(fallback.id);
            updateDeepLink(credentialId, fallback.id);
          }
        } else if (!modelRef.current) {
          setModel(connections.find((item) => item.id === credentialId)?.defaultModel ?? '');
        }
      })
      .catch((reason: Error) => active && setError(reason.message));
    return () => {
      active = false;
    };
  }, [connections, credentialId, requestedModel, t, updateDeepLink]);

  useEffect(() => {
    let active = true;
    if (!activeConversationId) {
      setMessages([]);
      return () => {
        active = false;
      };
    }
    localStorage.setItem(selectedConversationKey, activeConversationId);
    if (skipHistoryLoadRef.current === activeConversationId) {
      skipHistoryLoadRef.current = '';
      return;
    }
    setMessages([]);
    json<{ messages: ApiMessage[] }>(
      `/api/meo/conversations/${encodeURIComponent(activeConversationId)}/messages`,
    )
      .then(({ messages: result }) => {
        if (!active) return;
        setMessages(
          result.flatMap((message) =>
            message.role === 'user' || message.role === 'assistant'
              ? [{ role: message.role, content: messageText(message) }]
              : [],
          ),
        );
      })
      .catch((reason: Error) => active && setError(reason.message));
    return () => {
      active = false;
    };
  }, [activeConversationId, selectedConversationKey]);

  const selected = useMemo(
    () => connections.find((item) => item.id === credentialId),
    [connections, credentialId],
  );
  const selectedModelInfo = useMemo(
    () => models.find((item) => item.id === model),
    [models, model],
  );

  const changeConnection = useCallback(
    (id: string) => {
      const nextModel = connections.find((item) => item.id === id)?.defaultModel ?? '';
      setCredentialId(id);
      setModel(nextModel);
      updateDeepLink(id, nextModel);
    },
    [connections, updateDeepLink],
  );

  const delegateToWork = useCallback(
    (text: string) => { if (!busy && text.trim()) onDelegateToWork(text, activeConversationId); },
    [busy, onDelegateToWork, activeConversationId],
  );

  const changeModel = (value: string) => {
    setModel(value);
    updateDeepLink(credentialId, value);
  };

  const startNewChat = () => {
    if (busy) return;
    followOutputRef.current = true;
    setShowScrollToBottom(false);
    // A new conversation starts empty, without clearing drafts of other chats.
    writeChatDraft(draftStorage(), user?.id, '', '');
    setDraftState({ key: chatDraftKey(user?.id, ''), text: '' });
    setWindowState({ conversationId: '', count: MESSAGE_WINDOW_SIZE });
    pendingOlderScrollRef.current = null;
    setActiveConversationId('');
    setMessages([]);
    setStopNotice(false);
    localStorage.removeItem(selectedConversationKey);
  };

  // The shell stays mounted while /new is selected, so navigation alone does not reset a chat.
  useEffect(() => {
    if (lastNewChatRequestRef.current === newChatRequest) return;
    lastNewChatRequestRef.current = newChatRequest;
    if (busy) return;
    startNewChat();
    textareaRef.current?.focus();
  }, [newChatRequest]);

  const openConversation = (conversation: Conversation) => {
    if (busy) return;
    setError('');
    setStopNotice(false);
    followOutputRef.current = true;
    setShowScrollToBottom(false);
    setWindowState({ conversationId: conversation.id, count: MESSAGE_WINDOW_SIZE });
    pendingOlderScrollRef.current = null;
    setActiveConversationId(conversation.id);
  };

  const loadMoreHistory = async () => {
    if (!historyCursor || loadingMore || busy) return;
    const generation = historyGenerationRef.current;
    setLoadingMore(true);
    try {
      const page = await json<{ conversations: ApiConversation[]; nextCursor: string | null }>(
        `/api/meo/conversations?cursor=${encodeURIComponent(historyCursor)}`,
      );
      if (generation !== historyGenerationRef.current) return;
      const normalized = page.conversations.map(normalizeConversation);
      setHistory((current) => {
        const existing = new Set(current.map((item) => item.id));
        return [...current, ...normalized.filter((item) => !existing.has(item.id))];
      });
      setHistoryCursor(page.nextCursor);
    } catch (reason) {
      if (generation === historyGenerationRef.current)
        setError(reason instanceof Error ? reason.message : t('meo_web_chat_failed'));
    } finally {
      if (generation === historyGenerationRef.current) setLoadingMore(false);
    }
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    const prompt = draft.trim();
    if (!prompt || busy || !credentialId || !model.trim()) return;
    setError('');
    setStopNotice(false);
    followOutputRef.current = true;
    setShowScrollToBottom(false);
    setBusy(true);
    setRequestPhase('preparing');
    const nextMessages: Message[] = [...messages, { role: 'user', content: prompt }];
    const contextConversationId = activeConversationId || null;
    try {
      const prepared = await json<{ consent: MeoConsent }>('/api/meo/chat/prepare', {
        method: 'POST',
        body: JSON.stringify({
          credentialId,
          model: model.trim(),
          conversationId: contextConversationId,
          prompt,
          ...(selectedSkillId ? { skillId: selectedSkillId } : {}),
        }),
      });
      const consent = prepared.consent;
      setRequestPhase('approval');
      const approved = await requestConsent(consent);
      if (!approved) return;
      setRequestPhase('connecting');

      const abortController = new AbortController();
      streamAbortRef.current = abortController;
      setStreamingActive(true);
      const response = await fetch('/api/meo/chat/stream', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({
          credentialId,
          model: model.trim(),
          conversationId: contextConversationId,
          prompt,
          ...(selectedSkillId ? { skillId: selectedSkillId } : {}),
          consent,
        }),
        signal: abortController.signal,
      });
      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => ({}));
        throw new Error(requestError(body, response.status));
      }

      let conversationId = activeConversationId;
      if (!conversationId) {
        const created = await json<{ conversation: ApiConversation }>('/api/meo/conversations', {
          method: 'POST',
          body: JSON.stringify({ title: prompt.slice(0, 80) }),
        });
        const normalized = normalizeConversation(created.conversation);
        conversationId = normalized.id;
        skipHistoryLoadRef.current = conversationId;
        setHistory((current) => [normalized, ...current]);
        setActiveConversationId(conversationId);
      }

      await json(`/api/meo/conversations/${encodeURIComponent(conversationId)}/messages`, {
        method: 'POST',
        body: JSON.stringify({ role: 'user', content: prompt }),
      });
      setMessages(nextMessages);
      setDraft('');
      setMessages((current) => [...current, { role: 'assistant', content: '' }]);
      setRequestPhase('streaming');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let assistantText = '';
      let completed = false;
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        let boundary = buffer.indexOf('\n\n');
        while (boundary >= 0) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const eventName = block.match(/^event:\s*(.+)$/m)?.[1]?.trim();
          const data = block.match(/^data:\s*(.+)$/m)?.[1];
          if (eventName === 'delta' && data) {
            const chunk = JSON.parse(data).text as string;
            assistantText += chunk;
            setMessages((current) =>
              current.map((message, index) =>
                index === current.length - 1 && message.role === 'assistant'
                  ? { ...message, content: message.content + chunk }
                  : message,
              ),
            );
          } else if (eventName === 'error' && data) {
            const failure = JSON.parse(data) as { message?: string };
            throw new Error(failure.message ?? t('meo_web_stream_failed'));
          } else if (eventName === 'done') {
            completed = true;
          }
          boundary = buffer.indexOf('\n\n');
        }
        if (done) break;
      }
      if (!completed) throw new Error(t('meo_web_stream_incomplete'));
      // The stream is finished; the Stop control must not claim to cancel persistence.
      setStreamingActive(false);
      setRequestPhase('saving');
      if (assistantText) {
        await json(`/api/meo/conversations/${encodeURIComponent(conversationId)}/messages`, {
          method: 'POST',
          body: JSON.stringify({ role: 'assistant', content: assistantText }),
        });
      }
      setHistory((current) => {
        const item = current.find((conversation) => conversation.id === conversationId);
        if (!item) return current;
        return [
          { ...item, updatedAt: new Date().toISOString() },
          ...current.filter((conversation) => conversation.id !== conversationId),
        ];
      });
    } catch (reason) {
      streamAbortRef.current?.abort();
      if (!(reason instanceof DOMException && reason.name === 'AbortError')) {
        setError(reason instanceof Error ? reason.message : t('meo_web_chat_failed'));
      }
    } finally {
      streamAbortRef.current = null;
      setStreamingActive(false);
      setRequestPhase('idle');
      setBusy(false);
    }
  }

  const stopReceiving = () => {
    if (!streamAbortRef.current) return;
    setStopNotice(true);
    streamAbortRef.current.abort();
  };

  // Export what the user can see. This is a browser-only download, not an
  // attempt to mutate server history or to include hidden tool payloads.
  const exportVisibleChat = () => {
    if (busy || messages.length === 0) return;
    try {
      const entries = messages.map((message) =>
        `## ${message.role === 'user' ? t('meo_web_role_user') : t('meo_web_role_assistant')}\n\n${message.content}`,
      ).join('\n\n---\n\n');
      const blob = new Blob([`# Meo AI\n\n${entries}\n`], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'meo-ai-conversation.md';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError(t('meo_web_export_failed'));
    }
  };

  return (
    <main className="meo-chat-root">
      <header className="meo-chat-toolbar">
        <div className="meo-chat-toolbar-label">{t('meo_web_connection')}</div>
        <div className="meo-chat-connection-controls">
          <select aria-label={t('meo_web_connection')} className="meo-chat-connection-select"
            value={credentialId} onChange={(event) => changeConnection(event.target.value)}
            disabled={loading || busy}>
            <option value="">{t('meo_web_choose_connection')}</option>
            {connections.map((item) => (
              <option key={item.id} value={item.id}>{item.displayName} · {item.provider}</option>
            ))}
          </select>
          {models.length > 0 && modelDiscovery === 'ready' ? (
            <select aria-label={t('meo_web_model')} className="meo-chat-model-select"
              aria-describedby={selectedModelInfo?.description ? 'meo-chat-model-description' : undefined}
              title={selectedModelInfo?.description}
              value={model} onChange={(event) => changeModel(event.target.value)} disabled={busy}>
              {models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          ) : (
            <input aria-label={t('meo_web_model_id')} className="meo-chat-model-select"
              value={model} onChange={(event) => changeModel(event.target.value)} disabled={busy}
              placeholder={t('meo_web_model_id')} />
          )}
          <select aria-label="Skill" title="Use a saved skill in this chat"
            className="meo-chat-model-select" value={selectedSkillId} disabled={busy}
            onChange={(event) => setSelectedSkillId(event.target.value)}>
            <option value="">No skill</option>
            {skillPlugins.filter((plugin) => plugin.skills?.length).map((plugin) => (
              <optgroup key={plugin.id} label={plugin.name}>
                {plugin.skills.map((skill) => <option key={skill.id} value={skill.id}>{skill.name}</option>)}
              </optgroup>
            ))}
          </select>
          <button type="button" className="meo-chat-export"
            onClick={exportVisibleChat} disabled={busy || messages.length === 0}
            title={t('meo_web_export_visible')}>
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M12 3v12m-4-4 4 4 4-4" /><path d="M4 17v3h16v-3" />
            </svg>
            <span>{t('meo_web_export')}</span>
          </button>
        </div>
      </header>
      {selectedModelInfo?.description && modelDiscovery === 'ready' && (
        <p id="meo-chat-model-description" className="meo-chat-model-description"
          title={selectedModelInfo.description}>{selectedModelInfo.description}</p>
      )}
      {modelDiscovery === 'unsupported' && (
        <p className="text-text-secondary text-sm">{t('meo_web_model_manual_fallback')}</p>
      )}
      {historyTarget && createPortal(
        <div className="meo-chat-history-panel">
          <label className="meo-chat-history-search">
            <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></svg>
            <input ref={historySearchRef} type="search" value={historyQuery}
              onChange={(event) => setHistoryQuery(event.target.value)}
              placeholder={t('meo_web_search_history')} aria-label={t('meo_web_search_history')}
              aria-keyshortcuts="Control+K Meta+K"
              title={t('meo_web_search_shortcut')} />
          </label>
          <span className="meo-desktop-section-label">{t('meo_web_recent')}</span>
          <nav aria-label={t('meo_web_history')} className="meo-chat-history-items">
            {historyLoading && <p role="status" className="meo-chat-history-muted">{t('meo_web_loading_more')}</p>}
            {!historyLoading && history.length === 0 && <p className="meo-chat-history-muted">{t('meo_web_no_history')}</p>}
            {!historyLoading && history.length > 0 && filteredHistory.length === 0 && <p className="meo-chat-history-muted">{t('meo_web_no_history_matches')}</p>}
            {filteredHistory.map((conversation) => (
              <button key={conversation.id} type="button"
                className={`meo-chat-history-item ${conversation.id === activeConversationId ? 'is-active' : ''}`}
                aria-current={conversation.id === activeConversationId ? 'page' : undefined}
                title={conversation.title || t('meo_web_untitled_chat')}
                onClick={() => { openConversation(conversation); if (!busy) onSelectConversation(); }}
                disabled={busy}>
                {conversation.title || t('meo_web_untitled_chat')}
              </button>
            ))}
            {historyCursor && <button type="button" className="meo-chat-history-more"
              onClick={loadMoreHistory} disabled={busy || loadingMore}>
              {loadingMore ? t('meo_web_loading_more') : t('meo_web_load_more')}
            </button>}
          </nav>
        </div>,
        historyTarget,
      )}
      <div className="meo-chat-stream-shell">
      <section
        ref={streamRef}
        aria-label={t('meo_web_conversation')}
        className={`meo-chat-stream ${messages.length === 0 ? 'is-empty' : ''}`}
        onScroll={(event) => {
          const element = event.currentTarget;
          const away = element.scrollHeight - element.scrollTop - element.clientHeight > 120;
          followOutputRef.current = !away;
          setShowScrollToBottom(away);
        }}
      >
        {(loading || historyLoading) && <p>{t('meo_web_loading')}</p>}
        {!loading && connections.length === 0 && <p className="meo-chat-connection-warning">{t('meo_web_no_connections')}</p>}
        {!loading && !historyLoading && !busy && messages.length === 0 && (
          <div className="meo-chat-welcome">
            <h1>{t('meo_web_welcome_title')}</h1>
            <p>{t('meo_web_welcome_subtitle')}</p>
            <div className="meo-chat-suggestions">
              {(['explain', 'plan', 'code'] as const).map((suggestion) => (
                <button key={suggestion} type="button" disabled={!selected}
                  onClick={() => {
                    setDraft(t(`meo_web_suggestion_${suggestion}_prompt`));
                    textareaRef.current?.focus();
                  }}>
                  {t(`meo_web_suggestion_${suggestion}`)}
                </button>
              ))}
            </div>
          </div>
        )}
        {visibleRange.remaining > 0 && (
          <button className="meo-chat-show-earlier" type="button" onClick={showEarlierMessages}>
            {t('meo_web_show_earlier_messages', {
              count: Math.min(MESSAGE_WINDOW_SIZE, visibleRange.remaining),
              remaining: visibleRange.remaining,
            })}
          </button>
        )}
        {messages.slice(visibleRange.start).map((message, index) => (
          <ChatMessage key={`${visibleRange.start + index}-${message.role}`}
            message={message}
            waiting={busy && visibleRange.start + index === messages.length - 1 && message.role === 'assistant'}
            onDelegateToWork={delegateToWork} />
        ))}
        {stopNotice && <p role="status" className="meo-chat-stop-notice">{t('meo_web_stop_notice')}</p>}
        {error && (
          <p role="alert" className="text-status-error-strong text-sm">
            {error}
          </p>
        )}
      </section>
      {showScrollToBottom && (
        <button type="button" className="meo-chat-scroll-latest"
          aria-label={t('meo_web_scroll_latest')} title={t('meo_web_scroll_latest')}
          onClick={goToLatest}>
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 4v15m-6-6 6 6 6-6" />
          </svg>
        </button>
      )}
      </div>
      {pendingConsent && <MeoConsentDialog consent={pendingConsent} onResolve={resolveConsent} />}
      <div className="meo-chat-run-status" role="status" aria-live="polite" aria-atomic="true">
        {requestPhase !== 'idle' && (
          <>
            <span className="meo-chat-run-status-dot" aria-hidden="true" />
            {t(`meo_web_phase_${requestPhase}`)}
          </>
        )}
      </div>
      <form
        onSubmit={submit}
        className="meo-chat-composer"
      >
        <textarea
          ref={textareaRef}
          rows={1}
          className="meo-chat-textarea"
          value={draft}
          onKeyDown={(event) => {
            if(event.nativeEvent.isComposing || event.keyCode === 229 || event.key !== 'Enter' || event.shiftKey || event.repeat) return;
            const send = preferences.general.enter_to_send ? !event.ctrlKey && !event.metaKey : event.ctrlKey || event.metaKey;
            if(send) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
          }}
          maxLength={35000}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t('meo_web_message_placeholder')}
          aria-label={t('meo_web_message')}
          aria-describedby="meo-chat-input-hint"
          disabled={busy || !selected}
        />
        <button className="meo-chat-delegate-draft" type="button"
          onClick={() => delegateToWork(draft)} disabled={busy || !draft.trim()}
          aria-label={t('meo.work.delegateDraft')} title={t('meo.work.delegateDraft')}>
          {t('meo.nav.work')}
        </button>
        {streamingActive ? (
          <button className="meo-chat-send is-stop" type="button" onClick={stopReceiving} aria-label={t('meo_web_stop_receiving')} title={t('meo_web_stop_receiving')}>
            <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>
          </button>
        ) : (
        <button
          className="meo-chat-send"
          type="submit"
          aria-label={busy ? t('meo_web_thinking') : t('meo_web_send')}
          title={busy ? t('meo_web_thinking') : t('meo_web_send')}
          disabled={busy || !draft.trim() || !selected || !model.trim()}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
        </button>
        )}
      </form>
      <p className="meo-chat-composer-hint" id="meo-chat-input-hint">
        {t(preferences.general.enter_to_send ? 'meo_web_enter_to_send_hint' : 'meo_web_ctrl_enter_to_send_hint')}
      </p>
    </main>
  );
}
