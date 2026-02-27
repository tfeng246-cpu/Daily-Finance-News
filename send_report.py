#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Sending Module
Sends daily financial report via:
  - Primary: SendGrid API
  - Fallback: Gmail SMTP
  - WeChat Work Webhook (rich content with full market data + AI summary)
"""

import os
import re
import smtplib
import requests
import json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

# ============================================================
# Configuration (from environment variables / GitHub Secrets)
# ============================================================
SENDGRID_API_KEY      = os.environ.get("SENDGRID_API_KEY", "")
GMAIL_USER            = os.environ.get("GMAIL_USER", "tfeng246@gmail.com")
GMAIL_APP_PASSWORD    = os.environ.get("GMAIL_APP_PASSWORD", "")
EMAIL_FROM_NAME       = os.environ.get("EMAIL_FROM_NAME", "链采联盟-每日财金信息")
EMAIL_FROM_ADDR       = os.environ.get("EMAIL_FROM_ADDR", GMAIL_USER)
EMAIL_RECIPIENTS_STR  = os.environ.get("EMAIL_RECIPIENTS", "jack.tang@schainpro.com;service@schainpro.com;william.qin@schainpro.com;frankzhou@schainpro.com;bella.chen@schainpro.com;mario.qian@schainpro.com")
WECHAT_WEBHOOK_URL    = os.environ.get(
    "WECHAT_WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=c6942e51-0d31-415a-88a9-43cc38dc0fdc"
)
WECHAT_WEBHOOK_URL2   = os.environ.get(
    "WECHAT_WEBHOOK_URL2",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=4741cbb7-ac6c-47cf-94e0-b77e845636d2"
)
GITHUB_REPOSITORY     = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_PAGES_DOMAIN   = os.environ.get("GITHUB_PAGES_DOMAIN", "")  # Optional custom domain


def get_recipients() -> list:
    return [r.strip() for r in EMAIL_RECIPIENTS_STR.split(";") if r.strip()]


def get_html_public_url(html_filename: str) -> str:
    """Build the GitHub Pages public URL for the HTML report."""
    # Allow override via env var
    if GITHUB_PAGES_DOMAIN:
        return f"https://{GITHUB_PAGES_DOMAIN}/{html_filename}"
    if GITHUB_REPOSITORY:
        parts = GITHUB_REPOSITORY.split("/")
        if len(parts) == 2:
            owner, repo = parts[0], parts[1]
            return f"https://{owner}.github.io/{repo}/{html_filename}"
    return ""


# ============================================================
# SendGrid Sending
# ============================================================
def send_via_sendgrid(html_path: str, pdf_path: str, report_date: str) -> bool:
    if not SENDGRID_API_KEY:
        print("SendGrid API key not set, skipping SendGrid.")
        return False
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, Attachment, FileContent, FileName,
            FileType, Disposition, To, From
        )
        recipients = get_recipients()
        with open(html_path, "r", encoding="utf-8") as f:
            html_body = f.read()
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        message = Mail(
            from_email=From(EMAIL_FROM_ADDR, EMAIL_FROM_NAME),
            to_emails=[To(r) for r in recipients],
            subject=f"链采联盟-每日财金信息 - {report_date}",
            html_content=html_body
        )
        pdf_b64 = base64.b64encode(pdf_data).decode()
        attachment = Attachment(
            FileContent(pdf_b64),
            FileName(f"investment_research_{report_date}.pdf"),
            FileType("application/pdf"),
            Disposition("attachment")
        )
        message.attachment = attachment
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code in (200, 202):
            print(f"[SendGrid] Email sent to: {', '.join(recipients)}")
            return True
        else:
            print(f"[SendGrid] Unexpected status: {response.status_code} - {response.body}")
            return False
    except Exception as e:
        print(f"[SendGrid] Error: {e}")
        return False


# ============================================================
# Gmail SMTP Sending (Fallback)
# ============================================================
def send_via_gmail_smtp(html_path: str, pdf_path: str, report_date: str) -> bool:
    if not GMAIL_APP_PASSWORD:
        print("Gmail app password not set, skipping Gmail SMTP.")
        return False
    recipients = get_recipients()
    with open(html_path, "r", encoding="utf-8") as f:
        html_body = f.read()
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"链采联盟-每日财金信息 - {report_date}"
    msg["From"] = f"{EMAIL_FROM_NAME} <{GMAIL_USER}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    pdf_part = MIMEBase("application", "octet-stream")
    pdf_part.set_payload(pdf_data)
    encoders.encode_base64(pdf_part)
    pdf_part.add_header(
        "Content-Disposition", "attachment",
        filename=f"investment_research_{report_date}.pdf"
    )
    msg.attach(pdf_part)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, recipients, msg.as_string())
        print(f"[Gmail SMTP] Email sent to: {', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[Gmail SMTP] Error: {e}")
        return False


def send_email(html_path: str, pdf_path: str, report_date: str, html_public_url: str) -> bool:
    print(f"\n--- Sending Email ---")
    if SENDGRID_API_KEY:
        success = send_via_sendgrid(html_path, pdf_path, report_date)
        if success:
            return True
        print("SendGrid failed, trying Gmail SMTP fallback...")
    return send_via_gmail_smtp(html_path, pdf_path, report_date)


# ============================================================
# Helpers for WeChat content extraction
# ============================================================
def extract_section(md_text: str, section_title: str, max_chars: int = 400) -> str:
    """Extract a section from the generated markdown content."""
    pattern = rf'## [一二三四五六七八九十\d]+[、.．]?\s*{re.escape(section_title)}.*?(?=\n## |\Z)'
    match = re.search(pattern, md_text, re.DOTALL)
    if match:
        content = match.group(0)
        # Remove the heading line itself
        lines = content.split('\n')
        body_lines = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith('###'):
                continue
            if stripped.startswith('---'):
                continue
            if stripped:
                # Strip markdown bold/italic
                clean = re.sub(r'\*\*(.+?)\*\*', r'\1', stripped)
                clean = re.sub(r'\*(.+?)\*', r'\1', clean)
                body_lines.append(clean)
        body = ' '.join(body_lines)
        return body[:max_chars].rstrip() + ('…' if len(body) > max_chars else '')
    return ""


def fmt_market_row(name: str, val: dict) -> str:
    """Format a single market data row for WeChat markdown."""
    pct = val.get("pct", "N/A") if isinstance(val, dict) else "N/A"
    price = val.get("price", "N/A") if isinstance(val, dict) else "N/A"
    if isinstance(pct, str) and "+" in pct:
        arrow = "🔺"
    elif isinstance(pct, str) and "-" in pct:
        arrow = "🔻"
    else:
        arrow = "➡️"
    return f"{arrow} **{name}**: {price}  ({pct})"


# ============================================================
# WeChat Work Webhook — Rich Content
# ============================================================
def send_wechat_work(
    html_public_url: str,
    report_date: str,
    market_data_path: str = "market_data.json",
    content_md_path: str = "generated_content.md"
) -> bool:
    print(f"\n--- Sending WeChat Work Message ---")
    if not WECHAT_WEBHOOK_URL:
        print("WeChat Work webhook URL not set.")
        return False

    # --- Load market data ---
    try:
        with open(market_data_path, "r", encoding="utf-8") as f:
            market_data = json.load(f)
    except Exception:
        market_data = {"indices": {}, "commodities": {}, "forex": {}}

    # --- Load AI-generated content ---
    try:
        with open(content_md_path, "r", encoding="utf-8") as f:
            content_md = f.read()
    except Exception:
        content_md = ""

    # ---- Market Data Sections ----
    indices = market_data.get("indices", {})
    commodities = market_data.get("commodities", {})
    forex = market_data.get("forex", {})

    indices_lines   = "\n".join([fmt_market_row(k, v) for k, v in indices.items()])
    commodity_lines = "\n".join([fmt_market_row(k, v) for k, v in commodities.items()])
    forex_lines     = "\n".join([fmt_market_row(k, v) for k, v in forex.items()])

    # ---- Extract AI content summaries ----
    market_overview     = extract_section(content_md, "市场概览", 300)
    macro_summary       = extract_section(content_md, "宏观经济分析", 350)
    industry_summary    = extract_section(content_md, "行业动态", 350)
    company_summary     = extract_section(content_md, "公司聚焦", 300)
    procurement_summary = extract_section(content_md, "采购趋势", 400)
    strategy_summary    = extract_section(content_md, "投资策略建议", 300)

    # ---- Build report link line ----
    if html_public_url:
        link_line = f"📎 [**点击查看完整报告 →**]({html_public_url})"
    else:
        link_line = "📧 完整报告已通过邮件发送（含 PDF 附件）"

    # ---- Compose the full WeChat message ----
    # WeChat Work markdown supports: **bold**, [link](url), >, headings with #
    # Max message length: ~4096 chars
    message_parts = []

    # Header
    message_parts.append(
        f"# 📈 链采联盟-每日财金信息  {report_date}\n"
        f"> 数据来源：Bloomberg · FT · WSJ · CNBC · The Economist · Fed · ECB · BIS · OilPrice · TechCrunch · SCMP · Nikkei Asia · Supply Chain Dive · Spend Matters 等 **28+ 权威渠道**"
    )

    # Market overview excerpt
    if market_overview:
        message_parts.append(
            f"\n## 一、市场概览\n{market_overview}"
        )

    # Full indices
    message_parts.append(
        f"\n## 二、主要股票指数\n{indices_lines}"
    )

    # Commodities + Forex side by side (as separate blocks)
    message_parts.append(
        f"\n## 三、大宗商品\n{commodity_lines}"
    )
    message_parts.append(
        f"\n## 四、外汇市场\n{forex_lines}"
    )

    # Macro summary
    if macro_summary:
        message_parts.append(
            f"\n## 五、宏观经济要点\n{macro_summary}"
        )

    # Industry summary
    if industry_summary:
        message_parts.append(
            f"\n## 六、行业动态要点\n{industry_summary}"
        )

    # Company focus
    if company_summary:
        message_parts.append(
            f"\n## 七、公司聚焦\n{company_summary}"
        )

    # Procurement trends
    if procurement_summary:
        message_parts.append(
            f"\n## 八、采购趋势\n{procurement_summary}"
        )

    # Strategy
    if strategy_summary:
        message_parts.append(
            f"\n## 九、投资策略建议\n{strategy_summary}"
        )

    # Footer with link
    message_parts.append(
        f"\n---\n{link_line}\n\n"
        f"_⚠️ 本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。_"
    )

    full_message = "\n".join(message_parts)

    # WeChat Work markdown message limit is ~4096 chars; truncate gracefully if needed
    if len(full_message) > 4000:
        full_message = full_message[:3950] + f"\n\n…（内容已截断）\n{link_line}"

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": full_message}
    }

    success = False
    # Send to all configured webhook URLs
    urls_to_send = [u for u in [WECHAT_WEBHOOK_URL, WECHAT_WEBHOOK_URL2] if u]
    for idx, wechat_url in enumerate(urls_to_send, 1):
        try:
            resp = requests.post(wechat_url, json=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            if result.get("errcode") == 0:
                print(f"[WeChat Work] Message sent successfully to group {idx}.")
                success = True
            else:
                print(f"[WeChat Work] API error (group {idx}): {result}")
                if result.get("errcode") == 45009:
                    _send_wechat_fallback_url(wechat_url, html_public_url, report_date, indices, commodities)
        except Exception as e:
            print(f"[WeChat Work] Error (group {idx}): {e}")
    return success


def _send_wechat_fallback_url(wechat_url, html_public_url, report_date, indices, commodities):
    """Send a shorter fallback message to a specific URL if the full message is too long."""
    indices_lines = "\n".join([fmt_market_row(k, v) for k, v in list(indices.items())[:6]])
    commodity_lines = "\n".join([fmt_market_row(k, v) for k, v in list(commodities.items())[:4]])
    link_line = f"📎 [**点击查看完整报告 →**]({html_public_url})" if html_public_url else "📧 完整报告已发送至邮箱"
    msg = (
        f"# 📈 链采联盟-每日财金信息  {report_date}\n\n"
        f"**主要指数**\n{indices_lines}\n\n"
        f"**大宗商品**\n{commodity_lines}\n\n"
        f"{link_line}\n\n"
        f"_本报告仅供参考，不构成投资建议。_"
    )
    payload = {"msgtype": "markdown", "markdown": {"content": msg}}
    try:
        resp = requests.post(wechat_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            print("[WeChat Work] Fallback message sent.")
            return True
    except Exception as e:
        print(f"[WeChat Work] Fallback error: {e}")
    return False


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    report_date = datetime.now().strftime("%Y-%m-%d")
    base_name   = f"investment_research_{report_date}"
    html_path   = f"{base_name}.html"
    pdf_path    = f"{base_name}.pdf"

    html_public_url = get_html_public_url(f"{base_name}.html")
    print(f"HTML public URL: {html_public_url or '(not set)'}")

    send_email(html_path, pdf_path, report_date, html_public_url)
    send_wechat_work(html_public_url, report_date)
