"""Tests for the Alpha Vantage news adapter."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import NewsArticle
from src.data.adapters.news_adapter import NewsAdapter


def _make_settings():
    settings = MagicMock()
    settings.alpha_vantage_api_key = "test_key"
    settings.data.alpha_vantage.rate_limit_per_minute = 5
    settings.data.alpha_vantage.cache_ttl_hours = 24
    return settings


def _make_av_feed_item(
    symbol: str = "AAPL",
    title: str = "Test Article",
    source: str = "Reuters",
    time_published: str = "20260101T120000",
    url: str = "https://example.com/article",
    summary: str = "Test summary",
    overall_sentiment_score: float = 0.3,
    ticker_sentiment_score: float | None = None,
) -> dict:
    item = {
        "title": title,
        "source": source,
        "time_published": time_published,
        "url": url,
        "summary": summary,
        "overall_sentiment_score": str(overall_sentiment_score),
        "ticker_sentiment": [],
    }
    if ticker_sentiment_score is not None:
        item["ticker_sentiment"] = [
            {"ticker": symbol, "ticker_sentiment_score": str(ticker_sentiment_score)}
        ]
    return item


class TestParseArticles:
    """Test _parse_articles without network calls."""

    def test_parse_single_article(self):
        adapter = NewsAdapter(settings=_make_settings())
        data = {"feed": [_make_av_feed_item("AAPL")]}

        articles = adapter._parse_articles("AAPL", data)

        assert len(articles) == 1
        a = articles[0]
        assert a.symbol == "AAPL"
        assert a.title == "Test Article"
        assert a.source == "Reuters"
        assert a.url == "https://example.com/article"
        assert a.summary == "Test summary"
        assert isinstance(a.published_at, datetime)

    def test_ticker_sentiment_takes_priority(self):
        adapter = NewsAdapter(settings=_make_settings())
        item = _make_av_feed_item(
            "AAPL",
            overall_sentiment_score=0.1,
            ticker_sentiment_score=0.8,
        )
        data = {"feed": [item]}

        articles = adapter._parse_articles("AAPL", data)

        assert articles[0].sentiment == pytest.approx(0.8)

    def test_falls_back_to_overall_sentiment(self):
        adapter = NewsAdapter(settings=_make_settings())
        item = _make_av_feed_item("AAPL", overall_sentiment_score=0.5)
        data = {"feed": [item]}

        articles = adapter._parse_articles("AAPL", data)

        assert articles[0].sentiment == pytest.approx(0.5)

    def test_empty_feed_returns_empty(self):
        adapter = NewsAdapter(settings=_make_settings())
        articles = adapter._parse_articles("AAPL", {"feed": []})
        assert articles == []

    def test_missing_feed_key_returns_empty(self):
        adapter = NewsAdapter(settings=_make_settings())
        articles = adapter._parse_articles("AAPL", {})
        assert articles == []

    def test_bad_timestamp_uses_now(self):
        adapter = NewsAdapter(settings=_make_settings())
        item = _make_av_feed_item("AAPL")
        item["time_published"] = "invalid_timestamp"
        data = {"feed": [item]}

        articles = adapter._parse_articles("AAPL", data)

        assert len(articles) == 1
        assert articles[0].published_at.tzinfo is not None

    def test_malformed_item_skipped(self):
        adapter = NewsAdapter(settings=_make_settings())
        good = _make_av_feed_item("AAPL")
        data = {"feed": [{"bad": "data", "ticker_sentiment": []}, good]}

        # Should parse what it can, skip malformed
        articles = adapter._parse_articles("AAPL", data)
        assert len(articles) >= 1

    def test_multiple_articles_parsed(self):
        adapter = NewsAdapter(settings=_make_settings())
        items = [
            _make_av_feed_item("AAPL", title=f"Article {i}", time_published=f"2026010{i+1}T120000")
            for i in range(3)
        ]
        data = {"feed": items}

        articles = adapter._parse_articles("AAPL", data)

        assert len(articles) == 3

    def test_ticker_sentiment_case_insensitive(self):
        adapter = NewsAdapter(settings=_make_settings())
        item = _make_av_feed_item("AAPL", overall_sentiment_score=0.1)
        item["ticker_sentiment"] = [{"ticker": "aapl", "ticker_sentiment_score": "0.75"}]
        data = {"feed": [item]}

        articles = adapter._parse_articles("AAPL", data)

        assert articles[0].sentiment == pytest.approx(0.75)


class TestGetNews:
    """Test get_news with mocked Redis and HTTP."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        adapter = NewsAdapter(settings=_make_settings())
        cached_article = NewsArticle(
            symbol="AAPL",
            title="Cached",
            source="Reuters",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            url="https://example.com",
            summary="cached",
            sentiment=0.3,
        )
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps([cached_article.model_dump(mode="json")])

        with patch("src.data.adapters.news_adapter.get_redis", return_value=mock_redis):
            results = await adapter.get_news("AAPL")

        assert len(results) == 1
        assert results[0].title == "Cached"

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self):
        adapter = NewsAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session.closed = False

        with patch("src.data.adapters.news_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_get_session", return_value=mock_session), \
             patch.object(adapter._rate_limiter, "acquire", new_callable=AsyncMock):
            results = await adapter.get_news("AAPL")

        assert results == []

    @pytest.mark.asyncio
    async def test_api_error_message_returns_empty(self):
        adapter = NewsAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"Error Message": "Invalid API key"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session.closed = False

        with patch("src.data.adapters.news_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_get_session", return_value=mock_session), \
             patch.object(adapter._rate_limiter, "acquire", new_callable=AsyncMock):
            results = await adapter.get_news("AAPL")

        assert results == []

    @pytest.mark.asyncio
    async def test_rate_limit_note_returns_empty(self):
        adapter = NewsAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"Note": "API call frequency exceeded"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session.closed = False

        with patch("src.data.adapters.news_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_get_session", return_value=mock_session), \
             patch.object(adapter._rate_limiter, "acquire", new_callable=AsyncMock):
            results = await adapter.get_news("AAPL")

        assert results == []

    @pytest.mark.asyncio
    async def test_successful_fetch_stores_cache(self):
        adapter = NewsAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        feed_item = _make_av_feed_item("AAPL", ticker_sentiment_score=0.4)
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"feed": [feed_item]}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session.closed = False

        with patch("src.data.adapters.news_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_get_session", return_value=mock_session), \
             patch.object(adapter._rate_limiter, "acquire", new_callable=AsyncMock):
            results = await adapter.get_news("AAPL")

        assert len(results) == 1
        mock_redis.set.assert_called_once()
