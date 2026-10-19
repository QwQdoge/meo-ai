import { useState } from 'react';
import type { ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * Wide tables remain real semantic HTML tables. The wrapper scrolls independently
 * on small screens, and keyboard users can focus it to navigate large tables.
 */
export function ChatMarkdownTable({ node: _node, ...props }: ComponentProps<'table'> & { node?: unknown }) {
  const { t } = useTranslation();
  return (
    <div className="meo-chat-table-scroll" role="region" tabIndex={0}
      aria-label={t('meo_web_table_region')}>
      <table {...props} />
    </div>
  );
}

/**
 * Do not automatically fetch third-party image URLs embedded in AI output.
 * A model can supply arbitrary tracking URLs. Explicitly loading a preview
 * keeps the user's browser from silently contacting the image host.
 * ReactMarkdown's default URL sanitizer runs before these props are supplied.
 */
export function ChatMarkdownImage({ src, alt, title }: ComponentProps<'img'>) {
  const { t } = useTranslation();
  const [requested, setRequested] = useState(false);
  const [failed, setFailed] = useState(false);

  const validSource = typeof src === 'string' &&
    (/^https?:\/\//i.test(src) || src.startsWith('/'));
  if (!validSource) {
    return <span className="meo-chat-image-unavailable" role="note">
      {t('meo_web_image_unavailable')}
    </span>;
  }

  const caption = alt || title || t('meo_web_image');
  return (
    <span className="meo-chat-image-figure" role="group" aria-label={caption}>
      {!requested && (
        <button type="button" className="meo-chat-image-load"
          onClick={() => setRequested(true)}
          aria-label={t('meo_web_load_image_named', { name: caption })}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none"
            stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <rect x="3" y="4" width="18" height="16" rx="3" />
            <circle cx="8.5" cy="9" r="1.5" />
            <path d="m4 17 5-5 3 3 3-4 5 6" />
          </svg>
          <span>{t('meo_web_load_image')}</span>
          <small>{t('meo_web_external_image_notice')}</small>
        </button>
      )}
      {requested && (failed ? (
        <span className="meo-chat-image-unavailable" role="status">
          {t('meo_web_image_failed')}
          <button type="button" onClick={() => { setFailed(false); setRequested(false); }}>
            {t('meo_web_retry_image')}
          </button>
        </span>
      ) : (
        <a href={src} target="_blank" rel="noopener noreferrer"
          title={t('meo_web_open_image')}>
          <img src={src} alt={alt || ''} title={title} loading="lazy"
            decoding="async" referrerPolicy="no-referrer"
            onError={() => setFailed(true)} />
        </a>
      ))}
      <span className="meo-chat-image-caption">{caption}</span>
    </span>
  );
}
