"""
Exa API client for event discovery.

Provides async methods to search the web and fetch content via Exa's
Search API and Websets API.
"""

import logging
import os
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ExaSearchResult(BaseModel):
    """Parsed search result from Exa API."""

    id: str
    title: str
    url: str
    score: float | None = None
    published_date: datetime | None = None
    author: str | None = None
    text: str | None = None
    highlights: list[str] | None = None


class ExaWebset(BaseModel):
    """Webset status from Exa API."""

    id: str
    status: str  # "running", "completed", "failed"
    num_results: int | None = None
    results: list[ExaSearchResult] | None = None


class ExaClient:
    """Async client for Exa API (Search + Websets)."""

    BASE_URL = "https://api.exa.ai"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(
        self,
        query: str,
        num_results: int = 10,
        include_text: bool = True,
        include_highlights: bool = True,
        start_published_date: datetime | None = None,
        end_published_date: datetime | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[ExaSearchResult]:
        """
        Search the web using Exa's neural search.

        Args:
            query: Search query (natural language)
            num_results: Number of results to return
            include_text: Include full text content
            include_highlights: Include relevant text highlights
            start_published_date: Filter results published after this date
            end_published_date: Filter results published before this date
            include_domains: Only include results from these domains
            exclude_domains: Exclude results from these domains

        Returns:
            List of ExaSearchResult objects
        """
        if not self.api_key:
            logger.warning("EXA_API_KEY not set, returning empty results")
            return []

        client = await self._get_client()

        payload: dict[str, Any] = {
            "query": query,
            "numResults": num_results,
            "contents": {},
        }

        if include_text:
            payload["contents"]["text"] = True
        if include_highlights:
            payload["contents"]["highlights"] = True

        if start_published_date:
            payload["startPublishedDate"] = start_published_date.strftime("%Y-%m-%d")
        if end_published_date:
            payload["endPublishedDate"] = end_published_date.strftime("%Y-%m-%d")

        if include_domains:
            payload["includeDomains"] = include_domains
        if exclude_domains:
            payload["excludeDomains"] = exclude_domains

        try:
            response = await client.post("/search", json=payload)
            response.raise_for_status()
            data = response.json()

            results = []
            for result_data in data.get("results", []):
                result = self._parse_search_result(result_data)
                if result:
                    results.append(result)

            return results

        except httpx.HTTPError as e:
            logger.warning("Exa search API error: %s", e)
            return []

    async def find_similar(
        self,
        url: str,
        num_results: int = 10,
        include_text: bool = True,
        exclude_source_domain: bool = True,
    ) -> list[ExaSearchResult]:
        """
        Find pages similar to a given URL.

        Args:
            url: URL to find similar pages for
            num_results: Number of results to return
            include_text: Include full text content
            exclude_source_domain: Exclude results from the source domain

        Returns:
            List of ExaSearchResult objects
        """
        if not self.api_key:
            return []

        client = await self._get_client()

        payload: dict[str, Any] = {
            "url": url,
            "numResults": num_results,
            "excludeSourceDomain": exclude_source_domain,
            "contents": {"text": include_text},
        }

        try:
            response = await client.post("/findSimilar", json=payload)
            response.raise_for_status()
            data = response.json()

            return [
                result
                for result_data in data.get("results", [])
                if (result := self._parse_search_result(result_data))
            ]

        except httpx.HTTPError as e:
            logger.warning("Exa findSimilar API error: %s", e)
            return []

    async def create_webset(
        self,
        query: str,
        count: int = 50,
        criteria: str | None = None,
    ) -> str | None:
        """
        Create a Webset for async deep discovery.

        Websets gather comprehensive results over time, useful for
        discovering many events matching specific criteria.

        Args:
            query: Natural language search query
            count: Target number of results to gather
            criteria: Additional filtering criteria

        Returns:
            Webset ID if created successfully, None otherwise
        """
        if not self.api_key:
            return None

        client = await self._get_client()

        payload: dict[str, Any] = {
            "query": query,
            "count": count,
        }

        if criteria:
            payload["criteria"] = criteria

        try:
            response = await client.post("/websets", json=payload)
            response.raise_for_status()
            data = response.json()

            return data.get("id")

        except httpx.HTTPError as e:
            logger.warning("Exa create webset error: %s", e)
            return None

    async def get_webset(self, webset_id: str) -> ExaWebset | None:
        """
        Get the status and results of a Webset.

        Args:
            webset_id: The Webset ID from create_webset()

        Returns:
            ExaWebset with status and results if available
        """
        if not self.api_key:
            return None

        client = await self._get_client()

        try:
            response = await client.get(f"/websets/{webset_id}")
            response.raise_for_status()
            data = response.json()

            results = None
            if data.get("results"):
                results = [
                    result
                    for result_data in data["results"]
                    if (result := self._parse_search_result(result_data))
                ]

            return ExaWebset(
                id=data["id"],
                status=data.get("status", "unknown"),
                num_results=data.get("numResults"),
                results=results,
            )

        except httpx.HTTPError as e:
            logger.warning("Exa get webset error: %s", e)
            return None

    def _parse_search_result(self, data: dict[str, Any]) -> ExaSearchResult | None:
        """Parse raw Exa API response into ExaSearchResult."""
        try:
            published_date = None
            if data.get("publishedDate"):
                try:
                    published_date = datetime.fromisoformat(
                        data["publishedDate"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            return ExaSearchResult(
                id=data.get("id", data.get("url", "")),
                title=data.get("title", "Untitled"),
                url=data["url"],
                score=data.get("score"),
                published_date=published_date,
                author=data.get("author"),
                text=data.get("text"),
                highlights=data.get("highlights"),
            )

        except (KeyError, ValueError) as e:
            logger.warning("Error parsing Exa result: %s", e)
            return None


# Singleton instance
_client: ExaClient | None = None


def get_exa_client() -> ExaClient:
    """Get the singleton Exa client."""
    global _client
    if _client is None:
        _client = ExaClient()
    return _client
