from __future__ import annotations

from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class AlertChannel(str, Enum):
    LOG = "log"
    SLACK = "slack"
    TELEGRAM = "telegram"


class AlertManager:
    """Manages alert routing and delivery."""

    def __init__(self, channels: list[str] | None = None):
        self.channels = channels or ["log"]
        self._slack_webhook: str | None = None
        self._telegram_bot_token: str | None = None
        self._telegram_chat_id: str | None = None

    def configure_slack(self, webhook_url: str) -> None:
        self._slack_webhook = webhook_url
        if "slack" not in self.channels:
            self.channels.append("slack")

    def configure_telegram(self, bot_token: str, chat_id: str) -> None:
        self._telegram_bot_token = bot_token
        self._telegram_chat_id = chat_id
        if "telegram" not in self.channels:
            self.channels.append("telegram")

    async def send_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send alert to all configured channels."""
        alert_data = {
            "severity": severity.value,
            "title": title,
            "message": message,
            "metadata": metadata or {},
        }

        for channel in self.channels:
            try:
                if channel == "log":
                    await self._send_log(alert_data)
                elif channel == "slack" and self._slack_webhook:
                    await self._send_slack(alert_data)
                elif channel == "telegram" and self._telegram_bot_token:
                    await self._send_telegram(alert_data)
            except Exception as e:
                logger.error("Failed to send alert", channel=channel, error=str(e))

    async def _send_log(self, alert: dict) -> None:
        severity = alert["severity"]
        if severity == AlertSeverity.CRITICAL.value:
            logger.critical(alert["title"], message=alert["message"], **alert.get("metadata", {}))
        elif severity == AlertSeverity.WARNING.value:
            logger.warning(alert["title"], message=alert["message"], **alert.get("metadata", {}))
        else:
            logger.info(alert["title"], message=alert["message"], **alert.get("metadata", {}))

    async def _send_slack(self, alert: dict) -> None:
        import httpx

        severity_emoji = {
            AlertSeverity.CRITICAL.value: ":rotating_light:",
            AlertSeverity.WARNING.value: ":warning:",
            AlertSeverity.INFO.value: ":information_source:",
        }
        emoji = severity_emoji.get(alert["severity"], "")

        payload = {
            "text": f"{emoji} *[{alert['severity']}] {alert['title']}*\n{alert['message']}",
        }

        async with httpx.AsyncClient() as client:
            await client.post(self._slack_webhook, json=payload)

    async def _send_telegram(self, alert: dict) -> None:
        import httpx

        text = f"*[{alert['severity']}] {alert['title']}*\n{alert['message']}"
        url = f"https://api.telegram.org/bot{self._telegram_bot_token}/sendMessage"

        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": self._telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            })
