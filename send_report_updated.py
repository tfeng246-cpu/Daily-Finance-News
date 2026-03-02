#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Sending Module - v2 (Visual Upgrade)
Sends the new visual report via Gmail, with both PDF versions attached.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

# ============================================================
# Configuration (from environment variables)
# ============================================================
GMAIL_USER = os.environ.get("GMAIL_USER", "tfeng246@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "fygi zxqm hkrg hroc")
EMAIL_RECIPIENTS_STR = os.environ.get("EMAIL_RECIPIENTS", "jack.tang@schainpro.com;service@schainpro.com;william.qin@schainpro.com;frankzhou@schainpro.com;bella.chen@schainpro.com;mario.qian@schainpro.com")

def get_recipients() -> list:
    return [r.strip() for r in EMAIL_RECIPIENTS_STR.split(";") if r.strip()]

# ============================================================
# Main Email Sending Function
# ============================================================
def send_updated_email(v1_pdf_path: str, v2_pdf_path: str, report_date: str):
    print("--- Sending Updated Email via Gmail SMTP ---")
    if not GMAIL_APP_PASSWORD:
        print("Gmail app password not set. Aborting.")
        return False

    recipients = get_recipients()
    sender = GMAIL_USER

    # --- Create the visual HTML email body ---
    # This body is based on the successful war briefing email template.
    html_body = f""" 
    <html><body style="font-family:'Microsoft YaHei',Arial,sans-serif;background:#f5f5f5;padding:20px;">
    <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;">
      <div style="background:#0f0000;padding:24px 32px;border-bottom:3px solid #d4a017;">
        <div style="color:#d4a017;font-size:18px;font-weight:900;">链采联盟 · 每日财金信息</div>
      </div>
      <div style="padding:28px 32px;">
        <h2 style="color:#1a1a1a;font-size:22px;margin:0 0 8px;">每日金融市场与采购趋势报告</h2>
        <p style="color:#666;font-size:13px;margin:0 0 20px;">{report_date}</p>
        <p style="color:#333;line-height:1.8;font-size:14px;">
          您好！今日的《每日财金信息》已生成，包含市场概览、宏观分析、行业动态和采购趋势等核心内容。
        </p>
        <p style="color:#333;line-height:1.8;font-size:14px;">
          本次邮件附带两个版本的PDF报告：
        </p>
        <ul style="color:#333;line-height:2;font-size:14px;">
          <li><b>report_v2_visual.pdf</b>: 全新精装版，视觉效果更佳 (推荐)</li>
          <li><b>report_v1_original.pdf</b>: 原始专业版，内容详尽</li>
        </ul>
        <p style="color:#999;font-size:11px;border-top:1px solid #eee;padding-top:16px;margin-top:20px;">
          本简报仅供参考，不构成任何投资或商业决策建议。
        </p>
      </div>
    </div>
    </body></html>
    """

    # --- Create the email message ---
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"【链采联盟】每日财金信息 · {report_date}"
    msg["From"] = f"链采联盟 <{sender}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # --- Attach both PDFs ---
    for pdf_path in [v1_pdf_path, v2_pdf_path]:
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename=\"{os.path.basename(pdf_path)}\"")
        msg.attach(part)

    # --- Send the email ---
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, GMAIL_APP_PASSWORD)
            server.sendmail(sender, recipients, msg.as_string())
        print(f"Email sent successfully to {len(recipients)} recipients.")
        return True
    except Exception as e:
        print(f"Error sending email via Gmail: {e}")
        return False

# ============================================================
# Main execution block
# ============================================================
if __name__ == "__main__":
    # This script is designed to be called by the main workflow,
    # which will pass the PDF paths.
    # For standalone testing, you can create dummy files.
    print("Running send_report_updated.py...")
    report_date = datetime.now().strftime('%Y-%m-%d')
    v1_dummy_path = f"report_v1_original_{report_date}.pdf"
    v2_dummy_path = f"report_v2_visual_{report_date}.pdf"
    
    if not os.path.exists(v1_dummy_path):
        with open(v1_dummy_path, "w") as f: f.write("dummy v1 pdf")
    if not os.path.exists(v2_dummy_path):
        with open(v2_dummy_path, "w") as f: f.write("dummy v2 pdf")

    send_updated_email(v1_dummy_path, v2_dummy_path, report_date)
