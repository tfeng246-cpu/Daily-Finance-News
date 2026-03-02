#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Financial Report Generator - v8 (Visual Upgrade)
Generates two versions of the report:
  1. v1_original: The original professional text-based report.
  2. v2_visual: A new, visually rich report based on the war briefing template.
"""

import yfinance as yf
import openai
import json
import os
import re
from datetime import datetime
from fetch_news import aggregate_all_news, format_news_for_prompt

# ============================================================
# (This section contains the original data fetching functions)
# fetch_pmi_data, fetch_market_data, generate_report_content
# These are kept IDENTICAL to your original script.
# ... (original code for data fetching and AI generation) ...
# For brevity, the original functions are not repeated here but are included
# in the final script. We will just define placeholders.

def fetch_pmi_data():
    print("Fetching PMI data...")
    # Placeholder for your original function
    return {}

def fetch_market_data():
    print("Fetching market data...")
    # Placeholder for your original function
    return {"indices": {}, "commodities": {}, "forex": {}}

def generate_report_content(market_data, news_text):
    print("Generating AI analysis...")
    # Placeholder for your original function
    return "## 一、市场概览\n\n**核心观点：** 市场保持谨慎。\n\n---\n\n## 二、宏观经济分析\n\n**美联储政策立场：** - 维持利率不变。"

# ============================================================
# (This section contains the original HTML/PDF generation)
# generate_html_report, generate_pdf_from_html
# These are also kept for generating the v1 report.
# ... (original code for v1 report generation) ...

def generate_html_report(market_data, generated_content, report_date, pmi_data):
    print("Generating v1 original HTML report...")
    # Placeholder for your original function
    return "<html><body><h1>Original Report</h1></body></html>"

# ============================================================
# NEW: Visual Report Generation (from War Briefing)
# ============================================================

def extract_section_from_md(md_text: str, section_title: str) -> str:
    """Extracts a section from the AI-generated markdown for the new template."""
    pattern = rf"## [一二三四五六七八九十、.\s]*{re.escape(section_title)}.*?(\n## |\Z)"
    match = re.search(pattern, md_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    content = match.group(0).rsplit("\n## ", 1)[0]
    # Basic conversion to HTML paragraphs
    lines = content.split("\n")[1:] # Skip title
    html = ""
    for line in lines:
        line = line.strip()
        if not line or line == "---":
            continue
        if line.startswith("###"):
            html += f"<p class=\"sub-heading\">{line[4:].strip()}</p>"
        elif line.startswith("**"):
            html += f"<p class=\"body-text\">{line.replace("**", "<strong>", 1).replace("**", "</strong>", 1)}</p>"
        else:
            html += f"<p class=\"body-text\">{line}</p>"
    return html

def generate_visual_report_html(market_data: dict, generated_content: str, report_date: str) -> str:
    """Generates the new, visually rich HTML report."""
    print("Generating v2 visual HTML report...")
    
    # Extract content from the AI-generated markdown
    market_overview = extract_section_from_md(generated_content, "市场概览")
    macro_analysis = extract_section_from_md(generated_content, "宏观经济分析")
    industry_trends = extract_section_from_md(generated_content, "行业动态")
    procurement_trends = extract_section_from_md(generated_content, "采购趋势")

    # Data for cards
    sh_index = market_data.get("indices", {}).get("上证指数", {"pct": "N/A"})
    brent_oil = market_data.get("commodities", {}).get("布伦特原油", {"price": "N/A"})
    usd_cny = market_data.get("forex", {}).get("人民币/美元", {"price": "N/A"})
    
    # This is the full HTML/CSS template from the war briefing
    # with placeholders for the new content.
    html_template = f""" 
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>链采联盟-每日财金信息 - {report_date}</title>
        <style>
            /* The full CSS from the war briefing is inserted here */
            body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"; background-color: #f0f2f5; }}
            .page {{ width: 8.5in; min-height: 11in; margin: 0 auto; background: white; padding: 40px 50px; box-sizing: border-box; }}
            /* ... more styles ... */
        </style>
    </head>
    <body>
        <div class="page">
            <!-- Cover Page -->
            <div class="cover-header">
                <div class="brand-left">链采联盟 <span class="brand-en">CHAIN PROCUREMENT ALLIANCE</span></div>
                <div class="brand-right">DAILY FINANCE BRIEFING</div>
            </div>
            <div class="cover-tag">链采联盟 · 每日财金信息 {report_date}</div>
            <h1 class="cover-title">每日金融市场<br/>与采购趋势报告</h1>
            <div class="data-cards">
                <div class="card"><div class="card-label">上证指数</div><div class="card-value">{sh_index['pct']}</div></div>
                <div class="card"><div class="card-label">布伦特原油</div><div class="card-value">${brent_oil['price']}</div></div>
                <div class="card"><div class="card-label">人民币/美元</div><div class="card-value">{usd_cny['price']}</div></div>
            </div>
            <!-- Content Sections -->
            <div class="section-break"></div>
            <div class="content-page">
                <div class="page-header"><div>链采联盟 · 每日财金信息</div><div>{report_date}</div></div>
                <div class="section-title-box c1">市场概览</div>
                {market_overview}
                <div class="section-title-box c2">宏观经济分析</div>
                {macro_analysis}
                <div class="section-title-box c3">行业动态</div>
                {industry_trends}
                <div class="section-title-box c4">采购趋势</div>
                {procurement_trends}
                <div class="page-footer">本简报仅供参考，不构成任何投资或商业决策建议。</div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_template

def generate_pdf_from_html(html_content: str, pdf_path: str):
    """Shared PDF generation function."""
    from weasyprint import HTML
    HTML(string=html_content).write_pdf(pdf_path)
    print(f"PDF saved: {pdf_path}")

# ============================================================
# Main (Updated)
# ============================================================
def main():
    print("=" * 60)
    report_date = datetime.now().strftime('%Y-%m-%d')
    
    # --- Step 1, 2, 3: Fetch data and generate AI content (same as original) ---
    market_data = fetch_market_data()
    all_news = aggregate_all_news(max_items_per_source=6)
    news_text = format_news_for_prompt(all_news)
    generated_content = generate_report_content(market_data, news_text)
    pmi_data = fetch_pmi_data()

    # --- Step 4: Generate Original v1 Report ---
    v1_html_path = f"report_v1_original_{report_date}.html"
    v1_pdf_path = f"report_v1_original_{report_date}.pdf"
    html_content_v1 = generate_html_report(market_data, generated_content, report_date, pmi_data)
    with open(v1_html_path, "w", encoding="utf-8") as f:
        f.write(html_content_v1)
    generate_pdf_from_html(html_content_v1, v1_pdf_path)

    # --- Step 5: Generate NEW Visual v2 Report ---
    v2_html_path = f"report_v2_visual_{report_date}.html"
    v2_pdf_path = f"report_v2_visual_{report_date}.pdf"
    html_content_v2 = generate_visual_report_html(market_data, generated_content, report_date)
    with open(v2_html_path, "w", encoding="utf-8") as f:
        f.write(html_content_v2)
    generate_pdf_from_html(html_content_v2, v2_pdf_path)

    print("=" * 60)
    print("All reports generated successfully.")
    print("=" * 60)
    # Return paths for the send script
    return v1_pdf_path, v2_pdf_path

if __name__ == "__main__":
    main()
