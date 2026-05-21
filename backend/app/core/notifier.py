"""Notification dispatch.

Channels:
- DingTalk webhook (HMAC-SHA256 sign optional)
- Feishu webhook
- WeCom (Enterprise WeChat) webhook
- Email via SMTP

Flow:
- emit_event(event, payload): writes NotificationEvent row, then for each
  matching NotificationRule, attempts send. Failures retry up to 3 times.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from email.mime.text import MIMEText

import httpx
from sqlalchemy import select

from app.core.crypto import decrypt
from app.core.database import async_session
from app.models.notification import (
    ChannelType,
    EventStatus,
    EventType,
    NotificationChannel,
    NotificationEvent,
    NotificationRule,
    SmtpSettings,
)

logger = logging.getLogger(__name__)


def _format_message(event: EventType, payload: dict) -> str:
    if event == EventType.TASK_FAILED:
        return f"❌ 任务失败：{payload.get('task_name','?')} run={payload.get('run_id','?')[:8]} exit={payload.get('exit_code')}"
    if event == EventType.TASK_TIMEOUT:
        return f"⏰ 任务超时：{payload.get('task_name','?')} run={payload.get('run_id','?')[:8]}"
    if event == EventType.TASK_KILLED:
        return f"🛑 任务被终止：{payload.get('task_name','?')} run={payload.get('run_id','?')[:8]}"
    if event == EventType.WORKER_OFFLINE:
        return f"⚠️ 节点掉线：{payload.get('node_id','?')}"
    return f"事件：{event} {json.dumps(payload, ensure_ascii=False)}"


def _render_template(template: str, event: EventType, payload: dict) -> str:
    """Render channel.template using simple {{var}} substitution.

    Stays single-purpose: no Jinja2 dependency, no conditionals, just safe variable
    expansion. Unknown variables become empty string.
    """
    import re

    ctx = {
        "event": str(event),
        "task_name": payload.get("task_name") or "",
        "task_id": payload.get("task_id") or "",
        "run_id": payload.get("run_id") or "",
        "exit_code": payload.get("exit_code"),
        "error_msg": payload.get("error_msg") or "",
        "node_id": payload.get("node_id") or "",
    }
    return re.sub(
        r"\{\{\s*(\w+)\s*\}\}",
        lambda m: str(ctx.get(m.group(1), "")),
        template,
    )


async def _send_dingtalk(cfg: dict, message: str) -> None:
    webhook = cfg.get("webhook")
    secret = cfg.get("secret")
    if not webhook:
        raise RuntimeError("dingtalk: missing webhook")
    url = webhook
    if secret:
        ts = str(round(time.time() * 1000))
        sign_str = f"{ts}\n{secret}"
        sign = base64.b64encode(
            hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).digest()
        ).decode()
        url = f"{webhook}&timestamp={ts}&sign={urllib.parse.quote(sign)}"
    body = {"msgtype": "text", "text": {"content": message}}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(url, json=body)
        r.raise_for_status()


async def _send_feishu(cfg: dict, message: str) -> None:
    webhook = cfg.get("webhook")
    if not webhook:
        raise RuntimeError("feishu: missing webhook")
    body = {"msg_type": "text", "content": {"text": message}}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(webhook, json=body)
        r.raise_for_status()


async def _send_wecom(cfg: dict, message: str) -> None:
    webhook = cfg.get("webhook")
    if not webhook:
        raise RuntimeError("wecom: missing webhook")
    body = {"msgtype": "text", "text": {"content": message}}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(webhook, json=body)
        r.raise_for_status()


async def _send_email(cfg: dict, message: str) -> None:
    """Send a plain-text email using the singleton SmtpSettings row.

    cfg.recipients = ["a@b.com", ...]
    """
    recipients = cfg.get("recipients") or []
    subject = cfg.get("subject") or "SpiderMan 通知"
    if not recipients:
        raise RuntimeError("email: missing recipients")
    async with async_session() as s:
        smtp = (
            await s.execute(
                select(SmtpSettings).order_by(SmtpSettings.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
    if smtp is None or not smtp.is_enabled:
        raise RuntimeError("email: SMTP not configured/enabled")

    import aiosmtplib

    msg = MIMEText(message, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp.from_addr
    msg["To"] = ", ".join(recipients)
    await aiosmtplib.send(
        msg,
        hostname=smtp.host,
        port=smtp.port,
        username=smtp.username or None,
        password=decrypt(smtp.password_enc) if smtp.password_enc else None,
        start_tls=smtp.use_tls,
    )


SENDERS = {
    ChannelType.DINGTALK: _send_dingtalk,
    ChannelType.FEISHU: _send_feishu,
    ChannelType.WECOM: _send_wecom,
    ChannelType.EMAIL: _send_email,
}


async def _send_via(channel: NotificationChannel, message: str) -> None:
    cfg_str = decrypt(channel.config_enc) or "{}"
    cfg = json.loads(cfg_str)
    sender = SENDERS.get(channel.type)
    if sender is None:
        raise RuntimeError(f"unknown channel type {channel.type}")
    await sender(cfg, message)


async def emit_event(event: EventType, payload: dict) -> None:
    """Persist event then attempt deliveries for all matching rules."""
    async with async_session() as s:
        ev = NotificationEvent(event=event, payload=payload, status=EventStatus.PENDING)
        s.add(ev)
        await s.flush()
        ev_id = ev.id

        rules = (
            await s.execute(
                select(NotificationRule).where(NotificationRule.event == event)
            )
        ).scalars().all()
        rule_channel_ids = [r.channel_id for r in rules]
        channels = (
            (
                await s.execute(
                    select(NotificationChannel).where(
                        NotificationChannel.id.in_(rule_channel_ids),
                        NotificationChannel.is_enabled == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        await s.commit()

    if not channels:
        return

    default_message = _format_message(event, payload)
    failures: list[str] = []
    for ch in channels:
        # Per-channel template overrides global default. Render failures fall
        # back to default to ensure the notification still goes out.
        try:
            message = (
                _render_template(ch.template, event, payload)
                if ch.template
                else default_message
            )
        except Exception:
            message = default_message
        for attempt in range(3):
            try:
                await _send_via(ch, message)
                break
            except Exception as e:
                logger.warning(
                    "notify ch=%s attempt=%d failed: %s", ch.name, attempt + 1, e
                )
                if attempt == 2:
                    failures.append(f"{ch.name}: {e}")
                else:
                    await asyncio.sleep(2 * (attempt + 1))

    async with async_session() as s:
        ev = (
            await s.execute(
                select(NotificationEvent).where(NotificationEvent.id == ev_id)
            )
        ).scalar_one()
        ev.status = EventStatus.FAILED if failures else EventStatus.SENT
        ev.last_error = "; ".join(failures) if failures else None
        ev.sent_at = datetime.now(timezone.utc)
        await s.commit()
