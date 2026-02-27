# 股票监控系统 Web 应用

基于拉升资金与主力资金指标的智能股票交易提醒系统。

## 功能特点

1. **股票管理**
   - 支持监控10只股票（可扩展）
   - 可在网页端直接编辑股票代码
   - 自动获取股票名称和实时数据

2. **实时数据**
   - 最新价格
   - 涨跌幅（红涨绿跌）
   - 换手率/成交量

3. **邮件提醒**
   - 买入信号提醒
   - 卖出信号提醒
   - 今日/昨日邮件记录展示

4. **Web 控制面板**
   - 启动/停止监控
   - 刷新股票数据
   - 实时状态显示

## 数据源

- **Tushare Pro**：K线数据（需要 token）
- **AkShare**：股票名称缓存（免费）
- **新浪财经**：实时行情备选（免费）

## 安装步骤

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置参数

编辑 `stockBS.py` 文件，修改以下配置：

```python
# Tushare token（需要到 https://tushare.pro 注册获取）
TS_TOKEN = "your_token_here"

# 邮件配置
EMAIL_USER = "your_email@163.com"
EMAIL_PWD = "your_email_password"  # 163邮箱使用授权码
EMAIL_TO = "receiver@qq.com"
```

### 3. 启动应用

```bash
python stockBS.py
```

### 4. 访问网页

在浏览器中打开：`http://localhost:5000`

## 技术指标说明

### 拉升资金
- 基于 EMA（指数移动平均）计算
- 反映短期资金流入流出情况

### 主力资金
- 基于 EMA 跨度计算
- 反映大资金动向

### 买入条件（满足任一）
1. 拉升资金由0转正
2. 拉升资金增量 > 0.1

### 卖出条件（满足任一）
1. 拉升资金减量 < -0.05 且前一天增量 > 0.001
2. 主力资金从 > 0.01 下穿到 < 0

## 项目结构

```
StockBS/
├── stockBS.py       # Flask Web 应用（主程序）
├── app.py           # 旧版本（已弃用，可删除）
├── index.html       # 前端页面
├── stocks.json      # 股票列表数据
├── email.json       # 邮件记录（今日/昨日）
├── sent_emails.json # 按日期记录的发送历史
├── requirements.txt # Python 依赖
└── README.md        # 说明文档
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 返回主页 |
| `/api/stocks` | GET | 获取股票列表（含邮件记录） |
| `/api/stocks/update` | POST | 更新股票代码 |
| `/api/refresh` | POST | 刷新股票数据 |
| `/api/analyze` | POST | 分析单只股票信号 |
| `/api/monitor/start` | POST | 启动监控 |
| `/api/monitor/stop` | POST | 停止监控 |
| `/api/status` | GET | 获取系统状态 |

## 注意事项

1. Tushare token 需要注册获取：https://tushare.pro
2. 163邮箱需要开启SMTP服务并获取授权码
3. 建议在交易日 9:30-15:00 之间运行监控
4. 数据更新频率：
   - 交易时间：每60秒检查一次
   - 非交易时间：每600秒检查一次

## 常见问题

**Q: 股票数据为0？**
A: 请检查 Tushare token 是否有效，或等待交易日数据更新。

**Q: 邮件发送失败？**
A: 请检查邮箱配置，确保SMTP服务已开启并使用授权码。

**Q: 监控无反应？**
A: 请确认当前是否在交易时间内（工作日 9:30-15:00），非交易时间也会运行但频率较低。

**Q: 前端看不到邮件记录？**
A: 邮件记录使用6位标准股票代码作为key存储，确保 stocks.json 中的代码格式一致。
