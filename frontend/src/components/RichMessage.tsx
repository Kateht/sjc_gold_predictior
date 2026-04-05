import { useMemo } from 'react';

const ALLOWED_TAGS = new Set(['a', 'b', 'br', 'div', 'em', 'i', 'li', 'ol', 'p', 'span', 'strong', 'ul']);
const ALLOWED_STYLE_PROPS = new Set(['color', 'font-size', 'font-weight', 'text-decoration']);

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizePlainText(value: string): string {
  return escapeHtml(value).replace(/\n/g, '<br />');
}

function sanitizeStyle(value: string): string {
  return value
    .split(';')
    .map((rule) => rule.trim())
    .filter(Boolean)
    .map((rule) => {
      const [rawProperty, ...rawValueParts] = rule.split(':');
      const property = rawProperty?.trim().toLowerCase();
      const nextValue = rawValueParts.join(':').trim();
      if (!property || !nextValue || !ALLOWED_STYLE_PROPS.has(property)) {
        return '';
      }
      return `${property}: ${nextValue}`;
    })
    .filter(Boolean)
    .join('; ');
}

function sanitizeHref(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  try {
    const url = new URL(trimmed, window.location.origin);
    if (['http:', 'https:', 'mailto:', 'tel:'].includes(url.protocol)) {
      return url.toString();
    }
  } catch {
    return null;
  }

  return null;
}

function sanitizeNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return escapeHtml(node.textContent ?? '');
  }

  if (!(node instanceof HTMLElement)) {
    return '';
  }

  const tagName = node.tagName.toLowerCase();
  const childContent = Array.from(node.childNodes).map(sanitizeNode).join('');

  if (!ALLOWED_TAGS.has(tagName)) {
    return childContent;
  }

  const attributes: string[] = [];
  const style = sanitizeStyle(node.getAttribute('style') ?? '');
  if (style) {
    attributes.push(`style="${escapeHtml(style)}"`);
  }

  if (tagName === 'a') {
    const href = sanitizeHref(node.getAttribute('href') ?? '');
    if (href) {
      attributes.push(`href="${escapeHtml(href)}"`);
      attributes.push('target="_blank"');
      attributes.push('rel="noreferrer"');
    }
  }

  if (tagName === 'br') {
    return '<br />';
  }

  const attributeText = attributes.length ? ` ${attributes.join(' ')}` : '';
  return `<${tagName}${attributeText}>${childContent}</${tagName}>`;
}

function sanitizeHtml(value: string): string {
  if (typeof window === 'undefined' || typeof DOMParser === 'undefined') {
    return normalizePlainText(value);
  }

  const parser = new DOMParser();
  const document = parser.parseFromString(value, 'text/html');
  const sanitized = Array.from(document.body.childNodes).map(sanitizeNode).join('').trim();
  return sanitized || normalizePlainText(value);
}

type RichMessageProps = {
  content: string;
  className?: string;
};

export function RichMessage({ content, className = 'rich-message' }: RichMessageProps) {
  const html = useMemo(() => sanitizeHtml(content), [content]);

  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
