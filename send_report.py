#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Sending Module - v2 (Visual Upgrade)
Sends daily financial report via:
  - Primary: SendGrid API
  - Fallback: Gmail SMTP
  - WeChat Work Webhook (rich content with full market data + AI summary)

Changes from v1:
  - Attaches BOTH v1 (original) and v2 (visual branded cover) PDFs
  - Upgraded email HTML body with branded header and PDF preview button
  - All other logic (WeChat, env vars, fallback) unchanged
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
EMAIL_FROM_NAME       = os.environ.get("EMAIL_FROM_NAME", "链采联盟-每日财经信息")
EMAIL_FROM_ADDR       = os.environ.get("EMAIL_FROM_ADDR", GMAIL_USER)
EMAIL_RECIPIENTS_STR  = os.environ.get(
    "EMAIL_RECIPIENTS",
    "jack.tang@schainpro.com;service@schainpro.com;william.qin@schainpro.com;"
    "frankzhou@schainpro.com;support@schainpro.com;bella.chen@schainpro.com;mario.qian@schainpro.com"
)
WECHAT_WEBHOOK_URL    = os.environ.get(
    "WECHAT_WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=c6942e51-0d31-415a-88a9-43cc38dc0fdc"
)
WECHAT_WEBHOOK_URL2   = os.environ.get(
    "WECHAT_WEBHOOK_URL2",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=4741cbb7-ac6c-47cf-94e0-b77e845636d2"
)
GITHUB_REPOSITORY     = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_PAGES_DOMAIN   = os.environ.get("GITHUB_PAGES_DOMAIN", "")


def get_recipients() -> list:
    return [r.strip() for r in EMAIL_RECIPIENTS_STR.split(";") if r.strip()]


def get_html_public_url(html_filename: str) -> str:
    """Build the GitHub Pages public URL for the HTML report."""
    if GITHUB_PAGES_DOMAIN:
        return f"https://{GITHUB_PAGES_DOMAIN}/{html_filename}"
    if GITHUB_REPOSITORY:
        parts = GITHUB_REPOSITORY.split("/")
        if len(parts) == 2:
            owner, repo = parts[0], parts[1]
            return f"https://{owner}.github.io/{repo}/{html_filename}"
    return ""


# ============================================================
# NEW: Branded Email HTML Body Builder
# ============================================================
def build_email_html(report_date: str, html_public_url: str, v2_pdf_name: str) -> str:
    """Build a visually rich HTML email body with branded header."""
    date_cn = datetime.now().strftime('%Y年%m月%d日')
    link_section = ""
    if html_public_url:
        link_section = f"""
        <div style="text-align:center;margin:28px 0;">
          <a href="{html_public_url}"
             style="display:inline-block;background:#c0392b;color:#fff;
                    font-size:14px;font-weight:700;padding:12px 32px;
                    border-radius:4px;text-decoration:none;letter-spacing:1px;">
            点击查看完整网页版报告 →
          </a>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:'PingFang SC','Microsoft YaHei',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:24px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.08);">

  <!-- HEADER -->
  <tr>
    <td style="background:linear-gradient(135deg,#0f0000 0%,#1a0000 50%,#0a0a0a 100%);padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding:8px 32px;border-bottom:1px solid rgba(192,57,43,0.4);">
            <span style="font-size:13px;font-weight:900;color:#d4a017;letter-spacing:2px;">链采联盟</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.35);margin-left:12px;letter-spacing:1px;">CHAIN PROCUREMENT ALLIANCE</span>
          </td>
        </tr>
        <tr>
          <td style="padding:32px 32px 28px;">
            <div style="display:inline-block;background:#c0392b;color:#fff;font-size:10px;font-weight:900;
                        letter-spacing:3px;padding:4px 12px;border-radius:2px;margin-bottom:14px;">
              链采联盟 · 每日财经推送
            </div>
            <h1 style="font-size:28px;font-weight:900;color:#fff;margin:0 0 6px;line-height:1.2;">
              每日财经信息
            </h1>
            <p style="font-size:14px;color:#d4a017;margin:0 0 16px;font-weight:700;">
              金融市场 · 宏观经济 · 采购趋势 &nbsp;|&nbsp; {date_cn}
            </p>
            <p style="font-size:12px;color:rgba(255,255,255,0.45);margin:0;line-height:1.7;
                      border-left:2px solid rgba(192,57,43,0.6);padding-left:12px;">
              本期简报基于 Bloomberg · FT · WSJ · CNBC · The Economist · Fed · ECB 等
              28+ 权威渠道最新数据，由 AI 深度分析生成。
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- BODY -->
  <tr>
    <td style="padding:28px 32px 8px;">
      <p style="font-size:14px;color:#333;line-height:1.8;margin:0 0 16px;">
        您好，<br/>
        <strong>链采联盟每日财经信息</strong>已生成，请查阅本期简报。
        本邮件附有两个版本的 PDF 报告：
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
        <tr>
          <td width="48%" style="background:#fdf8f5;border:1px solid #f0ddd0;border-top:3px solid #c0392b;
                                  border-radius:4px;padding:14px 16px;">
            <div style="font-size:11px;font-weight:700;color:#c0392b;letter-spacing:1px;margin-bottom:6px;">
              📄 精装版（推荐）
            </div>
            <div style="font-size:13px;font-weight:700;color:#1a1a1a;margin-bottom:4px;">
              {v2_pdf_name}
            </div>
            <div style="font-size:11px;color:#888;">
              品牌封面 · 彩色板块 · 视觉优化
            </div>
          </td>
          <td width="4%"></td>
          <td width="48%" style="background:#f5f9ff;border:1px solid #c8dff5;border-top:3px solid #1a6fa8;
                                  border-radius:4px;padding:14px 16px;">
            <div style="font-size:11px;font-weight:700;color:#1a6fa8;letter-spacing:1px;margin-bottom:6px;">
              📋 专业版
            </div>
            <div style="font-size:13px;font-weight:700;color:#1a1a1a;margin-bottom:4px;">
              investment_research_{report_date}.pdf
            </div>
            <div style="font-size:11px;color:#888;">
              原始格式 · 数据完整 · 适合存档
            </div>
          </td>
        </tr>
      </table>
      {link_section}
    </td>
  </tr>

  <!-- SECTIONS PREVIEW -->
  <tr>
    <td style="padding:0 32px 24px;">
      <div style="background:#f9f9f9;border-radius:6px;overflow:hidden;">
        <div style="background:#0f0000;padding:10px 16px;">
          <span style="font-size:11px;font-weight:700;color:#d4a017;letter-spacing:1px;">本期内容板块</span>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #eee;">
              <span style="display:inline-block;background:#c0392b;color:#fff;font-size:10px;
                           font-weight:700;padding:2px 8px;border-radius:2px;margin-right:8px;">01</span>
              <span style="font-size:13px;color:#333;font-weight:600;">市场概览</span>
              <span style="font-size:11px;color:#999;margin-left:8px;">全球主要股指 · 核心主题</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #eee;">
              <span style="display:inline-block;background:#d35400;color:#fff;font-size:10px;
                           font-weight:700;padding:2px 8px;border-radius:2px;margin-right:8px;">02</span>
              <span style="font-size:13px;color:#333;font-weight:600;">宏观经济分析</span>
              <span style="font-size:11px;color:#999;margin-left:8px;">央行政策 · 通胀 · 经济数据</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #eee;">
              <span style="display:inline-block;background:#1a6fa8;color:#fff;font-size:10px;
                           font-weight:700;padding:2px 8px;border-radius:2px;margin-right:8px;">03</span>
              <span style="font-size:13px;color:#333;font-weight:600;">行业动态</span>
              <span style="font-size:11px;color:#999;margin-left:8px;">AI · 新能源 · 半导体 · 科技</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #eee;">
              <span style="display:inline-block;background:#b8860b;color:#fff;font-size:10px;
                           font-weight:700;padding:2px 8px;border-radius:2px;margin-right:8px;">04</span>
              <span style="font-size:13px;color:#333;font-weight:600;">采购趋势</span>
              <span style="font-size:11px;color:#999;margin-left:8px;">大宗商品 · 物流 · 供应链</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 16px;">
              <span style="display:inline-block;background:#148f77;color:#fff;font-size:10px;
                           font-weight:700;padding:2px 8px;border-radius:2px;margin-right:8px;">05</span>
              <span style="font-size:13px;color:#333;font-weight:600;">投资策略建议</span>
              <span style="font-size:11px;color:#999;margin-left:8px;">资产配置 · 风险提示 · 操作建议</span>
            </td>
          </tr>
        </table>
      </div>
    </td>
  </tr>

  <!-- FOOTER -->
  <tr>
    <td style="background:#0f0000;padding:16px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td>
            <span style="font-size:12px;font-weight:700;color:#d4a017;">链采联盟 · 每日财经信息</span><br/>
            <span style="font-size:10px;color:rgba(255,255,255,0.3);">CHAIN PROCUREMENT ALLIANCE · DAILY FINANCE BRIEFING</span>
          </td>
          <td align="right">
            <span style="font-size:10px;color:rgba(255,255,255,0.25);">
              {date_cn}<br/>
              本邮件仅供参考，不构成投资建议
            </span>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


# ============================================================
# SendGrid Sending (v2 - dual PDF attachments)
# ============================================================
def send_via_sendgrid(
    v1_html_path: str, v1_pdf_path: str,
    v2_pdf_path: str,
    report_date: str, html_public_url: str
) -> bool:
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
        v2_pdf_name = os.path.basename(v2_pdf_path)
        email_html = build_email_html(report_date, html_public_url, v2_pdf_name)

        message = Mail(
            from_email=From(EMAIL_FROM_ADDR, EMAIL_FROM_NAME),
            to_emails=[To(r) for r in recipients],
            subject=f"【链采联盟】每日财经信息 - {report_date}",
            html_content=email_html
        )

        # Attach v2 visual PDF (primary)
        with open(v2_pdf_path, "rb") as f:
            pdf2_b64 = base64.b64encode(f.read()).decode()
        message.add_attachment(Attachment(
            FileContent(pdf2_b64),
            FileName(v2_pdf_name),
            FileType("application/pdf"),
            Disposition("attachment")
        ))

        # Attach v1 original PDF (secondary)
        with open(v1_pdf_path, "rb") as f:
            pdf1_b64 = base64.b64encode(f.read()).decode()
        message.add_attachment(Attachment(
            FileContent(pdf1_b64),
            FileName(os.path.basename(v1_pdf_path)),
            FileType("application/pdf"),
            Disposition("attachment")
        ))

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
# Gmail SMTP Sending (v2 - dual PDF attachments + branded body)
# ============================================================
def send_via_gmail_smtp(
    v1_html_path: str, v1_pdf_path: str,
    v2_pdf_path: str,
    report_date: str, html_public_url: str
) -> bool:
    if not GMAIL_APP_PASSWORD:
        print("Gmail app password not set, skipping Gmail SMTP.")
        return False
    recipients = get_recipients()
    v2_pdf_name = os.path.basename(v2_pdf_path)
    email_html = build_email_html(report_date, html_public_url, v2_pdf_name)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"【链采联盟】每日财经信息 - {report_date}"
    msg["From"] = f"{EMAIL_FROM_NAME} <{GMAIL_USER}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(email_html, "html", "utf-8"))

    # Attach v2 visual PDF (primary - listed first)
    with open(v2_pdf_path, "rb") as f:
        pdf2_data = f.read()
    part2 = MIMEBase("application", "octet-stream")
    part2.set_payload(pdf2_data)
    encoders.encode_base64(part2)
    part2.add_header("Content-Disposition", "attachment", filename=v2_pdf_name)
    msg.attach(part2)

    # Attach v1 original PDF (secondary)
    with open(v1_pdf_path, "rb") as f:
        pdf1_data = f.read()
    part1 = MIMEBase("application", "octet-stream")
    part1.set_payload(pdf1_data)
    encoders.encode_base64(part1)
    part1.add_header(
        "Content-Disposition", "attachment",
        filename=f"investment_research_{report_date}.pdf"
    )
    msg.attach(part1)

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


def send_email(
    v1_html_path: str, v1_pdf_path: str,
    v2_pdf_path: str,
    report_date: str, html_public_url: str
) -> bool:
    print(f"\n--- Sending Email (v2 dual-PDF) ---")
    if SENDGRID_API_KEY:
        success = send_via_sendgrid(
            v1_html_path, v1_pdf_path, v2_pdf_path, report_date, html_public_url
        )
        if success:
            return True
        print("SendGrid failed, trying Gmail SMTP fallback...")
    return send_via_gmail_smtp(
        v1_html_path, v1_pdf_path, v2_pdf_path, report_date, html_public_url
    )


# ============================================================
# Helpers for WeChat content extraction (unchanged from v1)
# ============================================================
def extract_section(md_text: str, section_title: str, max_chars: int = 400) -> str:
    pattern = rf'## [一二三四五六七八九十\d]+[、.．]?\s*{re.escape(section_title)}.*?(?=\n## |\Z)'
    match = re.search(pattern, md_text, re.DOTALL)
    if match:
        content = match.group(0)
        lines = content.split('\n')
        body_lines = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith('###') or stripped.startswith('---'):
                continue
            if stripped:
                clean = re.sub(r'\*\*(.+?)\*\*', r'\1', stripped)
                clean = re.sub(r'\*(.+?)\*', r'\1', clean)
                body_lines.append(clean)
        body = ' '.join(body_lines)
        return body[:max_chars].rstrip() + ('…' if len(body) > max_chars else '')
    return ""


def fmt_market_row(name: str, val: dict) -> str:
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
# WeChat Work Webhook (unchanged from v1)
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

    try:
        with open(market_data_path, "r", encoding="utf-8") as f:
            market_data = json.load(f)
    except Exception:
        market_data = {"indices": {}, "commodities": {}, "forex": {}}

    try:
        with open(content_md_path, "r", encoding="utf-8") as f:
            content_md = f.read()
    except Exception:
        content_md = ""

    indices    = market_data.get("indices", {})
    commodities = market_data.get("commodities", {})
    forex      = market_data.get("forex", {})

    indices_lines   = "\n".join([fmt_market_row(k, v) for k, v in indices.items()])
    commodity_lines = "\n".join([fmt_market_row(k, v) for k, v in commodities.items()])
    forex_lines     = "\n".join([fmt_market_row(k, v) for k, v in forex.items()])

    market_overview     = extract_section(content_md, "市场概览", 300)
    macro_summary       = extract_section(content_md, "宏观经济分析", 350)
    industry_summary    = extract_section(content_md, "行业动态", 350)
    company_summary     = extract_section(content_md, "公司聚焦", 300)
    procurement_summary = extract_section(content_md, "采购趋势", 400)
    strategy_summary    = extract_section(content_md, "投资策略建议", 300)

    link_line = (
        f"📎 [**点击查看完整报告 →**]({html_public_url})"
        if html_public_url else
        "📧 完整报告已通过邮件发送（含 PDF 附件）"
    )

    message_parts = []
    message_parts.append(
        f"# 📈 链采联盟-每日财经信息  {report_date}\n"
        f"> 数据来源：Bloomberg · FT · WSJ · CNBC · The Economist · Fed · ECB · BIS · OilPrice · "
        f"TechCrunch · SCMP · Nikkei Asia · Supply Chain Dive · Spend Matters 等 **28+ 权威渠道**"
    )
    if market_overview:
        message_parts.append(f"\n## 一、市场概览\n{market_overview}")
    message_parts.append(f"\n## 二、主要股票指数\n{indices_lines}")
    message_parts.append(f"\n## 三、大宗商品\n{commodity_lines}")
    message_parts.append(f"\n## 四、外汇市场\n{forex_lines}")
    if macro_summary:
        message_parts.append(f"\n## 五、宏观经济要点\n{macro_summary}")
    if industry_summary:
        message_parts.append(f"\n## 六、行业动态要点\n{industry_summary}")
    if company_summary:
        message_parts.append(f"\n## 七、公司聚焦\n{company_summary}")
    if procurement_summary:
        message_parts.append(f"\n## 八、采购趋势\n{procurement_summary}")
    if strategy_summary:
        message_parts.append(f"\n## 九、投资策略建议\n{strategy_summary}")
    message_parts.append(
        f"\n---\n{link_line}\n\n"
        f"_⚠️ 本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。_"
    )

    full_message = "\n".join(message_parts)
    if len(full_message) > 4000:
        full_message = full_message[:3950] + f"\n\n…（内容已截断）\n{link_line}"

    payload = {"msgtype": "markdown", "markdown": {"content": full_message}}

    success = False
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
    indices_lines = "\n".join([fmt_market_row(k, v) for k, v in list(indices.items())[:6]])
    commodity_lines = "\n".join([fmt_market_row(k, v) for k, v in list(commodities.items())[:4]])
    link_line = (
        f"📎 [**点击查看完整报告 →**]({html_public_url})"
        if html_public_url else "📧 完整报告已发送至邮箱"
    )
    msg = (
        f"# 📈 链采联盟-每日财经信息  {report_date}\n\n"
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
# Main (v2 - reads both v1 and v2 PDF paths)
# ============================================================
if __name__ == "__main__":
    report_date = datetime.now().strftime("%Y-%m-%d")

    v1_base     = f"investment_research_{report_date}"
    v1_html_path = f"{v1_base}.html"
    v1_pdf_path  = f"{v1_base}.pdf"

    v2_html_path = f"report_visual_{report_date}.html"
    v2_pdf_path  = f"report_visual_{report_date}.pdf"

    html_public_url = get_html_public_url(v1_html_path)
    print(f"HTML public URL: {html_public_url or '(not set)'}")

    send_email(v1_html_path, v1_pdf_path, v2_pdf_path, report_date, html_public_url)
    send_wechat_work(html_public_url, report_date)
