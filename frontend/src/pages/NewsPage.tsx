import { useEffect, useState } from 'react';

import { fetchNewsArticles, fetchNewsCategories } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { NewsArticleRead, NewsCategoryRead } from '@/types';

export function NewsPage() {
  const [categories, setCategories] = useState<NewsCategoryRead[]>([]);
  const [articles, setArticles] = useState<NewsArticleRead[]>([]);
  const [activeCategory, setActiveCategory] = useState('all');
  const [featuredOnly, setFeaturedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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

      <section className="article-grid">
        {articles.map((article) => {
          if (article.source_url) {
            return (
              <a key={article.id} className="article-card article-card--link" href={article.source_url} target="_blank" rel="noreferrer">
              {article.image_url ? (
                <div className="article-card__media">
                  <img src={article.image_url} alt={article.title} loading="lazy" />
                </div>
              ) : null}
              <div className="article-card__meta">
                <span className="badge">{article.is_featured ? 'featured' : 'news'}</span>
                {article.source_name ? <span>{article.source_name}</span> : null}
                {article.published_at ? <span>{formatDateTime(article.published_at)}</span> : null}
              </div>
              <h3 className="article-card__title">{article.title}</h3>
              <p className="article-card__body">{article.summary ?? article.content ?? 'No summary available.'}</p>
              <div className="controls-row controls-row--space-between article-card__footer">
                <span className="article-card__hint">{article.source_url ? 'Open original article' : 'No source link available'}</span>
                <span className="button button--ghost">Read article</span>
              </div>
              </a>
            );
          }

          return (
            <article key={article.id} className="article-card">
              {article.image_url ? (
                <div className="article-card__media">
                  <img src={article.image_url} alt={article.title} loading="lazy" />
                </div>
              ) : null}
              <div className="article-card__meta">
                <span className="badge">{article.is_featured ? 'featured' : 'news'}</span>
                {article.source_name ? <span>{article.source_name}</span> : null}
                {article.published_at ? <span>{formatDateTime(article.published_at)}</span> : null}
              </div>
              <h3 className="article-card__title">{article.title}</h3>
              <p className="article-card__body">{article.summary ?? article.content ?? 'No summary available.'}</p>
            </article>
          );
        })}
        {!articles.length && !loading ? <div className="empty-state">No articles found for the selected filters.</div> : null}
      </section>
    </div>
  );
}
