#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Financial Report Generator - v7
Professional investment research report format matching reference design.
"""

import yfinance as yf
import openai
import json
import os
import re
from datetime import datetime
from fetch_news import aggregate_all_news, format_news_for_prompt


# ============================================================
# PMI Data Fetching (via Trading Economics real-time scraping)
# ============================================================
def _parse_te_pmi_description(desc: str) -> dict:
    """
    Parse Trading Economics meta description to extract PMI value, previous value, and date.
    Example: 'Manufacturing PMI in China increased to 50.30 points in January from 50.10 points in December of 2025.'
    """
    import re
    result = {}
    # Extract current value
    m = re.search(r'(?:increased|decreased|rose|fell|edged|climbed|dropped|unchanged)\s+to\s+([\d.]+)\s+points?\s+in\s+(\w+)', desc, re.IGNORECASE)
    if not m:
        m = re.search(r'(?:stands?|remained?|was)\s+at\s+([\d.]+)\s+points?\s+in\s+(\w+)', desc, re.IGNORECASE)
    if not m:
        m = re.search(r'([\d.]+)\s+points?\s+in\s+(\w+)', desc, re.IGNORECASE)
    if m:
        result['value'] = float(m.group(1))
        month_str = m.group(2)
        month_map = {'January':'01','February':'02','March':'03','April':'04','May':'05','June':'06',
                     'July':'07','August':'08','September':'09','October':'10','November':'11','December':'12'}
        month_num = month_map.get(month_str, '01')
        # The description pattern is: "increased to X in MONTH from Y in PREV_MONTH of YEAR"
        # The year mentioned ("of 2025") refers to the PREVIOUS month, not the current month.
        # We need to infer the current month's year correctly.
        from datetime import datetime
        now = datetime.now()
        yr_match = re.search(r'of\s+(\d{4})', desc)
        prev_year = int(yr_match.group(1)) if yr_match else now.year
        # If current month number < previous month number, current month is in the next year
        prev_month_match = re.search(r'from\s+[\d.]+\s+points?\s+in\s+(\w+)\s+of', desc, re.IGNORECASE)
        if prev_month_match:
            prev_month_str = prev_month_match.group(1)
            prev_month_num = int(month_map.get(prev_month_str, '01'))
            curr_month_num = int(month_num)
            if curr_month_num < prev_month_num:
                year = str(prev_year + 1)  # current month rolled over to next year
            else:
                year = str(prev_year)
        else:
            year = str(prev_year)
        result['date'] = f"{year}-{month_num}"
    # Extract previous value
    p = re.search(r'from\s+([\d.]+)\s+points?', desc, re.IGNORECASE)
    if p:
        result['prev'] = float(p.group(1))
    return result


def _scrape_te_pmi(name: str, url: str) -> dict:
    """Scrape a single PMI indicator from Trading Economics."""
    import requests
    from bs4 import BeautifulSoup
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    meta = soup.find('meta', {'name': 'description'})
    if not meta:
        return None
    desc = meta.get('content', '')
    parsed = _parse_te_pmi_description(desc)
    if 'value' not in parsed:
        return None
    return {'name': name, **parsed}


def fetch_pmi_data() -> dict:
    """Fetch latest PMI data from Trading Economics (real-time web scraping).
    Data is always current - reflects the most recently published official PMI figures.
    Sources: NBS China, Caixin/S&P Global, ISM (US), S&P Global (Euro Area)
    """
    print("Fetching PMI data from Trading Economics (real-time)...")
    pmi = {}

    pmi_sources = [
        ('cn_mfg',  '中国制造业PMI（官方·国家统计局）',  'https://tradingeconomics.com/china/manufacturing-pmi'),
        ('cn_svc',  '中国非制造业PMI（官方·国家统计局）', 'https://tradingeconomics.com/china/non-manufacturing-pmi'),
        ('cx_mfg',  '中国制造业PMI（财新·S&P Global）',  'https://tradingeconomics.com/china/caixin-manufacturing-pmi'),
        ('cx_svc',  '中国服务业PMI（财新·S&P Global）',  'https://tradingeconomics.com/china/caixin-services-pmi'),
        ('us_mfg',  '美国制造业PMI（ISM）',               'https://tradingeconomics.com/united-states/manufacturing-pmi'),
        ('eu_mfg',  '欧元区制造业PMI（S&P Global）',      'https://tradingeconomics.com/euro-area/manufacturing-pmi'),
    ]

    for key, name, url in pmi_sources:
        try:
            row = _scrape_te_pmi(name, url)
            if row:
                pmi[key] = row
                print(f"  [PMI] {key}: {row['value']} ({row.get('date','?')})")
            else:
                print(f"  [PMI] {key}: no data parsed")
        except Exception as e:
            print(f"  [PMI] {key} error: {e}")

    print(f"PMI data fetched: {len(pmi)} indicators")
    return pmi


def build_pmi_block_html(pmi_data: dict) -> str:
    """Build the PMI summary block HTML to display below the report title."""
    if not pmi_data:
        return ""

    items_html = ""
    for key, item in pmi_data.items():
        val = item['value']
        prev = item['prev']
        date_str = item['date']
        name = item['name']

        # Determine status color and arrow
        if val >= 50:
            status_color = "#16a34a"  # green - expansion
            status_text = "扩张"
        else:
            status_color = "#dc2626"  # red - contraction
            status_text = "收缩"

        # Change vs previous
        if prev is not None:
            diff = val - prev
            if diff > 0:
                arrow = "▲"
                diff_color = "#16a34a"
            elif diff < 0:
                arrow = "▼"
                diff_color = "#dc2626"
            else:
                arrow = "—"
                diff_color = "#888"
            diff_str = f'<span style="color:{diff_color};font-size:12px;">{arrow}{abs(diff):.1f}</span>'
        else:
            diff_str = ""

        items_html += f"""
        <div class="pmi-item">
            <div class="pmi-name">{name}</div>
            <div class="pmi-value" style="color:{status_color};">{val:.1f}</div>
            <div class="pmi-meta">{diff_str} &nbsp;<span class="pmi-status" style="background:{status_color};">{status_text}</span></div>
            <div class="pmi-date">{date_str}</div>
        </div>"""

    return f"""
    <div class="pmi-block">
        <div class="pmi-block-title">采购经理人指数（PMI）</div>
        <div class="pmi-grid">{items_html}
        </div>
    </div>"""

# ============================================================
# Market Data Configuration
# ============================================================
INDEX_TICKERS = {
    "上证指数": "000001.SS",
    "深证成指": "399001.SZ",
    "创业板指": "399006.SZ",
    "道琼斯": "^DJI",
    "纳斯达克": "^IXIC",
    "标普500": "^GSPC",
    "恒生指数": "^HSI",
    "日经225": "^N225",
}

COMMODITY_TICKERS = {
    "黄金": "GC=F",
    "原油WTI": "CL=F",
    "布伦特原油": "BZ=F",
    "铜": "HG=F",
    "白银": "SI=F",
}

FOREX_TICKERS = {
    "美元指数": "DX-Y.NYB",
    "人民币/美元": "CNY=X",
    "欧元/美元": "EURUSD=X",
    "美元/日元": "JPY=X",
    "英镑/美元": "GBPUSD=X",
}

# ============================================================
# Market Data Fetching
# ============================================================
def fetch_market_data() -> dict:
    print("Fetching market data from Yahoo Finance...")
    data = {"indices": {}, "commodities": {}, "forex": {}}

    def get_ticker_data(ticker_dict, category):
        for name, ticker in ticker_dict.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="2d")
                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    last_price = hist['Close'].iloc[-1]
                elif len(hist) == 1:
                    last_price = hist['Close'].iloc[-1]
                    prev_close = last_price
                else:
                    raise ValueError("No data")
                change = last_price - prev_close
                pct = (change / prev_close) * 100 if prev_close else 0
                is_up = pct >= 0
                data[category][name] = {
                    "price": f"{last_price:.2f}",
                    "change": f"{change:+.2f}",
                    "pct": f"{pct:+.2f}%",
                    "is_up": int(is_up) if is_up is not None else None,
                    "display": f"{last_price:.2f} ({pct:+.2f}%)"
                }
            except Exception as e:
                print(f"  [WARN] {name}: {e}")
                data[category][name] = {
                    "price": "N/A", "change": "N/A", "pct": "N/A",
                    "is_up": -1, "display": "N/A"
                }

    get_ticker_data(INDEX_TICKERS, "indices")
    get_ticker_data(COMMODITY_TICKERS, "commodities")
    get_ticker_data(FOREX_TICKERS, "forex")
    print("Market data fetching complete.")
    return data


# ============================================================
# AI Content Generation
# ============================================================
def generate_report_content(market_data: dict, news_text: str) -> str:
    print("Generating AI analysis with multi-source news data...")

    indices_str = "  ".join([f"{k}: {v['display']}" for k, v in market_data['indices'].items()])
    commodities_str = "  ".join([f"{k}: {v['display']}" for k, v in market_data['commodities'].items()])
    forex_str = "  ".join([f"{k}: {v['display']}" for k, v in market_data['forex'].items()])
    today = datetime.now().strftime('%Y年%m月%d日')

    prompt = f"""你是一位顶级专业金融分析师，服务于中国高净值投资者和机构客户。今天是{today}。

请根据以下来自全球20+权威信息渠道的最新新闻资讯和实时市场数据，生成一份高质量的链采联盟-每日财经信息报告。

## 今日实时市场数据

主要股票指数：{indices_str}
大宗商品：{commodities_str}
外汇市场：{forex_str}

## 来自28+权威渠道的最新新闻资讯
（来源：Bloomberg、Financial Times、WSJ、CNBC、MarketWatch、The Economist、Federal Reserve、ECB、BIS、OilPrice、TechCrunch、MIT Tech Review、SCMP、Nikkei Asia、CoinDesk、Seeking Alpha、Yahoo Finance、Supply Chain Dive、Procurement Magazine、Spend Matters、Logistics Management等）

{news_text}

---

## 严格按照以下格式输出报告

请直接输出以下8个章节的内容，使用Markdown格式，不要有任何额外说明或前言。

**格式规范（非常重要）：**
- 子标题下的内容格式为：**粗体标签**：- 要点1 - 要点2 - 要点3（同一行，用" - "分隔）
- 不要把每个要点单独放一行，要紧凑地写在同一段落里
- 数据要精确，引用新闻中的具体数字

---

## 一、市场概览

（写2-3段，约150字，综合分析今日全球市场整体表现，结合指数涨跌数据和最重要的新闻事件）

**核心观点：**（一句话总结今日市场最核心主题和投资启示）

---

## 二、宏观经济分析（800字）

### 2.1 全球流动性环境

**美联储政策立场：** - （最新CPI/就业数据解读）- （FedWatch降息概率）- （官员最新表态）

**欧洲央行动向：** - （最新政策动态）- （通胀数据）- （对全球资本流动的影响）

**中国货币政策：** - （社融/M2数据）- （LPR/存款准备金率动向）- （结构性政策工具）

### 2.2 经济景气度

**美国经济：** - （就业/消费/PMI最新数据）- （软着陆/衰退概率判断）- （企业盈利展望）

**中国经济：** - （消费/投资/出口数据）- （房地产市场进展）- （政策刺激效果评估）

**欧洲经济：** - （PMI/通胀数据）- （能源价格影响）- （经济复苏前景）

### 2.3 重大政策事件

**中美关系：** - （最新外交/贸易动态）- （市场影响评估）- （后续走势判断）

**产业政策：** - （芯片/AI/新能源等战略产业最新政策）- （各国政策博弈）- （投资机会与风险）

---

## 三、行业动态（800字）

### 3.1 AI与人工智能

**产业进展：** - （大模型/算力最新突破）- （头部公司最新动态）- （中国AI产业规模数据）

**资本支出动向：** - （科技巨头AI投资计划）- （投资回报率争议）- （分析师观点）

**应用落地：** - （企业级AI应用进展）- （新兴应用场景）- （监管政策动向）

### 3.2 新能源与汽车

**市场表现：** - （中国新能源汽车销量数据）- （头部车企最新动态）- （海外市场进展）

**政策环境：** - （补贴政策变化）- （欧美贸易壁垒）- （行业竞争格局）

**技术趋势：** - （固态电池/智能驾驶进展）- （车企与科技公司合作）- （2026年关键节点）

### 3.3 半导体与科技

**供需格局：** - （AI芯片供需现状）- （成熟制程/先进制程分化）- （交付周期变化）

**技术突破：** - （最新工艺/封装技术进展）- （国产替代进程）- （重要研究成果）

**政策与竞争：** - （美国出口管制最新动态）- （中国半导体政策支持）- （台积电/英伟达最新动态）

---

## 四、公司聚焦（600字）

（从今日新闻中选取3个最热门、最具投资价值的公司或事件进行深度分析，每个约200字）

### 4.1 [公司名称/事件标题]

**最新进展：** - （核心事件描述）- （关键数据）- （时间节点）

**业务影响：** - （对公司业务的具体影响）- （竞争格局变化）- （市场反应）

**投资价值：** - （估值判断）- （风险因素）- （建议关注点）

### 4.2 [公司名称/事件标题]

**最新进展：** - （核心事件描述）- （关键数据）- （时间节点）

**业务影响：** - （对公司业务的具体影响）- （竞争格局变化）- （市场反应）

**投资价值：** - （估值判断）- （风险因素）- （建议关注点）

### 4.3 [公司名称/事件标题]

**最新进展：** - （核心事件描述）- （关键数据）- （时间节点）

**业务影响：** - （对公司业务的具体影响）- （竞争格局变化）- （市场反应）

**投资价值：** - （估值判断）- （风险因素）- （建议关注点）

---

## 五、关键人物观点（300字）

（从今日新闻中选取5位最重要的政治领袖/央行官员/商界领袖，每人3个要点，用"·"分隔写在同一段）

### [人物姓名]（[职位]）

· （要点1） · （要点2） · （要点3）

### [人物姓名]（[职位]）

· （要点1） · （要点2） · （要点3）

### [人物姓名]（[职位]）

· （要点1） · （要点2） · （要点3）

### [人物姓名]（[职位]）

· （要点1） · （要点2） · （要点3）

### [人物姓名]（[职位]）

· （要点1） · （要点2） · （要点3）

---

## 六、采购趋势（600字）

（基于今日采购与供应链新闻，分析以下四大采购类别的最新趋势，每个类别约150字）

### 6.1 IT与数字化采购

**市场动态：** - （IT硬件/软件/云服务采购最新趋势）- （AI相关IT采购需求变化）- （主要供应商动态）

**价格走势：** - （IT设备/服务价格变化）- （汇率对IT采购成本的影响）- （采购策略建议）

**风险提示：** - （供应链风险）- （技术迭代风险）- （合规风险）

### 6.2 物流与运输采购

**运价动态：** - （集装箱运价/空运价格最新数据）- （主要航线运价变化）- （港口拥堵情况）

**供应链动态：** - （全球供应链最新压力点）- （物流成本变化趋势）- （主要物流商动态）

**采购建议：** - （锁价时机判断）- （多元化物流策略）- （风险对冲方法）

### 6.3 大宗材料采购

**价格走势：** - （钢铁/铜/铝/化工原料最新价格）- （与上周/上月对比）- （影响价格的核心因素）

**供需格局：** - （主要产区供应情况）- （下游需求变化）- （库存水平）

**采购策略：** - （当前是否适合锁价）- （套期保值建议）- （替代材料选项）

### 6.4 房地产与设施采购

**市场动态：** - （商业地产租金/价格走势）- （主要城市写字楼空置率）- （工业用地/仓储价格）

**政策影响：** - （房地产相关政策最新动态）- （对企业设施采购的影响）- （市场机会与风险）

**采购建议：** - （租赁vs购买决策参考）- （选址优化建议）- （成本控制策略）

---

## 七、投资策略建议（200字）

### 资产配置建议

**看好方向：** 1. [方向1]：（理由） 2. [方向2]：（理由） 3. [方向3]：（理由） 4. [方向4]：（理由）

**规避风险：** 1. [风险1]：（原因） 2. [风险2]：（原因） 3. [风险3]：（原因）

### 风险提示

· （风险1） · （风险2） · （风险3） · （风险4）

---

请注意：
1. 所有内容必须基于上述提供的真实新闻数据，不得凭空捏造
2. 所有新闻必须是今日或昨日的最新信息，严禁使用超过48小时的历史旧闻
3. 公司聚焦和关键人物观点必须来自今日新闻中实际出现的公司和人物
4. 数据引用必须准确，使用新闻中提到的具体数字
5. 采购趋势板块必须结合大宗商品价格数据和供应链新闻，给出具体的价格数据和趋势判断
6. 语言专业、简洁、有洞察力，避免空话套话
7. 直接输出Markdown内容，不要有任何额外说明"""

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
    model_name = os.environ.get("OPENAI_MODEL", "Qwen/Qwen2.5-72B-Instruct")
    client = openai.OpenAI(base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "你是一位服务于中国高净值投资者的顶级金融分析师，擅长整合全球多渠道信息，提供深度、准确、有洞察力的市场分析报告。你的报告风格专业、简洁、数据驱动，深受机构投资者信赖。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=5000,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        print("AI analysis generation complete.")
        return content
    except Exception as e:
        print(f"Error generating AI content: {e}")
        return f"## 报告生成失败\n\n错误信息：{e}\n\n请检查 OPENAI_API_KEY 和 OPENAI_BASE_URL 是否正确配置。"


# ============================================================
# Markdown to HTML (precise reference-matching renderer)
# ============================================================
def process_inline(text: str) -> str:
    """Process inline markdown: **bold**, *italic*"""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text


def markdown_to_html(md_text: str) -> str:
    """
    Convert markdown to HTML matching the reference document style exactly.
    Key rules:
    - ## headings -> h2 with left blue bar
    - ### headings -> h3 bold dark navy
    - Lines starting with · -> bullet list items
    - --- -> section divider
    - Regular paragraphs -> <p>
    """
    lines = md_text.split('\n')
    html_lines = []
    in_bullet = False

    for line in lines:
        stripped = line.strip()

        # H2: ## 一、市场概览
        if re.match(r'^## ', line):
            if in_bullet:
                html_lines.append('</ul>')
                in_bullet = False
            title = line[3:].strip()
            html_lines.append(f'<h2 class="section-title">{process_inline(title)}</h2>')

        # H3: ### 2.1 ...
        elif re.match(r'^### ', line):
            if in_bullet:
                html_lines.append('</ul>')
                in_bullet = False
            title = line[4:].strip()
            html_lines.append(f'<h3 class="subsection-title">{process_inline(title)}</h3>')

        # Horizontal rule
        elif stripped == '---':
            if in_bullet:
                html_lines.append('</ul>')
                in_bullet = False
            html_lines.append('<hr class="section-divider">')

        # Bullet items starting with · (used in key figures section)
        elif stripped.startswith('·') or stripped.startswith('• ') or re.match(r'^- ', line):
            if not in_bullet:
                html_lines.append('<ul class="bullet-list">')
                in_bullet = True
            if stripped.startswith('·'):
                # Multiple bullets on one line separated by ·
                parts = [p.strip() for p in stripped.split('·') if p.strip()]
                for part in parts:
                    html_lines.append(f'<li>{process_inline(part)}</li>')
            elif stripped.startswith('• '):
                content = stripped[2:].strip()
                html_lines.append(f'<li>{process_inline(content)}</li>')
            else:
                content = line[2:].strip()
                html_lines.append(f'<li>{process_inline(content)}</li>')

        # Empty line
        elif stripped == '':
            if in_bullet:
                html_lines.append('</ul>')
                in_bullet = False
            html_lines.append('')

        # Regular paragraph
        else:
            if in_bullet:
                html_lines.append('</ul>')
                in_bullet = False
            html_lines.append(f'<p>{process_inline(stripped)}</p>')

    if in_bullet:
        html_lines.append('</ul>')

    return '\n'.join(html_lines)


# ============================================================
# Market Data Table HTML (color-coded)
# ============================================================
def build_market_table(market_data: dict) -> str:
    """Build a clean color-coded market data table."""

    def row(name, info):
        pct_str = info.get('pct', 'N/A')
        price_str = info.get('price', 'N/A')
        change_str = info.get('change', 'N/A')
        is_up = info.get('is_up', None)
        if is_up == 1:
            color_class = 'up'
            arrow = '▲'
        elif is_up == 0:
            color_class = 'down'
            arrow = '▼'
        else:
            color_class = 'neutral'
            arrow = '—'
        return f'''<tr>
            <td class="col-name">{name}</td>
            <td class="col-price">{price_str}</td>
            <td class="col-change {color_class}">{arrow} {change_str}</td>
            <td class="col-pct {color_class}">{pct_str}</td>
        </tr>'''

    indices_rows = ''.join([row(k, v) for k, v in market_data['indices'].items()])
    commodity_rows = ''.join([row(k, v) for k, v in market_data['commodities'].items()])
    forex_rows = ''.join([row(k, v) for k, v in market_data['forex'].items()])

    return f'''
<div class="market-tables">
  <div class="market-table-group">
    <div class="table-label">主要股票指数</div>
    <table class="market-table">
      <thead><tr><th>指数</th><th>最新价</th><th>涨跌额</th><th>涨跌幅</th></tr></thead>
      <tbody>{indices_rows}</tbody>
    </table>
  </div>
  <div class="market-table-row">
    <div class="market-table-group half">
      <div class="table-label">大宗商品</div>
      <table class="market-table">
        <thead><tr><th>品种</th><th>最新价</th><th>涨跌额</th><th>涨跌幅</th></tr></thead>
        <tbody>{commodity_rows}</tbody>
      </table>
    </div>
    <div class="market-table-group half">
      <div class="table-label">外汇市场</div>
      <table class="market-table">
        <thead><tr><th>品种</th><th>最新价</th><th>涨跌额</th><th>涨跌幅</th></tr></thead>
        <tbody>{forex_rows}</tbody>
      </table>
    </div>
  </div>
</div>'''


# ============================================================
# HTML Report Generation
# ============================================================
def generate_html_report(market_data: dict, generated_content: str, report_date: str, pmi_data: dict = None) -> str:
    if pmi_data is None:
        pmi_data = {}
    content_html = markdown_to_html(generated_content)
    market_table_html = build_market_table(market_data)

    # Inline data for appendix (matching reference style)
    indices_inline = " &nbsp;-&nbsp; ".join([
        f"<strong>{k}</strong>：{v['display']}" for k, v in market_data['indices'].items()
    ])
    commodities_inline = " &nbsp;-&nbsp; ".join([
        f"<strong>{k}</strong>：{v['display']}" for k, v in market_data['commodities'].items()
    ])
    forex_inline = " &nbsp;-&nbsp; ".join([
        f"<strong>{k}</strong>：{v['display']}" for k, v in market_data['forex'].items()
    ])

    generation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    pmi_block_html = build_pmi_block_html(pmi_data)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>链采联盟-每日财金信息 - {report_date}</title>
    <style>
        /* ===== Reset & Base ===== */
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'PingFang SC', 'Microsoft YaHei', 'SimHei',
                         'Noto Sans CJK SC', 'WenQuanYi Zen Hei',
                         'Droid Sans Fallback', sans-serif;
            background: #ffffff;
            color: #222222;
            font-size: 14.5px;
            line-height: 1.85;
        }}
        .page {{
            max-width: 900px;
            margin: 0 auto;
            padding: 52px 68px 64px;
        }}

        /* ===== PMI Block ===== */
        .pmi-block {{
            margin: 18px 0 28px;
            padding: 16px 20px;
            background: #f8faff;
            border: 1px solid #dbeafe;
            border-radius: 6px;
        }}
        .pmi-block-title {{
            font-size: 13px;
            font-weight: 700;
            color: #1d4ed8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
            border-bottom: 1px solid #dbeafe;
            padding-bottom: 8px;
        }}
        .pmi-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .pmi-item {{
            flex: 1;
            min-width: 160px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 5px;
            padding: 10px 14px;
        }}
        .pmi-name {{
            font-size: 12px;
            color: #555;
            margin-bottom: 4px;
        }}
        .pmi-value {{
            font-size: 26px;
            font-weight: 800;
            line-height: 1.2;
        }}
        .pmi-meta {{
            font-size: 12px;
            margin-top: 4px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .pmi-status {{
            color: #fff;
            font-size: 11px;
            padding: 1px 6px;
            border-radius: 3px;
            font-weight: 600;
        }}
        .pmi-date {{
            font-size: 11px;
            color: #999;
            margin-top: 4px;
        }}

        /* ===== Report Header ===== */
        .report-header {{
            margin-bottom: 32px;
        }}
        .report-title {{
            font-size: 26px;
            font-weight: 800;
            color: #0f2a4a;
            letter-spacing: 0.5px;
            margin-bottom: 10px;
        }}
        .title-rule {{
            border: none;
            border-top: 2.5px solid #1d4ed8;
            margin: 0;
        }}

        /* ===== Section Headings ===== */
        h2.section-title {{
            font-size: 20px;
            font-weight: 800;
            color: #0f2a4a;
            border-left: 5px solid #1d4ed8;
            padding-left: 14px;
            margin: 44px 0 16px;
            line-height: 1.4;
        }}
        h3.subsection-title {{
            font-size: 15px;
            font-weight: 700;
            color: #0f2a4a;
            margin: 26px 0 10px;
            padding: 0;
        }}

        /* ===== Body Text ===== */
        p {{
            margin: 8px 0;
            color: #2d2d2d;
            text-align: justify;
            font-size: 14.5px;
        }}
        strong {{
            color: #0f2a4a;
            font-weight: 700;
        }}

        /* ===== Bullet List ===== */
        ul.bullet-list {{
            list-style: none;
            padding: 0;
            margin: 6px 0;
        }}
        ul.bullet-list li {{
            padding: 3px 0 3px 18px;
            position: relative;
            font-size: 14px;
            color: #2d2d2d;
            line-height: 1.75;
        }}
        ul.bullet-list li::before {{
            content: "·";
            position: absolute;
            left: 4px;
            color: #1d4ed8;
            font-weight: 900;
            font-size: 18px;
            line-height: 1.4;
        }}

        /* ===== Section Divider ===== */
        hr.section-divider {{
            border: none;
            border-top: 1px solid #d1d5db;
            margin: 36px 0;
        }}

        /* ===== Market Data Tables ===== */
        .market-tables {{
            margin: 20px 0 8px;
        }}
        .market-table-group {{
            margin-bottom: 18px;
        }}
        .market-table-group.half {{
            width: 48%;
        }}
        .market-table-row {{
            display: flex;
            gap: 4%;
            align-items: flex-start;
        }}
        .table-label {{
            font-size: 13px;
            font-weight: 700;
            color: #4b5563;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 4px;
        }}
        table.market-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
        }}
        table.market-table thead tr {{
            background: #f0f4f8;
        }}
        table.market-table th {{
            padding: 7px 10px;
            text-align: left;
            font-weight: 700;
            color: #374151;
            font-size: 12.5px;
            border-bottom: 1.5px solid #d1d5db;
        }}
        table.market-table td {{
            padding: 6px 10px;
            border-bottom: 1px solid #f0f0f0;
            color: #222222;
        }}
        table.market-table tr:hover td {{
            background: #f9fafb;
        }}
        td.col-name {{
            font-weight: 600;
            color: #1a1a2e;
        }}
        td.col-price {{
            font-variant-numeric: tabular-nums;
        }}
        td.up {{ color: #dc2626; font-weight: 600; }}
        td.down {{ color: #16a34a; font-weight: 600; }}
        td.neutral {{ color: #6b7280; }}

        /* ===== Data Appendix (inline text style) ===== */
        .data-appendix {{
            margin-top: 8px;
        }}
        .data-row {{
            margin: 10px 0;
            font-size: 14px;
            color: #2d2d2d;
            line-height: 1.9;
        }}

        /* ===== Footer ===== */
        .report-footer {{
            margin-top: 40px;
            padding-top: 18px;
            border-top: 1px solid #d1d5db;
        }}
        .report-footer p {{
            margin: 5px 0;
            font-size: 12.5px;
            color: #6b7280;
        }}
        .report-footer strong {{
            color: #374151;
            font-weight: 600;
        }}

        /* ===== Print / PDF ===== */
        @media print {{
            body {{ font-size: 13px; line-height: 1.75; }}
            .page {{ padding: 24px 36px; max-width: 100%; }}
            h2.section-title {{ font-size: 17px; margin: 32px 0 12px; }}
            h3.subsection-title {{ font-size: 14px; }}
            table.market-table {{ font-size: 12px; }}
        }}
    </style>
</head>
<body>
<div class="page">

    <!-- ===== Header ===== -->
    <div class="report-header">
        <h1 class="report-title">链采联盟-每日财金信息 &nbsp;·&nbsp; {report_date}</h1>
        <hr class="title-rule">
    </div>

    <!-- ===== PMI Block ===== -->
    {pmi_block_html}

    <!-- ===== AI Generated Content ===== -->
    {content_html}

    <!-- ===== Market Data Tables (inserted before Data Appendix) ===== -->
    <hr class="section-divider">
    <h2 class="section-title">八、数据附录</h2>
    {market_table_html}

    <div class="data-appendix" style="margin-top:20px;">
        <div class="data-row">
            <strong>主要指数</strong>（截至{report_date}）：{indices_inline}
        </div>
        <div class="data-row">
            <strong>大宗商品</strong>：{commodities_inline}
        </div>
        <div class="data-row">
            <strong>外汇</strong>：{forex_inline}
        </div>
    </div>

    <!-- ===== Footer ===== -->
    <div class="report-footer">
        <hr class="section-divider" style="margin-bottom:14px;">
        <p><strong>报告生成时间：</strong>{generation_time}</p>
        <p><strong>数据来源：</strong>Bloomberg · Financial Times · WSJ · CNBC · MarketWatch · The Economist · Federal Reserve · ECB · BIS · OilPrice · TechCrunch · MIT Tech Review · SCMP · Nikkei Asia · CoinDesk · Seeking Alpha · Yahoo Finance · Business Insider · Supply Chain Dive · Procurement Magazine · Spend Matters · Logistics Management 等 28+ 权威来源</p>
        <p><strong>免责声明：</strong>本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。</p>
    </div>

</div>
</body>
</html>"""
    return html


# ============================================================
# PDF Generation (Chinese font support)
# ============================================================
def generate_pdf_from_html(html_content: str, pdf_path: str):
    from weasyprint import HTML, CSS

    font_css = CSS(string="""
        @font-face {
            font-family: 'CJKFont';
            src: local('Noto Sans CJK SC'), local('Noto Sans SC'),
                 local('WenQuanYi Zen Hei'), local('WenQuanYi Micro Hei'),
                 local('Droid Sans Fallback'), local('AR PL UMing CN');
        }
        body {
            font-family: 'CJKFont', 'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei',
                         'Noto Sans CJK SC', 'Droid Sans Fallback', sans-serif !important;
        }
        @page {
            size: A4;
            margin: 18mm 20mm 18mm 20mm;
        }
    """)

    HTML(string=html_content, base_url=".").write_pdf(pdf_path, stylesheets=[font_css])
    print(f"PDF saved: {pdf_path}")


# ============================================================
# NEW: Visual Report HTML Generator (v2 - Branded Cover)
# ============================================================

def _md_to_html_simple(md_text: str) -> str:
    """Lightweight markdown-to-HTML for the visual report body."""
    lines = md_text.split('\n')
    html_parts = []
    in_ul = False
    for line in lines:
        s = line.strip()
        if not s or s == '---':
            if in_ul:
                html_parts.append('</ul>')
                in_ul = False
            continue
        if s.startswith('## '):
            if in_ul:
                html_parts.append('</ul>')
                in_ul = False
            title = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s[3:])
            html_parts.append(f'<h3 class="vis-h2">{title}</h3>')
        elif s.startswith('### '):
            if in_ul:
                html_parts.append('</ul>')
                in_ul = False
            title = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s[4:])
            html_parts.append(f'<h4 class="vis-h3">{title}</h4>')
        elif s.startswith('- ') or s.startswith('· '):
            if not in_ul:
                html_parts.append('<ul class="vis-ul">')
                in_ul = True
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s[2:])
            html_parts.append(f'<li>{content}</li>')
        else:
            if in_ul:
                html_parts.append('</ul>')
                in_ul = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
            html_parts.append(f'<p class="vis-p">{content}</p>')
    if in_ul:
        html_parts.append('</ul>')
    return '\n'.join(html_parts)


def _extract_section(md_text: str, title_keyword: str) -> str:
    """Extract a section from AI markdown by title keyword."""
    pattern = rf'## [^\n]*{re.escape(title_keyword)}[^\n]*\n(.*?)(?=\n## |\Z)'
    m = re.search(pattern, md_text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ''


def _build_market_cards(market_data: dict) -> str:
    """Build 4 key market data cards for the visual cover."""
    cards = []
    items = [
        ('indices', '上证指数', '上证指数'),
        ('commodities', '布伦特原油', '布伦特原油'),
        ('forex', '人民币/美元', '人民币/美元'),
        ('commodities', '黄金', '黄金'),
    ]
    for category, key, label in items:
        info = market_data.get(category, {}).get(key, {})
        price = info.get('price', 'N/A')
        pct = info.get('pct', 'N/A')
        color = '#e74c3c' if info.get('is_up', 0) == 1 else '#27ae60'
        prefix = '$' if category == 'commodities' else ''
        cards.append(
            f'<div class="cstat">'
            f'<span class="v" style="color:{color};font-size:15px;">{prefix}{price}</span>'
            f'<span class="v2" style="color:{color};">{pct}</span>'
            f'<span class="l">{label}</span>'
            f'</div>'
        )
    return '\n'.join(cards)


def _build_market_summary_table(market_data: dict) -> str:
    """Build a compact market data table for the visual report."""
    def arrow(info):
        if info.get('is_up') == 1: return '▲', '#c0392b'
        if info.get('is_up') == 0: return '▼', '#27ae60'
        return '—', '#888'

    rows = ''
    all_items = (
        list(market_data.get('indices', {}).items()) +
        list(market_data.get('commodities', {}).items()) +
        list(market_data.get('forex', {}).items())
    )
    for name, info in all_items:
        arr, col = arrow(info)
        rows += (
            f'<tr>'
            f'<td class="td-name">{name}</td>'
            f'<td>{info.get("price", "N/A")}</td>'
            f'<td style="color:{col};font-weight:700;">{arr} {info.get("pct", "N/A")}</td>'
            f'</tr>'
        )
    return (
        f'<table class="vis-table">'
        f'<thead><tr><th>品种</th><th>最新价</th><th>涨跌幅</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
    )


def generate_visual_html_report(market_data: dict, generated_content: str, report_date: str, pmi_data: dict = None) -> str:
    """Generate the new visually rich PDF-optimized report (v2 - branded cover)."""
    print("Generating v2 visual HTML report...")
    if pmi_data is None:
        pmi_data = {}
    generation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    date_cn = datetime.now().strftime('%Y年%m月%d日')

    # Extract AI content sections
    sec1_html = _md_to_html_simple(_extract_section(generated_content, '市场概览'))
    sec2_html = _md_to_html_simple(_extract_section(generated_content, '宏观经济'))
    sec3_html = _md_to_html_simple(_extract_section(generated_content, '行业动态'))
    sec4_html = _md_to_html_simple(_extract_section(generated_content, '采购趋势'))
    sec5_html = _md_to_html_simple(_extract_section(generated_content, '投资策略'))

    market_cards = _build_market_cards(market_data)
    market_table = _build_market_summary_table(market_data)

    # PMI summary line
    pmi_line = ''
    if pmi_data:
        pmi_items = [
            f"{v['name']}: <strong>{v['value']:.1f}</strong>"
            for v in list(pmi_data.values())[:4]
        ]
        pmi_line = f'<div class="vis-pmi-bar">PMI 快览：{" &nbsp;|&nbsp; ".join(pmi_items)}</div>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "SimHei", Arial, sans-serif;
  background: #fff; color: #1a1a1a; font-size: 12.5px; line-height: 1.75;
}}
/* ═══ COVER ═══ */
.cover {{
  width: 210mm; height: 297mm; position: relative; overflow: hidden;
  page-break-after: always; background: #0a0a0a;
}}
.cover-bg {{
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 70% 30%, rgba(160,20,20,0.55) 0%, transparent 70%),
    radial-gradient(ellipse 50% 40% at 20% 80%, rgba(100,10,10,0.4) 0%, transparent 60%),
    linear-gradient(160deg, #0f0000 0%, #1a0000 40%, #0a0a0a 100%);
}}
.cover-texture {{
  position: absolute; inset: 0;
  background: repeating-linear-gradient(-55deg, transparent 0px, transparent 28px,
    rgba(255,255,255,0.018) 28px, rgba(255,255,255,0.018) 29px);
}}
.cover-stripe {{
  position: absolute; left: 0; top: 0; bottom: 0; width: 8px;
  background: linear-gradient(to bottom, #c0392b, #8b0000, #c0392b);
}}
.cover-topbar {{
  position: absolute; top: 0; left: 8px; right: 0; height: 56px;
  background: rgba(0,0,0,0.6); border-bottom: 1px solid rgba(192,57,43,0.4);
  display: flex; align-items: center; padding: 0 36px; gap: 16px;
}}
.topbar-logo {{ font-size: 15px; font-weight: 900; color: #d4a017; letter-spacing: 2px; }}
.topbar-sep {{ width: 1px; height: 20px; background: rgba(255,255,255,0.2); }}
.topbar-sub {{ font-size: 11px; color: rgba(255,255,255,0.45); letter-spacing: 1px; }}
.topbar-live {{ margin-left: auto; display: flex; align-items: center; gap: 7px; }}
.live-dot {{ width: 8px; height: 8px; background: #c0392b; border-radius: 50%; box-shadow: 0 0 6px #c0392b; }}
.live-text {{ font-size: 11px; font-weight: 700; color: #c0392b; letter-spacing: 2px; }}
.cover-main {{
  position: absolute; top: 56px; left: 8px; right: 0; bottom: 80px;
  padding: 44px 44px 32px; display: flex; flex-direction: column; justify-content: space-between;
}}
.push-label {{ display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }}
.push-tag {{ background: #c0392b; color: #fff; font-size: 11px; font-weight: 900; letter-spacing: 3px; padding: 5px 14px; border-radius: 2px; }}
.push-chain {{ font-size: 13px; font-weight: 700; color: #d4a017; letter-spacing: 1.5px; }}
.cover-headline {{ margin-bottom: 28px; }}
.eyebrow {{ font-size: 12px; color: rgba(255,255,255,0.35); letter-spacing: 3px; text-transform: uppercase; margin-bottom: 10px; }}
.cover-headline h1 {{ font-size: 46px; font-weight: 900; color: #fff; line-height: 1.1; margin-bottom: 8px; }}
.cover-headline h2 {{ font-size: 22px; font-weight: 700; color: #d4a017; line-height: 1.2; margin-bottom: 16px; }}
.cover-desc {{ font-size: 12px; color: rgba(255,255,255,0.45); line-height: 1.8; max-width: 420px; border-left: 2px solid rgba(192,57,43,0.5); padding-left: 14px; }}
.cover-stats {{ display: flex; gap: 12px; margin-bottom: 28px; }}
.cstat {{ flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-top: 2px solid #c0392b; border-radius: 4px; padding: 12px 10px; text-align: center; }}
.cstat .v {{ display: block; font-size: 20px; font-weight: 900; line-height: 1; margin-bottom: 3px; }}
.cstat .v2 {{ display: block; font-size: 12px; font-weight: 700; margin-bottom: 3px; }}
.cstat .l {{ font-size: 10px; color: rgba(255,255,255,0.4); }}
.cover-toc {{ display: flex; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; }}
.toc-item {{ flex: 1; padding: 10px 8px; text-align: center; border-right: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.03); }}
.toc-item:last-child {{ border-right: none; }}
.toc-num {{ display: block; font-size: 16px; font-weight: 900; color: rgba(192,57,43,0.7); line-height: 1; margin-bottom: 3px; }}
.toc-name {{ font-size: 10px; color: rgba(255,255,255,0.4); line-height: 1.4; }}
.cover-footer {{
  position: absolute; bottom: 0; left: 8px; right: 0; height: 80px;
  background: rgba(0,0,0,0.7); border-top: 1px solid rgba(192,57,43,0.3);
  display: flex; align-items: center; padding: 0 44px; justify-content: space-between;
}}
.cf-brand {{ font-size: 14px; font-weight: 700; color: #d4a017; letter-spacing: 1px; }}
.cf-sub {{ font-size: 10px; color: rgba(255,255,255,0.3); margin-top: 2px; }}
.cf-date {{ font-size: 12px; color: rgba(255,255,255,0.5); margin-bottom: 2px; }}
.cf-disc {{ font-size: 10px; color: rgba(255,255,255,0.25); }}
.deco-circle {{ position: absolute; border-radius: 50%; pointer-events: none; }}
.dc1 {{ width: 320px; height: 320px; right: -60px; top: 60px; border: 1px solid rgba(192,57,43,0.12); }}
.dc2 {{ width: 200px; height: 200px; right: 20px; top: 120px; border: 1px solid rgba(192,57,43,0.08); }}
.dc3 {{ width: 120px; height: 120px; right: 80px; top: 180px; background: rgba(192,57,43,0.06); }}
/* ═══ CONTENT PAGES ═══ */
.cpage {{
  width: 210mm; min-height: 297mm; padding: 0;
  page-break-after: always; position: relative; background: #fff;
}}
.cpage:last-child {{ page-break-after: auto; }}
.ph {{
  height: 46px; background: #0f0000;
  display: flex; align-items: center; padding: 0 36px; justify-content: space-between;
  border-bottom: 2px solid #c0392b;
}}
.ph-brand {{ font-size: 11px; font-weight: 700; color: #d4a017; letter-spacing: 2px; }}
.ph-sub {{ font-size: 11px; color: rgba(255,255,255,0.35); letter-spacing: 1px; }}
.ph-date {{ font-size: 10px; color: rgba(255,255,255,0.25); }}
.pbody {{ padding: 20px 36px 52px; }}
.sec-banner {{ display: flex; align-items: stretch; margin-bottom: 20px; border-radius: 6px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }}
.sec-num {{ width: 56px; display: flex; align-items: center; justify-content: center; flex-direction: column; padding: 12px 0; flex-shrink: 0; background: #c0392b; }}
.sec-num.orange {{ background: #d35400; }}
.sec-num.blue {{ background: #1a6fa8; }}
.sec-num.gold {{ background: #b8860b; }}
.sec-num.teal {{ background: #148f77; }}
.sec-num.gray {{ background: #555; }}
.sec-num-text {{ font-size: 20px; font-weight: 900; color: rgba(255,255,255,0.9); line-height: 1; }}
.sec-num-label {{ font-size: 8px; color: rgba(255,255,255,0.5); letter-spacing: 1px; margin-top: 2px; }}
.sec-title {{ flex: 1; padding: 12px 18px; display: flex; flex-direction: column; justify-content: center; background: linear-gradient(135deg, #1a0000 0%, #2a0000 100%); }}
.sec-title.orange {{ background: linear-gradient(135deg, #1a0800 0%, #2a1000 100%); }}
.sec-title.blue {{ background: linear-gradient(135deg, #00101a 0%, #001828 100%); }}
.sec-title.gold {{ background: linear-gradient(135deg, #0f0a00 0%, #1a1200 100%); }}
.sec-title.teal {{ background: linear-gradient(135deg, #001a14 0%, #002a1e 100%); }}
.sec-title.gray {{ background: linear-gradient(135deg, #111 0%, #222 100%); }}
.sec-title h2 {{ font-size: 16px; font-weight: 900; color: #fff; margin-bottom: 2px; }}
.sec-title p {{ font-size: 10px; color: rgba(255,255,255,0.35); }}
.vis-h2 {{ font-size: 13px; font-weight: 800; color: #0f2a4a; border-left: 4px solid #c0392b; padding-left: 10px; margin: 16px 0 8px; }}
.vis-h3 {{ font-size: 12px; font-weight: 700; color: #c0392b; margin: 12px 0 6px; }}
.vis-p {{ font-size: 12px; color: #2a2a2a; line-height: 1.8; margin-bottom: 8px; text-align: justify; }}
.vis-ul {{ list-style: none; padding: 0; margin: 4px 0 10px; }}
.vis-ul li {{ font-size: 11.5px; color: #333; line-height: 1.7; padding: 2px 0 2px 16px; position: relative; }}
.vis-ul li::before {{ content: "·"; position: absolute; left: 4px; color: #c0392b; font-weight: 900; font-size: 16px; line-height: 1.3; }}
.vis-table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin: 10px 0; }}
.vis-table thead tr {{ background: #0f0000; }}
.vis-table th {{ color: #d4a017; font-weight: 700; padding: 7px 10px; text-align: left; font-size: 10px; letter-spacing: 0.5px; }}
.vis-table td {{ padding: 6px 10px; border-bottom: 1px solid #f0f0f0; }}
.vis-table .td-name {{ font-weight: 600; color: #1a1a2e; }}
.vis-table tr:nth-child(even) td {{ background: #fafafa; }}
.vis-pmi-bar {{ background: #f0f4ff; border: 1px solid #c8d8f5; border-radius: 4px; padding: 8px 14px; font-size: 11px; color: #1d4ed8; margin-bottom: 14px; }}
.pfoot {{
  position: absolute; bottom: 0; left: 0; right: 0; height: 30px;
  background: #0f0000; display: flex; align-items: center; padding: 0 36px; justify-content: space-between;
}}
.pf-brand {{ font-size: 10px; color: #d4a017; font-weight: 700; letter-spacing: 1px; }}
.pf-disc {{ font-size: 9px; color: rgba(255,255,255,0.25); }}
</style>
</head>
<body>

<!-- COVER -->
<div class="cover">
  <div class="cover-bg"></div>
  <div class="cover-texture"></div>
  <div class="cover-stripe"></div>
  <div class="deco-circle dc1"></div>
  <div class="deco-circle dc2"></div>
  <div class="deco-circle dc3"></div>
  <div class="cover-topbar">
    <span class="topbar-logo">链采联盟</span>
    <div class="topbar-sep"></div>
    <span class="topbar-sub">CHAIN PROCUREMENT ALLIANCE · DAILY FINANCE BRIEFING</span>
    <div class="topbar-live"><div class="live-dot"></div><span class="live-text">DAILY</span></div>
  </div>
  <div class="cover-main">
    <div>
      <div class="push-label">
        <span class="push-tag">链采联盟 · 每日财金推送</span>
        <span class="push-chain">{date_cn}</span>
      </div>
      <div class="cover-headline">
        <div class="eyebrow">DAILY FINANCIAL &amp; PROCUREMENT INTELLIGENCE</div>
        <h1>每日财金信息</h1>
        <h2>金融市场 · 宏观经济 · 采购趋势</h2>
        <div class="cover-desc">
          本期简报基于 Bloomberg · FT · WSJ · CNBC · The Economist · Fed · ECB 等 28+ 权威渠道最新数据，
          由 AI 深度分析生成，覆盖市场概览、宏观经济、行业动态、采购趋势等核心板块。
        </div>
      </div>
      <div class="cover-stats">
        {market_cards}
      </div>
      <div class="cover-toc">
        <div class="toc-item"><span class="toc-num">01</span><span class="toc-name">市场概览<br/>宏观经济</span></div>
        <div class="toc-item"><span class="toc-num">02</span><span class="toc-name">行业动态<br/>采购趋势</span></div>
        <div class="toc-item"><span class="toc-num">03</span><span class="toc-name">投资策略<br/>风险提示</span></div>
        <div class="toc-item"><span class="toc-num">04</span><span class="toc-name">数据附录<br/>市场行情</span></div>
      </div>
    </div>
  </div>
  <div class="cover-footer">
    <div class="cf-left">
      <div class="cf-brand">链采联盟 · 每日财金信息</div>
      <div class="cf-sub">CHAIN PROCUREMENT ALLIANCE · DAILY FINANCE BRIEFING</div>
    </div>
    <div style="text-align:right;">
      <div class="cf-date">发布日期：{date_cn} &nbsp;|&nbsp; 生成时间：{generation_time}</div>
      <div class="cf-disc">本简报仅供参考，不构成任何投资或商业决策建议</div>
    </div>
  </div>
</div>

<!-- PAGE 1: 市场概览 + 宏观经济 -->
<div class="cpage">
  <div class="ph">
    <span class="ph-brand">链采联盟 · 每日财金推送</span>
    <span class="ph-sub">DAILY FINANCE BRIEFING</span>
    <span class="ph-date">{report_date}</span>
  </div>
  <div class="pbody">
    {pmi_line}
    <div class="sec-banner">
      <div class="sec-num"><span class="sec-num-text">01</span><span class="sec-num-label">MARKET</span></div>
      <div class="sec-title"><h2>市场概览</h2><p>Global Market Overview · Key Indices · Core Themes</p></div>
    </div>
    {sec1_html}
    <div class="sec-banner" style="margin-top:18px;">
      <div class="sec-num orange"><span class="sec-num-text">02</span><span class="sec-num-label">MACRO</span></div>
      <div class="sec-title orange"><h2>宏观经济分析</h2><p>Macro Analysis · Central Banks · Policy Trends</p></div>
    </div>
    {sec2_html}
  </div>
  <div class="pfoot"><span class="pf-brand">链采联盟 · 每日财金信息</span><span class="pf-disc">仅供参考，不构成投资建议</span></div>
</div>

<!-- PAGE 2: 行业动态 + 采购趋势 -->
<div class="cpage">
  <div class="ph">
    <span class="ph-brand">链采联盟 · 每日财金推送</span>
    <span class="ph-sub">DAILY FINANCE BRIEFING</span>
    <span class="ph-date">{report_date}</span>
  </div>
  <div class="pbody">
    <div class="sec-banner">
      <div class="sec-num blue"><span class="sec-num-text">03</span><span class="sec-num-label">INDUSTRY</span></div>
      <div class="sec-title blue"><h2>行业动态</h2><p>Industry Trends · AI · New Energy · Semiconductors</p></div>
    </div>
    {sec3_html}
    <div class="sec-banner" style="margin-top:18px;">
      <div class="sec-num gold"><span class="sec-num-text">04</span><span class="sec-num-label">PROCURE</span></div>
      <div class="sec-title gold"><h2>采购趋势</h2><p>Procurement · Commodities · Logistics · Supply Chain</p></div>
    </div>
    {sec4_html}
  </div>
  <div class="pfoot"><span class="pf-brand">链采联盟 · 每日财金信息</span><span class="pf-disc">仅供参考，不构成投资建议</span></div>
</div>

<!-- PAGE 3: 投资策略 + 数据附录 -->
<div class="cpage">
  <div class="ph">
    <span class="ph-brand">链采联盟 · 每日财金推送</span>
    <span class="ph-sub">DAILY FINANCE BRIEFING</span>
    <span class="ph-date">{report_date}</span>
  </div>
  <div class="pbody">
    <div class="sec-banner">
      <div class="sec-num teal"><span class="sec-num-text">05</span><span class="sec-num-label">STRATEGY</span></div>
      <div class="sec-title teal"><h2>投资策略建议</h2><p>Investment Strategy · Asset Allocation · Risk Warning</p></div>
    </div>
    {sec5_html}
    <div class="sec-banner" style="margin-top:18px;">
      <div class="sec-num gray"><span class="sec-num-text">06</span><span class="sec-num-label">DATA</span></div>
      <div class="sec-title gray"><h2>市场数据附录</h2><p>Market Data Appendix · Real-time Prices</p></div>
    </div>
    {market_table}
    <div style="margin-top:16px;font-size:10px;color:#aaa;border-top:1px solid #eee;padding-top:10px;">
      数据来源：Bloomberg · FT · WSJ · CNBC · The Economist · Federal Reserve · ECB · BIS · OilPrice · TechCrunch · SCMP · Nikkei Asia · Supply Chain Dive · Spend Matters 等 28+ 权威渠道<br/>
      报告生成时间：{generation_time} &nbsp;|&nbsp; 本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。
    </div>
  </div>
  <div class="pfoot"><span class="pf-brand">链采联盟 · 每日财金信息</span><span class="pf-disc">仅供参考，不构成投资建议</span></div>
</div>

</body>
</html>"""
    return html


# ============================================================
# Main (v8 - Generates BOTH v1 original and v2 visual reports)
# ============================================================
def main():
    print("=" * 60)
    print(f"Daily Financial Report v8 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    report_date = datetime.now().strftime('%Y-%m-%d')

    # ── v1 paths (original naming, unchanged) ──
    v1_base = f"investment_research_{report_date}"
    v1_html_path = f"{v1_base}.html"
    v1_pdf_path  = f"{v1_base}.pdf"

    # ── v2 paths (new visual report) ──
    v2_html_path = f"report_visual_{report_date}.html"
    v2_pdf_path  = f"report_visual_{report_date}.pdf"

    # 1. Fetch market data
    market_data = fetch_market_data()
    with open("market_data.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    # 2. Aggregate news from 20+ sources
    all_news = aggregate_all_news(max_items_per_source=6)
    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    news_text = format_news_for_prompt(all_news)

    # 3. Generate AI analysis (shared by both reports)
    generated_content = generate_report_content(market_data, news_text)
    with open("generated_content.md", "w", encoding="utf-8") as f:
        f.write(generated_content)

    # 4. Fetch PMI data
    pmi_data = fetch_pmi_data()
    with open("pmi_data.json", "w", encoding="utf-8") as f:
        json.dump(pmi_data, f, ensure_ascii=False, indent=2)

    # 5. Render v1 original HTML + PDF
    html_v1 = generate_html_report(market_data, generated_content, report_date, pmi_data)
    with open(v1_html_path, "w", encoding="utf-8") as f:
        f.write(html_v1)
    print(f"[v1] HTML saved: {v1_html_path}")
    generate_pdf_from_html(html_v1, v1_pdf_path)

    # 6. Render v2 visual HTML + PDF
    html_v2 = generate_visual_html_report(market_data, generated_content, report_date, pmi_data)
    with open(v2_html_path, "w", encoding="utf-8") as f:
        f.write(html_v2)
    print(f"[v2] HTML saved: {v2_html_path}")
    generate_pdf_from_html(html_v2, v2_pdf_path)

    print("=" * 60)
    print("Both reports generated successfully.")
    print(f"  v1 (original): {v1_pdf_path}")
    print(f"  v2 (visual):   {v2_pdf_path}")
    print("=" * 60)
    return v1_html_path, v1_pdf_path, v2_html_path, v2_pdf_path


if __name__ == "__main__":
    main()
