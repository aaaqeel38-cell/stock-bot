import os
import requests
import json
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8323085330:AAGMhk8EqNnGbavDNZNir4ARCAPOrGY3u8c")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text, parse_mode="Markdown"):
    url = f"{TELEGRAM_API}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    requests.post(url, json=data)

def get_stock_price_us(symbol):
    """Get US stock data from Yahoo Finance"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("chartPreviousClose", 0)
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        name = meta.get("longName", symbol)
        currency = meta.get("currency", "USD")
        return {
            "name": name,
            "symbol": symbol.upper(),
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "currency": currency,
            "market": "US"
        }
    except Exception as e:
        return None

def get_stock_price_sa(symbol):
    """Get Saudi stock data from Yahoo Finance (add .SR suffix)"""
    return get_stock_price_us(f"{symbol}.SR")

def get_technical_analysis(symbol, is_saudi=False):
    """Get OHLCV data and calculate basic technical indicators"""
    ticker = f"{symbol}.SR" if is_saudi else symbol
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=3mo"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["closes"] if "closes" in result["indicators"]["quote"][0] else result["indicators"]["quote"][0].get("close", [])
        closes = [c for c in closes if c is not None]
        
        if len(closes) < 14:
            return None
        
        # RSI
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # Moving Averages
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        
        # Support & Resistance (simple: min/max of last 30 days)
        recent = closes[-30:]
        support = min(recent)
        resistance = max(recent)
        
        current = closes[-1]
        
        # Signal
        signal = "محايد ⚪"
        if rsi < 30:
            signal = "تشبع بيعي — فرصة شراء محتملة 🟢"
        elif rsi > 70:
            signal = "تشبع شرائي — احذر 🔴"
        elif ma20 and current > ma20:
            signal = "فوق المتوسط — اتجاه صاعد 🟢"
        elif ma20 and current < ma20:
            signal = "تحت المتوسط — اتجاه هابط 🔴"
        
        return {
            "rsi": rsi,
            "ma20": ma20,
            "ma50": ma50,
            "support": support,
            "resistance": resistance,
            "signal": signal,
            "current": current
        }
    except Exception as e:
        return None

def format_stock_report(stock, tech):
    arrow = "🟢 ▲" if stock["change"] >= 0 else "🔴 ▼"
    change_str = f"{arrow} {abs(stock['change']):.2f} ({abs(stock['change_pct']):.2f}%)"
    
    report = f"""
📊 *{stock['name']}* ({stock['symbol']})
━━━━━━━━━━━━━━━━━━
💰 *السعر:* {stock['price']:.2f} {stock['currency']}
📈 *التغيير:* {change_str}
"""
    if tech:
        report += f"""
━━━━━━━━━━━━━━━━━━
🔬 *التحليل الفني:*
• RSI: {tech['rsi']:.1f}
• MA20: {f"{tech['ma20']:.2f}" if tech['ma20'] else 'N/A'}
• MA50: {f"{tech['ma50']:.2f}" if tech['ma50'] else 'N/A'}
• دعم: {tech['support']:.2f}
• مقاومة: {tech['resistance']:.2f}

🎯 *الإشارة:* {tech['signal']}
"""
    report += f"\n⏰ _{datetime.now().strftime('%Y-%m-%d %H:%M')}_"
    report += "\n\n⚠️ _هذا تحليل إعلامي وليس نصيحة استثمارية_"
    return report

def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    
    if text.startswith("/start"):
        send_message(chat_id, """
🤖 *مرحباً بك في بوت تحليل الأسهم!*
━━━━━━━━━━━━━━━━━━
*الأوامر المتاحة:*

📌 `/sa 2222` — تحليل سهم سعودي (رمز تداول)
📌 `/us AAPL` — تحليل سهم أمريكي
📌 `/price 2222` — سعر سهم سعودي فقط
📌 `/help` — المساعدة

*أمثلة:*
• `/sa 2222` ← أرامكو
• `/us TSLA` ← تسلا
• `/us NVDA` ← نفيديا
        """)
    
    elif text.startswith("/sa ") or text.startswith("/sa"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "⚠️ اكتب رمز السهم، مثال: `/sa 2222`")
            return
        symbol = parts[1]
        send_message(chat_id, f"⏳ جاري تحليل سهم {symbol}...")
        stock = get_stock_price_sa(symbol)
        if not stock:
            send_message(chat_id, f"❌ ما قدرت أحصل على بيانات للرمز `{symbol}`\nتأكد من صحة الرمز (مثال: 2222 لأرامكو)")
            return
        tech = get_technical_analysis(symbol, is_saudi=True)
        report = format_stock_report(stock, tech)
        send_message(chat_id, report)
    
    elif text.startswith("/us ") or text.startswith("/us"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "⚠️ اكتب رمز السهم، مثال: `/us AAPL`")
            return
        symbol = parts[1].upper()
        send_message(chat_id, f"⏳ جاري تحليل سهم {symbol}...")
        stock = get_stock_price_us(symbol)
        if not stock:
            send_message(chat_id, f"❌ ما قدرت أحصل على بيانات للرمز `{symbol}`")
            return
        tech = get_technical_analysis(symbol, is_saudi=False)
        report = format_stock_report(stock, tech)
        send_message(chat_id, report)
    
    elif text.startswith("/price "):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "⚠️ اكتب رمز السهم، مثال: `/price 2222`")
            return
        symbol = parts[1]
        stock = get_stock_price_sa(symbol)
        if not stock:
            stock = get_stock_price_us(symbol.upper())
        if not stock:
            send_message(chat_id, f"❌ ما قدرت أحصل على بيانات للرمز `{symbol}`")
            return
        arrow = "🟢 ▲" if stock["change"] >= 0 else "🔴 ▼"
        send_message(chat_id, f"💰 *{stock['name']}*\n{stock['price']:.2f} {stock['currency']} {arrow} {abs(stock['change_pct']):.2f}%")
    
    elif text.startswith("/help"):
        send_message(chat_id, """
📖 *المساعدة*
━━━━━━━━━━━━━━━━━━
`/sa [رمز]` — تحليل سهم سعودي
`/us [رمز]` — تحليل سهم أمريكي  
`/price [رمز]` — سعر فقط

*أمثلة رموز سعودية:*
2222 أرامكو | 1120 الراجحي
2010 سابك | 7010 STC

*أمثلة رموز أمريكية:*
AAPL آبل | TSLA تسلا
NVDA نفيديا | AMZN أمازون
        """)
    else:
        send_message(chat_id, "❓ الأمر غير معروف. اكتب /help للمساعدة")

def main():
    print("🤖 البوت شغال...")
    offset = None
    while True:
        try:
            url = f"{TELEGRAM_API}/getUpdates"
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset
            r = requests.get(url, params=params, timeout=35)
            updates = r.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])
        except Exception as e:
            print(f"Error: {e}")
            import time
            time.sleep(5)

if __name__ == "__main__":
    main()
