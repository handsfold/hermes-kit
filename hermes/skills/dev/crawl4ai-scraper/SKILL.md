---
name: crawl4ai-scraper
description: "Scraper un site (JS, anti-bot, crawl) : Crawl4AI. Scraper web avancé avec Crawl4AI : sites JS, anti-bot, extraction CSS, crawling multi-pages. Utilise le MCP natif Hermes ou l'API Python directe."
when_to_use: "USER dit « scrape ce site », « extrais toutes les pages », « crawle ». Pas pour une page à lire une fois (voir recherche-profonde)."
version: 1.0.0
---

# Crawl4AI - Scraper Web Avancé

**Stack** : Crawl4AI 0.9.2 + Playwright (Chromium headless) + MCP natif Hermes.
**Machine** : hote-1 (Python 3.11, venv Hermes).
**Localisation** : pip dans `$HOME/.hermes/hermes-agent/venv`, config MCP dans `~/.hermes/config.yaml`.

## Utilisation depuis Hermes (MCP)

Après redémarrage du gateway, 4 outils MCP sont disponibles dans toutes les conversations :

| Outil MCP | Usage |
|---|---|
| `mcp_crawl4ai_crawl_webpage` | Scraper une page unique → markdown |
| `mcp_crawl4ai_crawl_website` | Crawler un site (profondeur + max pages) |
| `mcp_crawl4ai_extract_structured_data` | Extraction CSS ciblée |
| `mcp_crawl4ai_save_as_markdown` | Scraper + sauver en .md |

Paramètres clés :
- `crawl_webpage` : `url` (requis), `include_images` (défaut: true), `bypass_cache`, `force_deep_crawl`
- `crawl_website` : `url`, `max_depth` (défaut: 1), `max_pages` (défaut: 5), `include_images`
- `extract_structured_data` : `url`, `schema` (dict JSON), `css_selector` (défaut: "body")
- `save_as_markdown` : `url`, `filename`, `include_images`

## Utilisation directe (Python)

Pour les cas avancés (magic mode, stealth, JS wait) :

```python
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

async def scrape(url):
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        magic=True,              # Anti-bot
        simulate_user=True,      # Comportement humain
        override_navigator=True, # Masque l'automation
        page_timeout=30000
    )
    async with AsyncWebCrawler(verbose=False) as crawler:
        result = await crawler.arun(url=url, config=config)
        return result.markdown if result.success else None
```

## Extraction structurée (CSS)

```python
schema = {
    "name": "Articles",
    "baseSelector": "article",
    "fields": [
        {"name": "title", "selector": "h2", "type": "text"},
        {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"},
        {"name": "date", "selector": "time", "type": "text"}
    ]
}
config = CrawlerRunConfig(
    extraction_strategy=JsonCssExtractionStrategy(schema)
)
```

## Tests validés

- httpbin.org/html → markdown OK (17k chars)
- news.ycombinator.com → JS lourd OK
- bbc.com/news → site média OK (22k chars)

## Redémarrage après modif config

Ajouter/modifier un serveur MCP nécessite un restart du gateway :
```bash
systemctl --user restart hermes-gateway
```
Le reload ne suffit pas : les MCP sont découverts au démarrage.

## Dépendances installées

- `crawl4ai` 0.9.2
- `crawl4ai-mcp-server` 0.1.5 (expose 4 outils MCP)
- `mcp` (SDK Python)
- Playwright Chromium + Headless Shell (via `crawl4ai-setup`)
- Patchright (mode furtif)