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
            <p className="eyebrow">News feed</p>
            <h3>Market context and gold headlines.</h3>
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
        {articles.map((article) => (
          <article key={article.id} className="article-card">
            <div className="article-card__meta">
              <span className="badge">{article.is_featured ? 'featured' : 'news'}</span>
              {article.source_name ? <span>{article.source_name}</span> : null}
              {article.published_at ? <span>{formatDateTime(article.published_at)}</span> : null}
            </div>
            <h3 className="article-card__title">{article.title}</h3>
            <p className="article-card__body">{article.summary ?? article.content ?? 'No summary available.'}</p>
            {article.source_url ? (
              <a className="button button--ghost" href={article.source_url} target="_blank" rel="noreferrer">
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
