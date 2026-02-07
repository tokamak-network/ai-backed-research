"""Academic and web source retrieval for real citations.

Searches OpenAlex, arXiv, Semantic Scholar, and Brave to gather
real references before manuscript writing. Key-less APIs (OpenAlex, arXiv)
work immediately; key-gated APIs activate when env vars are set.
"""

import asyncio
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp

from ..models.collaborative_research import Reference


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

@dataclass
class _RateLimiter:
    """Token-bucket style per-API rate limiter."""

    interval: float  # minimum seconds between requests
    _last: float = field(default=0.0, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def wait(self):
        async with self._lock:
            now = time.monotonic()
            delay = self.interval - (now - self._last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


# ---------------------------------------------------------------------------
# In-memory cache with TTL
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    data: List[Reference]
    expires: float


class _TTLCache:
    """Simple in-memory cache with per-key TTL."""

    def __init__(self, ttl: float = 1800.0):  # 30 min default
        self._store: Dict[str, _CacheEntry] = {}
        self._ttl = ttl

    def get(self, key: str) -> Optional[List[Reference]]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires:
            del self._store[key]
            return None
        return entry.data

    def put(self, key: str, data: List[Reference]):
        self._store[key] = _CacheEntry(data=data, expires=time.monotonic() + self._ttl)


# ---------------------------------------------------------------------------
# SourceRetriever
# ---------------------------------------------------------------------------

class SourceRetriever:
    """Searches academic databases and the web for real references.

    Key-less APIs (OpenAlex, arXiv) always work.
    Key-gated APIs activate automatically when env vars are set:
      - SEMANTIC_SCHOLAR_API_KEY
      - BRAVE_API_KEY
    """

    _HEADERS = {
        "User-Agent": "AutonomousResearchPress/1.0 (research bot)",
        "Accept-Encoding": "gzip, deflate",
    }

    def __init__(self):
        self._cache = _TTLCache()
        self._limiters = {
            "openalex": _RateLimiter(interval=0.1),     # 10 req/s
            "arxiv": _RateLimiter(interval=3.0),         # 1 req/3s (arxiv ToS)
            "semantic_scholar": _RateLimiter(interval=1.0),  # 1 req/s
            "brave": _RateLimiter(interval=1.0),         # 1 req/s
        }

    # ------------------------------------------------------------------
    # OpenAlex  (free, no key)
    # ------------------------------------------------------------------

    async def search_openalex(self, query: str, max_results: int = 5) -> List[Reference]:
        cache_key = f"openalex:{query}:{max_results}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        await self._limiters["openalex"].wait()

        url = "https://api.openalex.org/works"
        params = {
            "search": query,
            "per_page": max_results,
            "sort": "relevance_score:desc",
            "select": "id,title,authorships,primary_location,publication_year,doi",
        }

        refs: List[Reference] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=self._HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return refs
                    data = await resp.json()

            for i, work in enumerate(data.get("results", []), start=1):
                authors = []
                for authorship in work.get("authorships", [])[:5]:
                    name = authorship.get("author", {}).get("display_name")
                    if name:
                        authors.append(name)

                venue = ""
                loc = work.get("primary_location") or {}
                source = loc.get("source") or {}
                venue = source.get("display_name", "")

                doi_raw = work.get("doi") or ""
                doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

                refs.append(Reference(
                    id=0,  # assigned later during dedup
                    authors=authors or ["Unknown"],
                    title=work.get("title") or "Untitled",
                    venue=venue or "OpenAlex",
                    year=work.get("publication_year") or 0,
                    url=doi_raw or None,
                    doi=doi,
                    summary="",
                ))
        except Exception:
            pass

        self._cache.put(cache_key, refs)
        return refs

    # ------------------------------------------------------------------
    # arXiv  (free, no key)
    # ------------------------------------------------------------------

    async def search_arxiv(self, query: str, max_results: int = 5) -> List[Reference]:
        cache_key = f"arxiv:{query}:{max_results}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        await self._limiters["arxiv"].wait()

        url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        refs: List[Reference] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=self._HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return refs
                    text = await resp.text()

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(text)

            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else "Untitled"

                authors = []
                for author_el in entry.findall("atom:author", ns):
                    name_el = author_el.find("atom:name", ns)
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                published = entry.find("atom:published", ns)
                year = 0
                if published is not None and published.text:
                    year = int(published.text[:4])

                link_el = entry.find("atom:id", ns)
                arxiv_url = link_el.text.strip() if link_el is not None and link_el.text else None

                # Extract arXiv ID for DOI-like reference
                arxiv_id = None
                if arxiv_url:
                    match = re.search(r"(\d{4}\.\d{4,5})", arxiv_url)
                    if match:
                        arxiv_id = match.group(1)

                refs.append(Reference(
                    id=0,
                    authors=authors or ["Unknown"],
                    title=title,
                    venue="arXiv",
                    year=year,
                    url=arxiv_url,
                    doi=f"arXiv:{arxiv_id}" if arxiv_id else None,
                    summary="",
                ))
        except Exception:
            pass

        self._cache.put(cache_key, refs)
        return refs

    # ------------------------------------------------------------------
    # Semantic Scholar  (key optional, higher rate limit with key)
    # ------------------------------------------------------------------

    async def search_semantic_scholar(self, query: str, max_results: int = 5) -> List[Reference]:
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        if not api_key:
            return []

        cache_key = f"ss:{query}:{max_results}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        await self._limiters["semantic_scholar"].wait()

        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,year,venue,externalIds,url",
        }
        headers = {**self._HEADERS, "x-api-key": api_key}

        refs: List[Reference] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return refs
                    data = await resp.json()

            for paper in data.get("data", []):
                authors = [a.get("name", "Unknown") for a in paper.get("authors", [])[:5]]
                ext_ids = paper.get("externalIds") or {}
                doi = ext_ids.get("DOI")

                refs.append(Reference(
                    id=0,
                    authors=authors or ["Unknown"],
                    title=paper.get("title") or "Untitled",
                    venue=paper.get("venue") or "Semantic Scholar",
                    year=paper.get("year") or 0,
                    url=paper.get("url"),
                    doi=doi,
                    summary="",
                ))
        except Exception:
            pass

        self._cache.put(cache_key, refs)
        return refs

    # ------------------------------------------------------------------
    # Brave Search  (key required, 2000 free/month)
    # ------------------------------------------------------------------

    async def search_brave(self, query: str, max_results: int = 4) -> List[Reference]:
        api_key = os.environ.get("BRAVE_API_KEY")
        if not api_key:
            return []

        cache_key = f"brave:{query}:{max_results}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        await self._limiters["brave"].wait()

        url = "https://api.search.brave.com/res/v1/web/search"
        params = {"q": query, "count": max_results}
        headers = {
            **self._HEADERS,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }

        refs: List[Reference] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return refs
                    data = await resp.json()

            for result in data.get("web", {}).get("results", []):
                title = result.get("title", "Untitled")
                page_url = result.get("url", "")
                description = result.get("description", "")

                refs.append(Reference(
                    id=0,
                    authors=["Web Source"],
                    title=title,
                    venue=page_url.split("/")[2] if "/" in page_url else "Web",
                    year=0,
                    url=page_url,
                    doi=None,
                    summary=description[:200],
                ))
        except Exception:
            pass

        self._cache.put(cache_key, refs)
        return refs

    # ------------------------------------------------------------------
    # Unified search
    # ------------------------------------------------------------------

    async def search_all(
        self,
        topic: str,
        max_academic: int = 8,
        max_web: int = 4,
    ) -> List[Reference]:
        """Search all available sources, deduplicate, and assign IDs.

        Args:
            topic: Research topic string
            max_academic: Max academic results (split across sources)
            max_web: Max web results from Brave

        Returns:
            Deduplicated list of References with sequential IDs starting at 1
        """
        per_academic = max(2, max_academic // 3)  # split among up to 3 academic APIs

        # Launch all searches concurrently
        results = await asyncio.gather(
            self.search_openalex(topic, max_results=per_academic),
            self.search_arxiv(topic, max_results=per_academic),
            self.search_semantic_scholar(topic, max_results=per_academic),
            self.search_brave(topic, max_results=max_web),
            return_exceptions=True,
        )

        all_refs: List[Reference] = []
        for result in results:
            if isinstance(result, list):
                all_refs.extend(result)

        # Deduplicate by normalized title
        seen_titles: set = set()
        unique_refs: List[Reference] = []
        for ref in all_refs:
            norm = ref.title.lower().strip()
            if norm in seen_titles or norm == "untitled":
                continue
            seen_titles.add(norm)
            unique_refs.append(ref)

        # Assign sequential IDs
        for i, ref in enumerate(unique_refs, start=1):
            ref.id = i

        return unique_refs

    # ------------------------------------------------------------------
    # Formatting helper (for prompt injection)
    # ------------------------------------------------------------------

    @staticmethod
    def format_for_prompt(references: List[Reference]) -> str:
        """Format references into a text block suitable for LLM prompts.

        Example output:
          [1] Smith, Lee (2023). "Title". Venue. https://doi.org/10.xxx
          [2] ...
        """
        if not references:
            return ""

        lines = []
        for ref in references:
            authors = ", ".join(ref.authors[:3])
            if len(ref.authors) > 3:
                authors += " et al."

            line = f"[{ref.id}] {authors} ({ref.year}). \"{ref.title}\". {ref.venue}."
            if ref.doi and not ref.doi.startswith("arXiv:"):
                line += f" https://doi.org/{ref.doi}"
            elif ref.url:
                line += f" {ref.url}"
            lines.append(line)

        return "\n".join(lines)
