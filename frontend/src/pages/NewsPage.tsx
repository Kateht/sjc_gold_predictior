import { type KeyboardEvent, useEffect, useRef, useState } from 'react';

import { fetchNewsArticleBySlug, fetchNewsArticles, fetchNewsCategories } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { NewsArticleRead, NewsCategoryRead } from '@/types';

export function NewsPage() {
  const [categories, setCategories] = useState<NewsCategoryRead[]>([]);
  const [articles, setArticles] = useState<NewsArticleRead[]>([]);
  const [activeCategory, setActiveCategory] = useState('all');
  const [featuredOnly, setFeaturedOnly] = useState(false);
  const [selectedArticleSlug, setSelectedArticleSlug] = useState<string | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<NewsArticleRead | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const detailRequestRef = useRef(0);
  const detailPanelRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let active = true;

    async function loadCategories() {
      try {
        const result = await fetchNewsCategories();
        if (active) {
          setCategories(result);
        }
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load categories');
        }
      }
    }

    void loadCategories();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadArticles() {
      setLoading(true);
      setError('');
      try {
        const result = await fetchNewsArticles(activeCategory === 'all' ? undefined : activeCategory, featuredOnly, 18);
        if (active) {
          setArticles(result);
        }
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load articles');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadArticles();
    return () => {
      active = false;
    };
  }, [activeCategory, featuredOnly]);

  useEffect(() => {
    detailRequestRef.current += 1;
    setSelectedArticleSlug(null);
    setSelectedArticle(null);
    setDetailLoading(false);
    setDetailError('');
  }, [activeCategory, featuredOnly]);

  async function handleArticleClick(article: NewsArticleRead) {
    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;

    setSelectedArticleSlug(article.slug);
    setSelectedArticle(article);
    setDetailLoading(true);
    setDetailError('');
    detailPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
      const result = await fetchNewsArticleBySlug(article.slug);
      if (detailRequestRef.current === requestId) {
        setSelectedArticle(result);
      }
    } catch (loadError) {
      if (detailRequestRef.current === requestId) {
        setDetailError(loadError instanceof Error ? loadError.message : 'Failed to load article details');
      }
    } finally {
      if (detailRequestRef.current === requestId) {
        setDetailLoading(false);
      }
    }
  }

  function handleArticleKeyDown(event: KeyboardEvent<HTMLElement>, article: NewsArticleRead) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    event.preventDefault();
    void handleArticleClick(article);
  }

  const detailSummary = selectedArticle?.summary?.trim() ?? '';
  const detailContent = selectedArticle?.content?.trim() || detailSummary || 'No details available.';
  const showDetailSummary = Boolean(detailSummary && detailSummary !== selectedArticle?.content?.trim());

  return (
    <div className="page stack">
      <section className="panel stack">
        <div className="section-title">
          <div>
            <p className="eyebrow">Live news feed</p>
            <h3>Market context and gold headlines from live sources.</h3>
            <p className="section-title__meta">Each card opens the original article so the page acts like a real news reader, not a static bulletin board.</p>
          </div>
          <label className="controls-row" style={{ alignItems: 'center' }}>
            <input type="checkbox" checked={featuredOnly} onChange={(event) => setFeaturedOnly(event.target.checked)} />
            <span>Featured only</span>
          </label>
        </div>

        <div className="tabs" style={{ flexWrap: 'wrap' }}>
          <button type="button" className={`tab ${activeCategory === 'all' ? 'is-active' : ''}`} onClick={() => setActiveCategory('all')}>
            All
          </button>
          {categories.map((category) => (
            <button key={category.slug} type="button" className={`tab ${activeCategory === category.slug ? 'is-active' : ''}`} onClick={() => setActiveCategory(category.slug)}>
              {category.name}
            </button>
          ))}
        </div>

        {error ? <div className="error-state">{error}</div> : null}
        {loading ? <div className="panel panel--compact">Loading articles...</div> : null}
      </section>

      <section ref={detailPanelRef} className="panel stack news-detail">
        <div className="section-title section-title--tight">
          <div>
            <p className="eyebrow">Article detail</p>
            <h3>{selectedArticle ? selectedArticle.title : 'Select an article to load its detail.'}</h3>
          </div>
          {selectedArticleSlug ? <span className={`badge ${detailLoading ? 'badge--neutral' : 'badge--positive'}`}>{detailLoading ? 'loading' : 'loaded'}</span> : null}
        </div>

        {detailError ? <div className="error-state">{detailError}</div> : null}
        {!selectedArticle && !detailLoading ? <div className="empty-state">Click any article card to view its details.</div> : null}

        {selectedArticle ? (
          <article className="news-detail__article">
            <div className="news-detail__meta">
              <span className="badge">{selectedArticle.is_featured ? 'featured' : 'news'}</span>
              <span>{selectedArticle.slug}</span>
              {selectedArticle.source_name ? <span>{selectedArticle.source_name}</span> : null}
              {selectedArticle.published_at ? <span>{formatDateTime(selectedArticle.published_at)}</span> : null}
            </div>

            {selectedArticle.image_url ? <img className="news-detail__image" src={selectedArticle.image_url} alt={selectedArticle.title} /> : null}
            {showDetailSummary ? <p className="news-detail__summary">{detailSummary}</p> : null}
            <div className="news-detail__body">{detailContent}</div>

            {selectedArticle.source_url ? (
              <div className="controls-row">
                <a className="button button--ghost" href={selectedArticle.source_url} target="_blank" rel="noreferrer">
                  Open source
                </a>
              </div>
            ) : null}
          </article>
        ) : null}
      </section>

      <section className="article-grid">
        {articles.map((article) => (
          <article
            key={article.id}
            className={`article-card ${selectedArticleSlug === article.slug ? 'is-active' : ''}`}
            role="button"
            tabIndex={0}
            aria-pressed={selectedArticleSlug === article.slug}
            onClick={() => void handleArticleClick(article)}
            onKeyDown={(event) => handleArticleKeyDown(event, article)}
          >
            <div className="article-card__meta">
              <span className="badge">{article.is_featured ? 'featured' : 'news'}</span>
              {article.source_name ? <span>{article.source_name}</span> : null}
              {article.published_at ? <span>{formatDateTime(article.published_at)}</span> : null}
            </div>
            <h3 className="article-card__title">{article.title}</h3>
            <p className="article-card__body">{article.summary ?? article.content ?? 'No summary available.'}</p>
            {article.source_url ? (
              <a
                className="button button--ghost"
                href={article.source_url}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              >
                Open source
              </a>
            ) : null}
          </article>
        ))}
        {!articles.length && !loading ? <div className="empty-state">No articles found for the selected filters.</div> : null}
      </section>
    </div>
  );
}
