#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Sending Module - SendGrid primary, Gmail SMTP fallback, WeChat Work webhook.
"""

import os
import smtplib
import requests
import json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "tfeng246@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "每日财金信息")
EMAIL_FROM_ADDR = os.environ.get("EMAIL_FROM_ADDR", GMAIL_USER)
EMAIL_RECIPIENTS_STR = os.environ.get("EMAIL_RECIPIENTS", "jack.tang@schainpro.com")
WECHAT_WEBHOOK_URL = os.environ.get(
    "WECHAT_WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=c6942e51-0d31-415a-88a9-43cc38dc0fdc"
 )
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")

def get_recipients() -> list:
    return [r.strip() for r in EMAIL_RECIPIENTS_STR.split(";") if r.strip()]

def get_html_public_url(html_filename: str) -> str:
    if GITHUB_REPOSITORY:
        parts = GITHUB_REPOSITORY.split("/")
        if len(parts) == 2:
            return f"https://{parts[0]}.github.io/{parts[1]}/{html_filename}"
    return ""

def send_via_sendgrid(html_path: str, pdf_path: str, report_date: str ) -> bool:
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
            subject=f"每日财金信息 - {report_date}",
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
            print(f"[SendGrid] Email sent successfully to: {', '.join(recipients)}")
            return True
        else:
            print(f"[SendGrid] Unexpected status: {response.status_code}")
            return False
    except Exception as e:
        print(f"[SendGrid] Error: {e}")
        return False

def send_via_gmail_smtp(html_path: str, pdf_path: str, report_date: str) -> bool:
    if not GMAIL_APP_PASSWORD:
        print("Gmail app password not set, skipping Gmail SMTP.")
        return False
    recipients = get_recipients()
    with open(html_path, "r", encoding="utf-8") as f:
        html_body = f.read()
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"每日财金信息 - {report_date}"
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
        print(f"[Gmail SMTP] Email sent successfully to: {', '.join(recipients)}")
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

def send_wechat_work(html_public_url: str, report_date: str, market_data_path: str = "market_data.json") -> bool:
    print(f"\n--- Sending WeChat Work Message ---")
    if not WECHAT_WEBHOOK_URL:
        print("WeChat Work webhook URL not set.")
        return False
    try:
        with open(market_data_path, "r", encoding="utf-8") as f:
            market_data = json.load(f)
    except Exception:
        market_data = {"indices": {}, "commodities": {}, "forex": {}}

    def fmt_index(name, val):
        if isinstance(val, dict):
            pct = val.get("pct", "")
            price = val.get("price", "N/A")
            arrow = "🔺" if "+" in pct else ("🔻" if "-" in pct else "➡️")
            return f"{arrow} **{name}**: {price} ({pct})"
        return f"**{name}**: {val}"

    indices_lines = "\n".join([fmt_index(k, v) for k, v in list(market_data.get("indices", {}).items())[:6]])
    commodity_lines = "\n".join([fmt_index(k, v) for k, v in list(market_data.get("commodities", {}).items())[:3]])

    if html_public_url:
        link_line = f"\n\n📄 **[点击查看完整报告（HTML）]({html_public_url})**"
    else:
        link_line = "\n\n📧 完整报告已通过邮件发送（含PDF附件）"

    message = f"""📈 **每日财金信息 - {report_date}**
> 数据整合自 Bloomberg · FT · WSJ · CNBC · The Economist · Fed · ECB · OilPrice · TechCrunch · SCMP · Nikkei 等 20+ 权威来源

**📊 主要指数**
{indices_lines}

**🛢️ 大宗商品**
{commodity_lines}
{link_line}

---
_本报告仅供参考，不构成投资建议。_"""

    payload = {"msgtype": "markdown", "markdown": {"content": message}}
    try:
        resp = requests.post(WECHAT_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") == 0:
            print("[WeChat Work] Message sent successfully.")
            return True
        else:
            print(f"[WeChat Work] API error: {result}")
            return False
    except Exception as e:
        print(f"[WeChat Work] Error: {e}")
        return False

if __name__ == "__main__":
    report_date = datetime.now().strftime("%Y-%m-%d")
    base_name = f"investment_research_{report_date}"
    html_path = f"{base_name}.html"
    pdf_path = f"{base_name}.pdf"
    html_public_url = get_html_public_url(f"{base_name}.html")
    print(f"HTML public URL: {html_public_url or '(not set)'}")
    send_email(html_path, pdf_path, report_date, html_public_url)
    send_wechat_work(html_public_url, report_date)
