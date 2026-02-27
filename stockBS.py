"""
股票监控系统 Web 应用
基于 Flask 框架提供 API 接口
使用 AkShare 免费数据接口
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import threading
import time
import random
from datetime import datetime, date, timedelta
import tushare as ts
import akshare as ak
import pandas as pd
import numpy as np
import yagmail

# =========================== 配置参数 ===========================
# Tushare token（用于获取K线数据）
TS_TOKEN = "1b7ae70af8bfa3df174b6f20f9e0f3f7eb9cb8c9a67db9e3bdbab98d"
# AkShare 是免费接口，无需 token（用于实时数据）
EMAIL_USER = "zhurongjung@163.com"
EMAIL_PWD = "BWe4uYnj6XyL5FzJ"
EMAIL_TO = "2251887675@qq.com"
DATA_PERIOD = "D"
DATA_LENGTH = 120

# 文件路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKS_FILE = os.path.join(BASE_DIR, "stocks.json")
EMAIL_FILE = os.path.join(BASE_DIR, "email.json")
SENT_EMAILS_FILE = os.path.join(BASE_DIR, "sent_emails.json")

# 全局股票名称缓存
_stock_name_cache = None

def get_stock_name_cache():
    """获取股票名称缓存"""
    global _stock_name_cache
    if _stock_name_cache is None:
        try:
            print(f"正在加载股票名称缓存...")
            _stock_name_cache = ak.stock_info_a_code_name()
            if _stock_name_cache is not None and not _stock_name_cache.empty:
                print(f"股票名称缓存加载成功，共 {len(_stock_name_cache)} 只股票")
            else:
                print(f"股票名称缓存为空，将重新加载")
                _stock_name_cache = None
        except Exception as e:
            print(f"加载股票名称缓存失败: {e}")
            _stock_name_cache = pd.DataFrame(columns=['code', 'name'])
    return _stock_name_cache

# 初始化 Flask
app = Flask(__name__)
CORS(app)

# 初始化 Tushare（用于K线数据）
ts.set_token(TS_TOKEN)
pro = ts.pro_api()

# 初始化 yagmail
yag = yagmail.SMTP(user=EMAIL_USER, password=EMAIL_PWD, host="smtp.163.com")

# =========================== 数据读写函数 ===========================
def load_json_file(filepath, default_data):
    """加载 JSON 文件，如果不存在则返回默认数据"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return default_data
    except Exception as e:
        print(f"加载文件失败 {filepath}: {e}")
        return default_data

def save_json_file(filepath, data):
    """保存数据到 JSON 文件"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存文件失败 {filepath}: {e}")
        return False

def get_today_date():
    """获取今天的日期字符串"""
    return datetime.now().strftime('%Y-%m-%d')

def has_email_sent_today(stock_code):
    """检查某股票今日是否已发送邮件"""
    try:
        sent_data = load_json_file(SENT_EMAILS_FILE, {"dates": {}})
        today = get_today_date()
        if today in sent_data["dates"]:
            sent_stocks = sent_data["dates"][today]
            return stock_code in sent_stocks
        return False
    except Exception as e:
        print(f"检查邮件记录失败: {e}")
        return False

def record_email_sent(stock_code):
    """记录某股票今日已发送邮件"""
    try:
        sent_data = load_json_file(SENT_EMAILS_FILE, {"dates": {}})
        today = get_today_date()

        if today not in sent_data["dates"]:
            sent_data["dates"][today] = []

        if stock_code not in sent_data["dates"][today]:
            sent_data["dates"][today].append(stock_code)

        save_json_file(SENT_EMAILS_FILE, sent_data)
        print(f"记录邮件发送: {stock_code} - {today}")
    except Exception as e:
        print(f"记录邮件发送失败: {e}")

def clean_old_email_records():
    """清理30天前的邮件记录"""
    try:
        sent_data = load_json_file(SENT_EMAILS_FILE, {"dates": {}})
        today = datetime.now()
        dates_to_remove = []

        for d in list(sent_data.get("dates", {}).keys()):
            try:
                record_date = datetime.strptime(d, '%Y-%m-%d')
                days_diff = (today - record_date).days
                if days_diff > 30:
                    dates_to_remove.append(d)
            except:
                dates_to_remove.append(d)

        for d in dates_to_remove:
            del sent_data["dates"][d]

        save_json_file(SENT_EMAILS_FILE, sent_data)
    except Exception as e:
        print(f"清理旧记录失败: {e}")

def to_standard_code(stock_code):
    """将带后缀的代码转换为标准6位代码"""
    if '.' in stock_code:
        return stock_code.split('.')[0]
    return stock_code

def to_akshare_code(stock_code):
    """将6位代码转换为 AkShare 需要的格式"""
    if '.' not in stock_code:
        if stock_code.startswith('6'):
            return f"sh{stock_code}"
        elif stock_code.startswith('0') or stock_code.startswith('3'):
            return f"sz{stock_code}"
        elif stock_code.startswith('8') or stock_code.startswith('4'):
            return f"bj{stock_code}"
    return stock_code

def get_stock_name(stock_code):
    """获取股票名称 - 使用 AkShare"""
    try:
        # 转换为标准6位代码
        standard_code = to_standard_code(stock_code)

        # 获取股票名称缓存
        cache_df = get_stock_name_cache()

        if cache_df is None or cache_df.empty:
            print(f"股票名称缓存为空")
            return stock_code

        # 在缓存中查找股票名称
        # stock_info_a_code_name 返回的DataFrame包含 'code' 和 'name' 列
        stock_row = cache_df[cache_df['code'] == standard_code]

        if not stock_row.empty:
            return stock_row.iloc[0]['name']
        else:
            print(f"未找到股票 {standard_code} 的名称")
            return stock_code
    except Exception as e:
        print(f"获取股票名称失败 {stock_code}: {e}")
        return stock_code


def _get_sina_realtime_data(stock_code):
    """
    使用新浪财经API获取股票实时数据（轻量级备选方案）
    当东方财富源失败时使用此方法
    """
    try:
        import requests

        # 将6位代码转换为新浪需要的格式
        # 沪市：sh6xxxxx，深市：sz0xxxxx/3xxxxx，北交所：bj8xxxxx/4xxxxx
        if '.' in stock_code:
            standard_code = stock_code.split('.')[0]
            prefix = stock_code.split('.')[1].lower()
        else:
            standard_code = stock_code
            if stock_code.startswith('6'):
                prefix = 'sh'
            elif stock_code.startswith('0') or stock_code.startswith('3'):
                prefix = 'sz'
            elif stock_code.startswith('8') or stock_code.startswith('4'):
                prefix = 'bj'
            else:
                return 0, 0, 0

        sina_code = f"{prefix}{standard_code}"
        # 新浪财经API（轻量级）
        url = f"http://hq.sinajs.cn/list={sina_code}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn/'
        }

        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            content = response.text
            # 解析新浪财经返回的数据格式: var hq_str_sh600000="..."
            if f"var hq_str_{sina_code}=" in content:
                start = content.find('"')
                end = content.rfind('"')
                if start != -1 and end != -1:
                    data_str = content[start+1:end]
                    data = data_str.split(',')
                    # 新浪数据格式: 名称,开盘,昨收,现价,最高,最低,买入价,卖出价,成交数(手),成交额,买一量,买一价,买二量,买二价,买三量,买三价,买四量,买四价,买五量,买五价,卖一量,卖一价,卖二量,卖二价,卖三量,卖三价,卖四量,卖四价,卖五量,卖五价,日期,时间
                    if len(data) >= 10:
                        try:
                            price = float(data[3])  # 现价
                            prev_close = float(data[2])  # 昨收
                            change_pct = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0

                            # 计算换手率：直接使用成交量作为参考指标
                            # 新浪成交数单位是手，1手=100股
                            volume_hands = float(data[8]) if len(data) > 8 and data[8] else 0  # 成交量（手）
                            # 直接以万手为单位显示换手率参考值
                            turnover = volume_hands / 10000  # 转换为万手
                            print(f"    成交量: {volume_hands:.0f} 手 ({turnover:.2f}万手)")

                            print(f"获取 {stock_code} 新浪数据成功: 价格={price}, 涨跌={change_pct:.2f}%, 换手率={turnover:.2f}万手")
                            return price, change_pct, turnover
                        except (ValueError, IndexError):
                            pass

        return 0, 0, 0
    except Exception as e:
        print(f"  获取新浪数据失败: {str(e)[:100]}")
        return 0, 0, 0

def get_stock_realtime_data(stock_code):
    """获取股票实时数据（价格、涨跌幅、换手率）- 支持多数据源"""
    import time as time_module

    # 数据源优先级：东方财富历史 -> 东方财富实时 -> 新浪财经
    # source_type: hist-东方财富hist, spot-东方财富实时, sina-新浪财经
    data_sources = [
        ("hist", "东方财富hist", lambda code: _get_eastmoney_hist_data(code, time_module)),
        ("spot", "东方财富实时", lambda code: _get_eastmoney_spot_data(code)),
        ("sina", "新浪财经", lambda code: _get_sina_realtime_data(code))
    ]

    try:
        print(f"正在获取 {stock_code} 的实时数据...")

        for source_type, source_name, get_data_func in data_sources:
            try:
                price, change, turnover = get_data_func(stock_code)
                if price > 0:
                    print(f"  [{source_name}] 获取成功")
                    return price, change, turnover, source_type
                else:
                    print(f"  [{source_name}] 数据无效，尝试下一源")
                    # 切换数据源时添加随机延时
                    time_module.sleep(random.uniform(1, 2))
            except Exception as e:
                print(f"  [{source_name}] 失败: {str(e)[:100]}")
                # 出错后添加随机延时再尝试下一源
                time_module.sleep(random.uniform(1, 2))
                continue

        print(f"获取 {stock_code} 数据失败: 所有数据源均失败")
        return 0, 0, 0, None

    except Exception as e:
        print(f"获取实时数据失败 {stock_code}: {e}")
        return 0, 0, 0, None

def _get_eastmoney_hist_data(stock_code, time_module):
    """使用Tushare获取K线数据"""
    standard_code = to_standard_code(stock_code)
    max_retries = 2
    BASE_DELAY = 2

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"  Tushare K线重试第 {attempt + 1} 次...")
                wait_time = (BASE_DELAY * (attempt + 1)) + random.uniform(0.5, 1.5)
                time_module.sleep(wait_time)

            # 获取最近30天数据
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

            # 转换为tushare格式的股票代码
            if standard_code.startswith('6'):
                ts_code = f"{standard_code}.SH"
            elif standard_code.startswith('0') or standard_code.startswith('3'):
                ts_code = f"{standard_code}.SZ"
            elif standard_code.startswith('8') or standard_code.startswith('4'):
                ts_code = f"{standard_code}.BJ"
            else:
                return 0, 0, 0

            # 使用tushare获取日线数据
            hist_df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if not hist_df.empty and len(hist_df) >= 2:
                # tushare返回的数据是倒序的（最新的在前），需要排序
                hist_df = hist_df.sort_values('trade_date').reset_index(drop=True)
                latest = hist_df.iloc[-1]  # 最新一天
                prev = hist_df.iloc[-2]  # 前一天

                price = float(latest['close'])
                prev_price = float(prev['close'])

                # 计算涨跌幅
                change_pct = ((price - prev_price) / prev_price) * 100

                # tushare的换手率需要单独获取（或使用pct_chg字段）
                # 暂时返回0，换手率可从其他数据源获取
                turnover = 0.0

                return price, change_pct, turnover
            else:
                return 0, 0, 0
        except Exception as e:
            error_str = str(e)
            # 检查是否是连接相关错误
            if 'Connection' in error_str or 'aborted' in error_str.lower() or 'remote' in error_str.lower():
                print(f"  Tushare K线连接中断(尝试{attempt + 1}): {error_str[:80]}")
                if attempt == max_retries - 1:
                    return 0, 0, 0
            else:
                return 0, 0, 0

    return 0, 0, 0

def _get_eastmoney_spot_data(stock_code):
    """使用东方财富实时行情接口获取数据"""
    standard_code = to_standard_code(stock_code)
    now = time.localtime()
    hour = now.tm_hour
    current_time = hour * 100 + now.tm_min

    # 仅在交易时间尝试实时数据
    if not (930 <= current_time <= 1500):
        return 0, 0, 0

    try:
        spot_df = ak.stock_zh_a_spot_em()
        if spot_df is not None and not spot_df.empty:
            stock_row = spot_df[spot_df['代码'] == standard_code]
            if not stock_row.empty:
                stock_row = stock_row.iloc[0]
                price = float(stock_row.get('最新价', 0))
                change_pct = float(stock_row.get('涨跌幅', 0))
                turnover = float(stock_row.get('换手率', 0))
                if pd.isna(turnover):
                    turnover = 0.0
                return price, change_pct, turnover
        return 0, 0, 0
    except Exception as e:
        print(f"  获取东方财富实时数据失败: {str(e)[:80]}")
        return 0, 0, 0

# =========================== 核心指标计算函数 ===========================
def calculate_fund_index(df):
    """
    计算拉升资金、主力资金指标
    :param df: 包含high/low/close的DataFrame
    :return: 新增拉升资金、主力资金列的DataFrame
    """
    data = df.copy()

    # 计算VAR1: (HIGH+LOW+CLOSE*2)/4
    data['VAR1'] = (data['high'] + data['low'] + data['close'] * 2) / 4

    # 计算VAR2-VAR4
    data['VAR2'] = data['VAR1'].ewm(span=21, adjust=False).mean()
    data['VAR3'] = data['VAR1'].rolling(window=21).std()
    data['VAR4'] = ((data['VAR1'] - data['VAR2']) / data['VAR3'] * 100 + 200) / 4

    # 计算VAR5-VAR7
    data['VAR5'] = (data['VAR4'].ewm(span=89, adjust=False).mean() - 25) * 1.56
    data['VAR6'] = data['VAR5'].ewm(span=5, adjust=False).mean() * 1.22
    data['VAR7'] = data['VAR6'].ewm(span=3, adjust=False).mean()

    # 计算拉升资金
    data['VAR1B'] = data['close'].ewm(span=3, adjust=False).mean() - data['close'].ewm(span=89, adjust=False).mean()
    data['VAR1C'] = data['VAR1B'].ewm(span=21, adjust=False).mean()
    data['VAR1D'] = (data['VAR1B'] - data['VAR1C']) * 10
    data['VAR1F'] = np.power(data['VAR1D'], 3) * 0.1 + np.power(data['VAR1D'], 2)
    data['拉升资金'] = np.where(data['VAR1D'] > 0.015, data['VAR1F'] / 45, 0)

    # 计算主力资金
    data['VAR9'] = data['close'].ewm(span=2, adjust=False).mean() - data['close'].ewm(span=55, adjust=False).mean()
    data['VAR10'] = data['VAR9'].ewm(span=13, adjust=False).mean()
    data['VAR11'] = 2 * (data['VAR9'] - data['VAR10'])
    data['主力资金'] = np.power(data['VAR11'], 3) * 0.1 + np.power(data['VAR11'], 1)

    data = data.fillna(0)
    return data

def judge_trade_signal(df):
    """
    判断买入/卖出信号
    :param df: 包含拉升资金、主力资金的DataFrame
    :return: signal（buy/sell/none）、股票代码、最新价格
    """
    latest_three = df.tail(3)
    if len(latest_three) < 3:
        return "none", "", 0

    today = latest_three.iloc[2]
    yesterday = latest_three.iloc[1]
    two_days_ago = latest_three.iloc[0]

    # 买入条件
    buy_cond1 = (today['拉升资金'] > 0) and (yesterday['拉升资金'] == 0)
    buy_cond2 = (today['拉升资金'] - yesterday['拉升资金']) > 0.1
    buy_signal = buy_cond1 or buy_cond2

    # 卖出条件
    sell_cond1 = ((today['拉升资金'] - yesterday['拉升资金']) < -0.05) and ((yesterday['拉升资金']-two_days_ago['拉升资金']) > 0.001)
    sell_cond2 = (yesterday['主力资金'] > 0.01) and (today['主力资金'] < 0)
    sell_signal = sell_cond1 or sell_cond2

    stock_code = df['code'].iloc[0]
    latest_price = today['close']

    if buy_signal:
        return "buy", stock_code, latest_price
    elif sell_signal:
        return "sell", stock_code, latest_price
    else:
        return "none", stock_code, latest_price

def get_stock_data(stock_code, preferred_source=None):
    """获取单只股票的日线数据 - 使用 Tushare
    Args:
        stock_code: 股票代码
        preferred_source: 优先使用的数据源（保留参数兼容性，但统一使用tushare）
    """
    import time as time_module

    standard_code = to_standard_code(stock_code)

    # 转换为tushare格式的股票代码
    if standard_code.startswith('6'):
        ts_code = f"{standard_code}.SH"
    elif standard_code.startswith('0') or standard_code.startswith('3'):
        ts_code = f"{standard_code}.SZ"
    elif standard_code.startswith('8') or standard_code.startswith('4'):
        ts_code = f"{standard_code}.BJ"
    else:
        print(f"  无法识别股票代码格式: {stock_code}")
        return pd.DataFrame()

    # 日期范围
    today = datetime.now()
    end_date = today.strftime('%Y%m%d')
    start_date = (today - timedelta(days=DATA_LENGTH + 30)).strftime('%Y%m%d')

    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = (attempt + 1) * 2 + random.uniform(0.5, 1.5)
                print(f"  重试第 {attempt + 1} 次... 等待 {wait_time:.2f} 秒")
                time_module.sleep(wait_time)

            print(f"  尝试获取{stock_code}数据 - Tushare (尝试{attempt + 1})")
            # 使用tushare获取日线数据
            df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df.empty:
                print(f"  Tushare 数据为空")
                continue

            if len(df) < 2:
                print(f"  Tushare 数据不足2天")
                continue

            # tushare返回的数据是倒序的（最新的在前），需要排序
            df = df.sort_values('trade_date').reset_index(drop=True)

            # 构建标准格式的DataFrame
            df_new = pd.DataFrame()
            df_new['trade_date'] = df['trade_date']
            df_new['open'] = df['open']
            df_new['close'] = df['close']
            df_new['high'] = df['high']
            df_new['low'] = df['low']
            df_new['vol'] = df['vol']

            # 添加 code 列（不带后缀）
            df_new['code'] = stock_code

            # 按日期升序排列
            df_new = df_new.sort_values('trade_date').reset_index(drop=True)

            print(f"  获取{stock_code}数据成功 - Tushare，共{len(df_new)}条")
            return df_new

        except Exception as e:
            error_str = str(e)
            # 检查是否是连接相关错误
            is_connection_error = (
                'Connection' in error_str or
                'aborted' in error_str.lower() or
                'remote' in error_str.lower() or
                'timeout' in error_str.lower()
            )

            if is_connection_error:
                print(f"  Tushare 连接中断(尝试{attempt + 1}): {error_str[:60]}")
                if attempt == max_retries - 1:
                    print(f"  Tushare 连续失败")
            else:
                print(f"  Tushare 获取失败: {error_str[:60]}")
                break  # 非连接错误，直接退出

    # 所有尝试都失败
    print(f"获取股票{stock_code}数据失败：所有尝试均失败")
    return pd.DataFrame()

# =========================== 邮件相关函数 ===========================
def check_and_reset_daily_emails():
    """检查并重置每日邮件记录（将today移到yesterday，today置空）"""
    try:
        email_data = load_json_file(EMAIL_FILE, {"emails": {}, "lastUpdate": ""})
        today_date = get_today_date()

        # 检查是否需要重置（通过比较lastUpdate的日期）
        last_update = email_data.get("lastUpdate", "")
        if last_update:
            try:
                last_date = last_update.split()[0]  # 获取日期部分
                if last_date == today_date:
                    # 同一天，不需要重置
                    return
            except:
                pass

        # 新的一天，重置所有股票的邮件记录
        print(f"检测到新的一天({today_date})，重置邮件记录...")
        reset_count = 0
        for code in email_data["emails"]:
            if email_data["emails"][code].get("today"):
                # 将today移到yesterday
                email_data["emails"][code]["yesterday"] = email_data["emails"][code]["today"]
                email_data["emails"][code]["today"] = None
                reset_count += 1
            else:
                # today本来就是None，yesterday也置空
                email_data["emails"][code]["yesterday"] = None

        email_data["lastUpdate"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_json_file(EMAIL_FILE, email_data)
        print(f"邮件记录重置完成，共处理 {reset_count} 条记录")
    except Exception as e:
        print(f"重置每日邮件记录失败: {e}")

def save_email_record(stock_code, stock_name, signal_type, price, condition, content):
    """保存邮件记录到 email.json"""
    email_data = load_json_file(EMAIL_FILE, {"emails": {}, "lastUpdate": ""})

    # 使用不带后缀的6位代码作为key
    standard_code = to_standard_code(stock_code)

    if standard_code not in email_data["emails"]:
        email_data["emails"][standard_code] = {"yesterday": None, "today": None}

    # 添加今日新邮件（不自动移动yesterday，由check_and_reset_daily_emails处理）
    email_data["emails"][standard_code]["today"] = {
        "type": signal_type,
        "code": stock_code,
        "name": stock_name,
        "price": price,
        "condition": condition,
        "content": content,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    email_data["lastUpdate"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_json_file(EMAIL_FILE, email_data)

def send_email_alert(signal_type, stock_code, stock_name, price):
    """发送邮件提醒"""
    subject = f"股票交易提醒 - {stock_name}({stock_code})"

    if signal_type == "buy":
        condition = "拉升资金满足买入规则"
        content_lines = [
            f"📈 买入提醒",
            f"股票名称：{stock_name}",
            f"股票代码：{stock_code}",
            f"最新价格：{price:.2f}",
            f"触发条件：{condition}",
            f"提醒时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
        ]
    elif signal_type == "sell":
        condition = "拉升资金/主力资金满足卖出规则"
        content_lines = [
            f"📉 卖出提醒",
            f"股票名称：{stock_name}",
            f"股票代码：{stock_code}",
            f"最新价格：{price:.2f}",
            f"触发条件：{condition}",
            f"提醒时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
        ]
    else:
        return False

    content = "\n".join(content_lines)

    # 检查是否今日已发送过该股票的邮件
    standard_code = to_standard_code(stock_code)
    if has_email_sent_today(standard_code):
        print(f"今日已发送过 {stock_code}({stock_name}) 的邮件，跳过")
        return False

    try:
        yag.send(to=EMAIL_TO, subject=subject, contents=content)
        print(f"邮件已发送：{subject}")

        # 记录今日已发送
        record_email_sent(standard_code)

        # 保存邮件记录
        save_email_record(stock_code, stock_name, signal_type, price, condition, content)
        return True
    except Exception as e:
        print(f"邮件发送失败：{e}")
        return False

# =========================== 监控逻辑 ===========================
monitoring_thread = None
monitoring_active = False
new_emails_queue = []
# 记录最后成功的数据源类型：hist-东方财富hist, spot-东方财富实时, sina-新浪财经
_last_successful_data_source = None

def monitor_stocks():
    """监控股票的主函数"""
    global monitoring_active, new_emails_queue, _last_successful_data_source

    while monitoring_active:
        try:
            # 清理旧记录
            clean_old_email_records()

            # 检查当前时间
            now = time.localtime()
            hour = now.tm_hour
            minute = now.tm_min
            current_time = hour * 100 + minute
            is_trading_time = 930 <= current_time <= 1500

            # 获取股票列表
            stocks_data = load_json_file(STOCKS_FILE, {"stocks": [], "lastUpdate": ""})

            if is_trading_time:
                # 交易时间：持续监控模式
                print(f"\n========== 交易时间监控 {get_today_date()} {hour:02d}:{minute:02d} ==========")
                print(f"当前监控 {len(stocks_data['stocks'])} 只股票")
            else:
                # 非交易时间：收盘价一次性分析模式
                print(f"\n========== 非交易时间 - 基于收盘价分析 {get_today_date()} {hour:02d}:{minute:02d} ==========")
                print(f"分析 {len(stocks_data['stocks'])} 只股票的交易信号")

            new_emails = []

            for stock in stocks_data["stocks"]:
                stock_code = stock["code"]
                stock_name = stock.get("name", "未知")

                print(f"检查股票: {stock_code}({stock_name})")

                # 如果没有记录成功的数据源，先测试确定可用的数据源
                if _last_successful_data_source is None:
                    _, _, _, source_type = get_stock_realtime_data(stock_code)
                    if source_type:
                        _last_successful_data_source = source_type
                        source_name_map = {'hist': '东方财富hist', 'spot': '东方财富实时', 'sina': '新浪财经'}
                        print(f"  已确定数据源: {source_name_map.get(source_type, source_type)}")
                        # 获取K线数据时使用相同的数据源
                        df = get_stock_data(stock_code, preferred_source=_last_successful_data_source)
                    else:
                        # 所有数据源均失败，跳过该股票
                        print(f"  -> 所有实时数据源均失败，跳过")
                        continue
                else:
                    # 使用已记录的数据源获取K线数据
                    df = get_stock_data(stock_code, preferred_source=_last_successful_data_source)

                if df.empty:
                    print(f"  -> 数据为空，跳过")
                    continue

                df = calculate_fund_index(df)
                signal, _, price = judge_trade_signal(df)

                if signal != "none":
                    print(f"  -> 发现 {signal} 信号！")
                    # 使用 AkShare 格式代码
                    ak_code = to_akshare_code(stock_code)
                    success = send_email_alert(signal, ak_code, stock_name, price)
                    if success:
                        new_emails.append({
                            "code": stock_code,
                            "name": stock_name,
                            "type": signal,
                            "price": price,
                            "time": time.strftime('%Y-%m-%d %H:%M:%S')
                        })

            # 将新邮件添加到队列（供前端轮询获取）
            if new_emails:
                new_emails_queue.extend(new_emails)
                # 限制队列大小
                if len(new_emails_queue) > 50:
                    new_emails_queue = new_emails_queue[-50:]

            # 根据交易时间决定等待策略
            if is_trading_time:
                # 交易时间：每分钟检查一次
                print(f"等待60秒后继续监控...")
                time.sleep(60)
            else:
                # 非交易时间：分析完成后等待较长时间（等待下一个交易时段）
                print(f"非交易时间分析完成，等待600秒后重新检查...")
                time.sleep(600)

        except Exception as e:
            print(f"监控出错: {e}")
            time.sleep(60)  # 出错后等待60秒再重试

# =========================== API 路由 ===========================
@app.route('/')
def index():
    """返回主页"""
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze_current_price():
    """使用当天收盘价计算指标并发送邮件提醒"""
    try:
        data = request.json
        stock_code = data.get('code', '').strip()

        if not stock_code:
            return jsonify({"success": False, "message": "请提供股票代码"})

        stock_name = get_stock_name(stock_code)

        # 使用当天收盘价计算指标
        price, change, turnover, _ = get_stock_realtime_data(stock_code)

        # 如果获取失败，跳过
        if price == 0:
            return jsonify({"success": False, "message": f"无法获取{stock_name}({stock_code})的有效价格"})

        # 使用当天收盘价计算指标（需要至少2天历史数据）
        # today = datetime.now().strftime('%Y%m%d')
        # yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

        # 获取最近10天的数据（包含今天和昨天）
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

        # 转换为tushare格式的股票代码
        standard_code = to_standard_code(stock_code)
        if standard_code.startswith('6'):
            ts_code = f"{standard_code}.SH"
        elif standard_code.startswith('0') or standard_code.startswith('3'):
            ts_code = f"{standard_code}.SZ"
        elif standard_code.startswith('8') or standard_code.startswith('4'):
            ts_code = f"{standard_code}.BJ"
        else:
            return jsonify({"success": False, "message": f"无法识别股票代码格式: {stock_code}"})

        # 使用tushare获取日线数据
        hist_df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

        if hist_df.empty or len(hist_df) < 2:
            return jsonify({"success": False, "message": f"历史数据不足，无法计算{stock_name}({stock_code})的指标"})

        # tushare返回的数据是倒序的，需要排序并转换为标准格式
        hist_df = hist_df.sort_values('trade_date').reset_index(drop=True)

        # 构建与calculate_fund_index兼容的DataFrame格式
        df = pd.DataFrame()
        df['trade_date'] = hist_df['trade_date']
        df['open'] = hist_df['open']
        df['close'] = hist_df['close']
        df['high'] = hist_df['high']
        df['low'] = hist_df['low']
        df['vol'] = hist_df['vol']
        df['code'] = stock_code

        if df.empty or len(df) < 2:
            return jsonify({"success": False, "message": f"历史数据不足，无法计算{stock_name}({stock_code})的指标"})

        # 计算指标
        df = calculate_fund_index(df)

        # 判断信号（使用最后一天的数据）
        latest = df.iloc[-1]
        signal, code, latest_price = judge_trade_signal(df.tail(2))

        if signal != "none":
            # 发送邮件提醒
            send_email_alert(signal, stock_code, stock_name, latest_price)

            result = {
                "success": True,
                "message": f"分析完成！{stock_name}({stock_code}) - {signal}信号",
                "signal": signal,
                "price": latest_price,
                "拉升资金": float(latest['拉升资金']),
                "主力资金": float(latest['主力资金'])
            }

            print(f"  [使用当前价格] {stock_code} 分析完成：{signal}信号")
            print(f"    拉升资金: {float(latest['拉升资金']):.4f}")
            print(f"    主力资金: {float(latest['主力资金']):.4f}")

            return jsonify(result)
        else:
            return jsonify({"success": True, "message": f"{stock_name}({stock_code}) 当前无交易信号"})

    except Exception as e:
        print(f"  [使用当前价格] 分析失败: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/stocks', methods=['GET'])
def get_stocks():
    """获取股票列表数据"""
    # 检查并重置每日邮件记录
    check_and_reset_daily_emails()

    stocks_data = load_json_file(STOCKS_FILE, {"stocks": [], "lastUpdate": ""})
    email_data = load_json_file(EMAIL_FILE, {"emails": {}, "lastUpdate": ""})

    # 合并邮件数据（使用标准6位代码匹配）
    for stock in stocks_data["stocks"]:
        # 统一使用6位标准代码进行匹配
        standard_code = to_standard_code(stock["code"])
        if standard_code in email_data["emails"]:
            stock["emails"] = email_data["emails"][standard_code]
        else:
            stock["emails"] = {"yesterday": None, "today": None}

    return jsonify(stocks_data)

@app.route('/api/stocks/update', methods=['POST'])
def update_stocks():
    """更新股票代码"""
    try:
        data = request.json
        codes = data.get('codes', [])

        stocks_data = load_json_file(STOCKS_FILE, {"stocks": [], "lastUpdate": ""})

        for item in codes:
            index = int(item['index'])
            new_code = item['newCode'].strip()

            if index < len(stocks_data["stocks"]):
                old_code = stocks_data["stocks"][index]["code"]

                # 更新代码
                stocks_data["stocks"][index]["code"] = new_code

                # 如果代码改变了，获取新名称并重置数据
                if new_code != old_code:
                    print(f"更新股票代码: {old_code} -> {new_code}")
                    name = get_stock_name(new_code)
                    stocks_data["stocks"][index]["name"] = name
                    stocks_data["stocks"][index]["price"] = 0
                    stocks_data["stocks"][index]["change"] = 0
                    stocks_data["stocks"][index]["turnover"] = 0
                    print(f"  股票名称: {name}")

        stocks_data["lastUpdate"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_json_file(STOCKS_FILE, stocks_data)

        return jsonify({"success": True, "message": "股票代码已更新"})
    except Exception as e:
        print(f"更新股票代码失败: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """刷新股票数据"""
    import time as time_module
    try:
        print("\n========== 刷新股票数据 ==========")
        stocks_data = load_json_file(STOCKS_FILE, {"stocks": [], "lastUpdate": ""})

        for i, stock in enumerate(stocks_data["stocks"]):
            code = stock["code"]
            print(f"刷新股票: {code}")
            price, change, turnover, _ = get_stock_realtime_data(code)
            stock["price"] = price
            stock["change"] = change
            stock["turnover"] = turnover

            # 每次刷新都更新股票名称
            name = get_stock_name(code)
            stock["name"] = name
            print(f"  名称: {name}, 价格: {price}, 涨跌: {change}%, 成交量: {turnover}")

            # 每个股票之间随机延时(0.5-1.5秒)，避免固定间隔被识别为爬虫
            if i > 0:
                delay = random.uniform(0.5, 1.5)
                print(f"  延时 {delay:.2f} 秒后处理下一只股票...")
                time_module.sleep(delay)

        stocks_data["lastUpdate"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_json_file(STOCKS_FILE, stocks_data)

        return jsonify({"success": True, "message": "数据已刷新"})
    except Exception as e:
        print(f"刷新数据失败: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/monitor/start', methods=['POST'])
def start_monitor():
    """启动监控"""
    global monitoring_thread, monitoring_active

    if monitoring_active:
        return jsonify({"success": True, "message": "监控已在运行中"})

    monitoring_active = True
    monitoring_thread = threading.Thread(target=monitor_stocks, daemon=True)
    monitoring_thread.start()

    return jsonify({"success": True, "message": "监控已启动"})

@app.route('/api/monitor/stop', methods=['POST'])
def stop_monitor():
    """停止监控"""
    global monitoring_active

    monitoring_active = False
    return jsonify({"success": True, "message": "监控已停止"})

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取系统状态"""
    global monitoring_active, new_emails_queue

    # 获取并清空新邮件队列
    result_emails = []
    if new_emails_queue:
        result_emails = new_emails_queue.copy()
        new_emails_queue.clear()

    return jsonify({
        "monitoring": monitoring_active,
        "newEmails": result_emails,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# =========================== 启动应用 ===========================
if __name__ == '__main__':
    # 确保数据文件存在
    if not os.path.exists(STOCKS_FILE):
        save_json_file(STOCKS_FILE, {
            "stocks": [
                {"code": "600000", "name": "浦发银行", "price": 0, "change": 0, "turnover": 0},
                {"code": "600036", "name": "招商银行", "price": 0, "change": 0, "turnover": 0},
                {"code": "000001", "name": "平安银行", "price": 0, "change": 0, "turnover": 0},
                {"code": "000858", "name": "五粮液", "price": 0, "change": 0, "turnover": 0},
                {"code": "002594", "name": "比亚迪", "price": 0, "change": 0, "turnover": 0},
                {"code": "300750", "name": "宁德时代", "price": 0, "change": 0, "turnover": 0},
                {"code": "601318", "name": "中国平安", "price": 0, "change": 0, "turnover": 0},
                {"code": "600519", "name": "贵州茅台", "price": 0, "change": 0, "turnover": 0},
                {"code": "002415", "name": "海康威视", "price": 0, "change": 0, "turnover": 0},
                {"code": "601899", "name": "紫金矿业", "price": 0, "change": 0, "turnover": 0}
            ],
            "lastUpdate": ""
        })

    if not os.path.exists(EMAIL_FILE):
        save_json_file(EMAIL_FILE, {
            "emails": {},
            "lastUpdate": ""
        })

    if not os.path.exists(SENT_EMAILS_FILE):
        save_json_file(SENT_EMAILS_FILE, {
            "dates": {}
        })

    print("=" * 50)
    print("股票监控系统 Web 应用 (使用 AkShare 免费数据接口)")
    print("访问地址: http://localhost:5000")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=False)
