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
# PMI Data Fetching (via AKShare)
# ============================================================
def _get_latest_pmi_row(df, value_col='今值', date_col='日期', prev_col='前值'):
    """Sort by date descending, drop NaN in value_col, return the most recent valid row."""
    import pandas as pd
    df = df.copy()
    # Parse date column to datetime for proper sorting
    try:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.dropna(subset=[date_col])
        df = df.sort_values(date_col, ascending=False)
    except Exception:
        pass
    # Drop rows where value is NaN or empty
    df = df[df[value_col].notna()]
    df = df[df[value_col].astype(str).str.strip().str.lower().isin(['nan', 'none', '']) == False]
    if df.empty:
        return None
    last = df.iloc[0]
    date_val = last[date_col]
    try:
        date_str = date_val.strftime('%Y-%m') if hasattr(date_val, 'strftime') else str(date_val)[:7]
    except Exception:
        date_str = str(date_val)[:7]
    prev_val = None
    try:
        pv = str(last[prev_col]).strip()
        if pv not in ('nan', 'None', '', 'NaN'):
            prev_val = float(pv)
    except Exception:
        pass
    return {
        'value': float(last[value_col]),
        'prev':  prev_val,
        'date':  date_str
    }


def fetch_pmi_data() -> dict:
    """Fetch latest PMI data from AKShare (China official + Caixin).
    Always returns the most recent available data by sorting by date descending.
    """
    print("Fetching PMI data from AKShare...")
    pmi = {}
    try:
        import akshare as ak

        # China NBS Manufacturing PMI
        try:
            df = ak.macro_china_pmi_yearly()
            row = _get_latest_pmi_row(df)
            if row:
                pmi['cn_mfg'] = {'name': '中国制造业PMI（官方）', **row}
                print(f"  [PMI] cn_mfg: {row['value']} ({row['date']})")
        except Exception as e:
            print(f"  [PMI] cn_mfg error: {e}")

        # China NBS Non-Manufacturing PMI
        try:
            df2 = ak.macro_china_non_man_pmi()
            row2 = _get_latest_pmi_row(df2)
            if row2:
                pmi['cn_svc'] = {'name': '中国非制造业PMI（官方）', **row2}
                print(f"  [PMI] cn_svc: {row2['value']} ({row2['date']})")
        except Exception as e:
            print(f"  [PMI] cn_svc error: {e}")

        # Caixin Manufacturing PMI
        try:
            df3 = ak.macro_china_cx_pmi_yearly()
            row3 = _get_latest_pmi_row(df3)
            if row3:
                pmi['cx_mfg'] = {'name': '中国制造业PMI（财新）', **row3}
                print(f"  [PMI] cx_mfg: {row3['value']} ({row3['date']})")
        except Exception as e:
            print(f"  [PMI] cx_mfg error: {e}")

        # Caixin Services PMI
        try:
            df4 = ak.macro_china_cx_services_pmi_yearly()
            row4 = _get_latest_pmi_row(df4)
            if row4:
                pmi['cx_svc'] = {'name': '中国服务业PMI（财新）', **row4}
                print(f"  [PMI] cx_svc: {row4['value']} ({row4['date']})")
        except Exception as e:
            print(f"  [PMI] cx_svc error: {e}")

    except ImportError:
        print("  [PMI] akshare not installed, skipping PMI data.")
    except Exception as e:
        print(f"  [PMI] General error: {e}")

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

请根据以下来自全球20+权威信息渠道的最新新闻资讯和实时市场数据，生成一份高质量的链采联盟-每日财金信息报告。

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
# Main
# ============================================================
def main():
    print("=" * 60)
    print(f"Daily Financial Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    report_date = datetime.now().strftime('%Y-%m-%d')
    base_name = f"investment_research_{report_date}"
    html_path = f"{base_name}.html"
    pdf_path = f"{base_name}.pdf"

    # 1. Fetch market data
    market_data = fetch_market_data()
    with open("market_data.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    # 2. Aggregate news from 20+ sources
    all_news = aggregate_all_news(max_items_per_source=6)
    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    news_text = format_news_for_prompt(all_news)

    # 3. Generate AI analysis
    generated_content = generate_report_content(market_data, news_text)
    with open("generated_content.md", "w", encoding="utf-8") as f:
        f.write(generated_content)

    # 3.5 Fetch PMI data
    pmi_data = fetch_pmi_data()
    with open("pmi_data.json", "w", encoding="utf-8") as f:
        json.dump(pmi_data, f, ensure_ascii=False, indent=2)

    # 4. Render HTML
    html_content = generate_html_report(market_data, generated_content, report_date, pmi_data)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML saved: {html_path}")

    # 5. Render PDF
    generate_pdf_from_html(html_content, pdf_path)

    print("=" * 60)
    print("Report generation complete.")
    print("=" * 60)
    return html_path, pdf_path


if __name__ == "__main__":
    main()
