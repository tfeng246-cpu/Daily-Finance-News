#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
News Aggregation Module
Fetches headlines and summaries from 20+ authoritative financial news sources via RSS.
"""

import feedparser
import json
import time
import socket
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import urllib.request

# Set global socket timeout
socket.setdefaulttimeout(8)

# ============================================================
# 24 Authoritative Financial News Sources
# ============================================================
RSS_SOURCES = [
    # --- Global Markets & Finance ---
    {"name": "Bloomberg Markets",       "url": "https://feeds.bloomberg.com/markets/news.rss",              "category": "global_markets"},
    {"name": "Financial Times",         "url": "https://www.ft.com/rss/home",                               "category": "global_markets"},
    {"name": "WSJ Markets",             "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",             "category": "global_markets"},
    {"name": "CNBC Top News",           "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",     "category": "global_markets"},
    {"name": "MarketWatch",             "url": "https://feeds.marketwatch.com/marketwatch/topstories/",     "category": "global_markets"},
    {"name": "Yahoo Finance",           "url": "https://finance.yahoo.com/rss/topfinstories",               "category": "global_markets"},
    {"name": "Barron's",                "url": "https://www.barrons.com/xml/rss/3_7201.xml",                "category": "global_markets"},
    {"name": "Seeking Alpha",           "url": "https://seekingalpha.com/market_currents.xml",              "category": "global_markets"},
    # --- Macro & Research ---
    {"name": "The Economist Finance",   "url": "https://www.economist.com/finance-and-economics/rss.xml",  "category": "macro"},
    {"name": "IMF Blog",                "url": "https://www.imf.org/en/Blogs/rss",                         "category": "macro"},
    {"name": "Project Syndicate",       "url": "https://www.project-syndicate.org/rss/section/finance",    "category": "macro"},
    {"name": "World Bank Blog",         "url": "https://blogs.worldbank.org/en/rss.xml",                   "category": "macro"},
    # --- Central Banks & Policy ---
    {"name": "Federal Reserve",         "url": "https://www.federalreserve.gov/feeds/press_all.xml",       "category": "central_banks"},
    {"name": "ECB Press Releases",      "url": "https://www.ecb.europa.eu/rss/press.html",                 "category": "central_banks"},
    {"name": "BIS Speeches",            "url": "https://www.bis.org/rss/speeches.rss",                     "category": "central_banks"},
    # --- Commodities & Energy ---
    {"name": "OilPrice.com",            "url": "https://oilprice.com/rss/main",                            "category": "commodities"},
    {"name": "Reuters Commodities",     "url": "https://feeds.reuters.com/reuters/commoditiesNews",        "category": "commodities"},
    # --- Technology & AI ---
    {"name": "TechCrunch Fintech",      "url": "https://techcrunch.com/category/fintech/feed/",            "category": "tech"},
    {"name": "MIT Tech Review",         "url": "https://www.technologyreview.com/feed/",                   "category": "tech"},
    # --- Asia & China ---
    {"name": "SCMP Business",           "url": "https://www.scmp.com/rss/91/feed",                         "category": "china"},
    {"name": "Nikkei Asia",             "url": "https://asia.nikkei.com/rss/feed/nar",                     "category": "asia"},
    {"name": "Reuters Asia Markets",    "url": "https://feeds.reuters.com/reuters/asiaMarketsNews",        "category": "asia"},
    # --- Digital Assets ---
    {"name": "CoinDesk",                "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",          "category": "crypto"},
    # --- Business Intelligence ---
    {"name": "Business Insider Markets","url": "https://markets.businessinsider.com/rss/news",             "category": "global_markets"},
]

def fetch_rss_feed(source: dict, max_items: int = 6 ) -> list:
    """Fetch news items from a single RSS feed with timeout protection."""
    items = []
    try:
        feed = feedparser.parse(source["url"])
        if not feed.entries:
            return items
        
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link = entry.get("link", "")
            
            # Clean HTML from summary
            if summary:
                try:
                    soup = BeautifulSoup(summary, "html.parser")
                    summary = soup.get_text(separator=" ").strip()[:250]
                except Exception:
                    summary = summary[:250]
            
            if title:
                items.append({
                    "source": source["name"],
                    "category": source["category"],
                    "title": title,
                    "summary": summary,
                    "link": link,
                })
    except Exception as e:
        print(f"  [WARN] {source['name']}: {type(e).__name__}")
    
    return items

def aggregate_all_news(max_items_per_source: int = 6) -> dict:
    """Aggregate news from all sources, organized by category."""
    print(f"Fetching news from {len(RSS_SOURCES)} sources...")
    
    all_news = {
        "global_markets": [],
        "macro": [],
        "central_banks": [],
        "commodities": [],
        "tech": [],
        "china": [],
        "asia": [],
        "crypto": [],
    }
    
    successful_sources = 0
    
    for i, source in enumerate(RSS_SOURCES):
        print(f"  [{i+1:02d}/{len(RSS_SOURCES)}] {source['name']}...", end=" ", flush=True)
        items = fetch_rss_feed(source, max_items_per_source)
        if items:
            cat = source["category"]
            all_news[cat].extend(items)
            successful_sources += 1
            print(f"OK ({len(items)} items)")
        else:
            print("SKIP")
    
    print(f"\nSuccessfully fetched from {successful_sources}/{len(RSS_SOURCES)} sources.")
    total_items = sum(len(v) for v in all_news.values())
    print(f"Total news items collected: {total_items}")
    for cat, items in all_news.items():
        if items:
            print(f"  {cat}: {len(items)} items")
    
    return all_news

def format_news_for_prompt(all_news: dict) -> str:
    """Format aggregated news into a structured text for the AI prompt."""
    category_labels = {
        "global_markets": "全球市场动态",
        "macro": "宏观经济与研究",
        "central_banks": "央行政策动向",
        "commodities": "大宗商品与能源",
        "tech": "科技与AI行业",
        "china": "中国市场",
        "asia": "亚太市场",
        "crypto": "数字资产",
    }
    
    sections = []
    for cat, label in category_labels.items():
        items = all_news.get(cat, [])
        if not items:
            continue
        section_lines = [f"\n### {label} (来源: {', '.join(set(i['source'] for i in items[:8]))})"]
        for item in items[:8]:
            section_lines.append(f"- **{item['title']}**")
            if item['summary']:
                section_lines.append(f"  {item['summary'][:200]}")
        sections.append("\n".join(section_lines))
    
    return "\n".join(sections)

if __name__ == "__main__":
    all_news = aggregate_all_news()
    formatted = format_news_for_prompt(all_news)
    print("\n--- Sample of Formatted News ---")
    print(formatted[:3000])
    
    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    print("\nNews data saved to news_data.json")
