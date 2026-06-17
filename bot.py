import os
import requests
import json
from datetime import datetime
import time

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8323085330:AAGMhk8EqNnGbavDNZNir4ARCAPOrGY3u8c")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
RISK_PERCENT = 5

def send_message(chat_id, text, parse_mode="Markdown"):
    url = f"{TELEGRAM_API}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(url, json=data, timeout=10)
    except:
        pass

def get_ohlcv(ticker, period="6mo", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={period}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        result = data["chart"]["result"][0]
        meta = result["meta"]
        quotes = result["indicators"]["quote"][0]
        def clean(lst):
            return [x if x is not None else 0 for x in lst]
        return {
            "meta": meta,
            "closes": clean(quotes.get("close", [])),
            "highs": clean(quotes.get("high", [])),
            "lows": clean(quotes.get("low", [])),
            "volumes": clean(quotes.get("volume", [])),
            "opens": clean(quotes.get("open", []))
        }
    except:
        return None

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_macd(closes):
    def ema(data, period):
        if len(data) < period:
            return None
        k = 2 / (period + 1)
        val = sum(data[:period]) / period
        for p in data[period:]:
            val = p * k + val * (1 - k)
        return round(val, 4)
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    if not ema12 or not ema26:
        return None, None, None
    macd_line = round(ema12 - ema26, 4)
    macd_vals = []
    for i in range(26, len(closes)):
        e12 = ema(closes[:i], 12)
        e26 = ema(closes[:i], 26)
        if e12 and e26:
            macd_vals.append(e12 - e26)
    signal = ema(macd_vals, 9) if len(macd_vals) >= 9 else None
    histogram = round(macd_line - signal, 4) if signal else None
    return macd_line, round(signal, 4) if signal else None, histogram

def calc_bollinger(closes, period=20):
    if len(closes) < period:
        return None, None, None
    recent = closes[-period:]
    ma = sum(recent) / period
    std = (sum((x - ma) ** 2 for x in recent) / period) ** 0.5
    return round(ma + 2*std, 2), round(ma, 2), round(ma - 2*std, 2)

def calc_stochastic(closes, highs, lows, k_period=14):
    if len(closes) < k_period:
        return None, None
    highest = max(highs[-k_period:])
    lowest = min(lows[-k_period:])
    if highest == lowest:
        return 50, 50
    k = round(((closes[-1] - lowest) / (highest - lowest)) * 100, 2)
    return k, k

def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 4)

def calc_support_resistance(highs, lows, periods=30):
    rh = sorted(set([round(h, 1) for h in highs[-periods:]]), reverse=True)
    rl = sorted(set([round(l, 1) for l in lows[-periods:]]))
    r1 = rh[0] if rh else 0
    r2 = rh[1] if len(rh) > 1 else r1
    s1 = rl[0] if rl else 0
    s2 = rl[1] if len(rl) > 1 else s1
    return s1, s2, r1, r2

def calc_volume(volumes):
    if len(volumes) < 20:
        return 0, 0, 1
    avg = sum(volumes[-20:]) / 20
    curr = volumes[-1]
    return round(avg), round(curr), round(curr/avg, 2) if avg > 0 else 1

def determine_trend(closes, ma20, ma50):
    if not ma20 or not ma50:
        return "محايد"
    c = closes[-1]
    if c > ma20 and ma20 > ma50:
        return "صاعد"
    elif c < ma20 and ma20 < ma50:
        return "هابط"
    return "محايد"

def calc_trade_zones(current, atr, s1, r1, trend):
    """
    شراء:  دخول = current، SL تحته، أهداف فوقه
    بيع:   دخول = current، SL فوقه، أهداف تحته
    محايد: لا صفقة
    """
    if atr is None or atr == 0:
        atr = current * 0.02

    if trend == "صاعد":
        entry1 = round(current, 2)
        entry2 = round(current * 0.99, 2)          # دخول أفضل عند تراجع بسيط
        stop_loss = round(s1 - atr * 0.3, 2)       # تحت الدعم
        target1 = round(current + atr * 1.5, 2)
        target2 = round(current + atr * 3.0, 2)
        target3 = round(r1, 2)
        sl_pct = round(abs(entry1 - stop_loss) / entry1 * 100, 2)
        rr = round((target1 - entry1) / (entry1 - stop_loss), 2) if entry1 != stop_loss else 0
        trade_type = "🟢 شراء (Long)"

    elif trend == "هابط":
        entry1 = round(current, 2)
        entry2 = round(current * 1.01, 2)           # دخول أفضل عند ارتداد بسيط
        stop_loss = round(r1 + atr * 0.3, 2)        # فوق المقاومة
        target1 = round(current - atr * 1.5, 2)
        target2 = round(current - atr * 3.0, 2)
        target3 = round(s1, 2)
        sl_pct = round(abs(stop_loss - entry1) / entry1 * 100, 2)
        rr = round((entry1 - target1) / (stop_loss - entry1), 2) if entry1 != stop_loss else 0
        trade_type = "🔴 بيع (Short)"

    else:
        return None

    return {
        "trade_type": trade_type,
        "entry1": entry1,
        "entry2": entry2,
        "stop_loss": stop_loss,
        "target1": target1,
        "target2": target2,
        "target3": target3,
        "sl_pct": sl_pct,
        "rr": rr
    }

def get_decision(rsi, macd, histogram, trend, vol_ratio, stoch_k, bb_upper, bb_lower, current):
    score = 0
    signals = []
    if rsi:
        if rsi < 30: score += 2; signals.append("RSI تشبع بيعي 🟢")
        elif rsi < 45: score += 1; signals.append("RSI منطقة شراء 🟢")
        elif rsi > 70: score -= 2; signals.append("RSI تشبع شرائي 🔴")
        elif rsi > 55: score -= 1
    if macd and histogram:
        if macd > 0 and histogram > 0: score += 2; signals.append("MACD إيجابي 🟢")
        elif macd < 0 and histogram < 0: score -= 2; signals.append("MACD سلبي 🔴")
    if trend == "صاعد": score += 2; signals.append("اتجاه صاعد 🟢")
    elif trend == "هابط": score -= 2; signals.append("اتجاه هابط 🔴")
    if vol_ratio and vol_ratio > 1.5: signals.append(f"حجم مرتفع x{vol_ratio} ⚡")
    if bb_lower and current < bb_lower: score += 1; signals.append("تحت بولينجر السفلي 🟢")
    elif bb_upper and current > bb_upper: score -= 1; signals.append("فوق بولينجر العلوي 🔴")
    if stoch_k:
        if stoch_k < 20: score += 1; signals.append("ستوكاستك تشبع بيعي 🟢")
        elif stoch_k > 80: score -= 1; signals.append("ستوكاستك تشبع شرائي 🔴")

    if score >= 4: decision = "🟢 شراء قوي"
    elif score >= 2: decision = "🟡 شراء محتمل"
    elif score <= -4: decision = "🔴 بيع قوي"
    elif score <= -2: decision = "🟠 بيع محتمل"
    else: decision = "⚪ محايد — انتظر"

    return decision, signals, score

def full_analysis(symbol, is_saudi=False):
    ticker = f"{symbol}.SR" if is_saudi else symbol.upper()
    data = get_ohlcv(ticker)
    if not data:
        return None

    closes = data["closes"]
    highs = data["highs"]
    lows = data["lows"]
    volumes = data["volumes"]
    meta = data["meta"]

    current = closes[-1]
    prev = closes[-2] if len(closes) > 1 else current
    change = current - prev
    change_pct = (change / prev * 100) if prev else 0

    rsi = calc_rsi(closes)
    macd_line, signal_line, histogram = calc_macd(closes)
    bb_upper, bb_mid, bb_lower = calc_bollinger(closes)
    stoch_k, stoch_d = calc_stochastic(closes, highs, lows)
    atr = calc_atr(highs, lows, closes)
    s1, s2, r1, r2 = calc_support_resistance(highs, lows)
    ma20 = round(sum(closes[-20:])/20, 2) if len(closes)>=20 else None
    ma50 = round(sum(closes[-50:])/50, 2) if len(closes)>=50 else None
    ma200 = round(sum(closes[-200:])/200, 2) if len(closes)>=200 else None
    avg_vol, curr_vol, vol_ratio = calc_volume(volumes)
    trend = determine_trend(closes, ma20, ma50)
    zones = calc_trade_zones(current, atr, s1, r1, trend)
    decision, signals, score = get_decision(rsi, macd_line, histogram, trend, vol_ratio, stoch_k, bb_upper, bb_lower, current)

    return {
        "name": meta.get("longName", symbol),
        "symbol": symbol.upper(),
        "currency": meta.get("currency", "SAR" if is_saudi else "USD"),
        "current": current, "change": change, "change_pct": change_pct,
        "rsi": rsi, "macd": macd_line, "macd_signal": signal_line, "histogram": histogram,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
        "stoch_k": stoch_k, "stoch_d": stoch_d, "atr": atr,
        "s1": s1, "s2": s2, "r1": r1, "r2": r2,
        "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "avg_vol": avg_vol, "curr_vol": curr_vol, "vol_ratio": vol_ratio,
        "trend": trend, "zones": zones,
        "decision": decision, "signals": signals, "score": score
    }

def format_report(d):
    arrow = "🟢 ▲" if d["change"] >= 0 else "🔴 ▼"
    z = d["zones"]

    report = f"""
╔══════════════════════╗
  📊 {d['name']}
  🔖 {d['symbol']} | {d['currency']}
╚══════════════════════╝

💰 *السعر الحالي:* `{d['current']:.2f}`
{arrow} `{abs(d['change']):.2f}` ({abs(d['change_pct']):.2f}%)

━━━━━━━━━━━━━━━━━━━━━━
📐 *المؤشرات الفنية*
━━━━━━━━━━━━━━━━━━━━━━
• RSI: `{d['rsi']}` {'🔴 تشبع شرائي' if d['rsi'] and d['rsi']>70 else '🟢 تشبع بيعي' if d['rsi'] and d['rsi']<30 else '⚪ محايد'}
• MACD: `{d['macd']}` | إشارة: `{d['macd_signal']}`
• هيستوجرام: `{d['histogram']}`
• ستوكاستك: `{d['stoch_k']}`
• ATR: `{d['atr']}`

━━━━━━━━━━━━━━━━━━━━━━
📈 *المتوسطات المتحركة*
━━━━━━━━━━━━━━━━━━━━━━
• MA20: `{d['ma20']}` {'✅ فوقه' if d['current'] > (d['ma20'] or 0) else '❌ تحته'}
• MA50: `{d['ma50']}` {'✅ فوقه' if d['current'] > (d['ma50'] or 0) else '❌ تحته'}
• MA200: `{d['ma200'] or 'غير متاح'}`
• الاتجاه: *{d['trend']}*

━━━━━━━━━━━━━━━━━━━━━━
🎯 *بولينجر باند*
━━━━━━━━━━━━━━━━━━━━━━
• العلوي: `{d['bb_upper']}`
• الوسط: `{d['bb_mid']}`
• السفلي: `{d['bb_lower']}`

━━━━━━━━━━━━━━━━━━━━━━
🏗️ *الدعم والمقاومة*
━━━━━━━━━━━━━━━━━━━━━━
• مقاومة 2: `{d['r2']}` ⬆️
• مقاومة 1: `{d['r1']}` ⬆️
• السعر: `{d['current']:.2f}` 📍
• دعم 1: `{d['s1']}` ⬇️
• دعم 2: `{d['s2']}` ⬇️

━━━━━━━━━━━━━━━━━━━━━━
📦 *حجم التداول*
━━━━━━━━━━━━━━━━━━━━━━
• الحالي: `{d['curr_vol']:,}`
• المتوسط: `{d['avg_vol']:,}`
• النسبة: `x{d['vol_ratio']}` {'⚡ مرتفع' if d['vol_ratio'] and d['vol_ratio']>1.5 else ''}
"""

    if z:
        is_buy = "شراء" in z['trade_type']
        report += f"""
━━━━━━━━━━━━━━━━━━━━━━
💼 *نوع الصفقة: {z['trade_type']}*
━━━━━━━━━━━━━━━━━━━━━━
"""
        if is_buy:
            report += f"""🟢 دخول 1: `{z['entry1']}`
🟢 دخول 2 (أفضل): `{z['entry2']}` ← عند تراجع بسيط
🛑 وقف الخسارة: `{z['stop_loss']}` ({z['sl_pct']}%) ← تحت الدعم
🎯 هدف 1: `{z['target1']}`
🎯 هدف 2: `{z['target2']}`
🏆 هدف 3: `{z['target3']}`
⚖️ مخاطرة/عائد: `1:{z['rr']}`

📌 *ترتيب الأسعار (شراء):*
`{z['stop_loss']}` 🛑 ← وقف خسارة
`{z['entry2']}` 🟢 ← دخول أفضل  
`{z['entry1']}` 🟢 ← دخول الآن
`{z['target1']}` 🎯 ← هدف 1
`{z['target2']}` 🎯 ← هدف 2
`{z['target3']}` 🏆 ← هدف 3
"""
        else:
            report += f"""🔴 دخول 1: `{z['entry1']}`
🔴 دخول 2 (أفضل): `{z['entry2']}` ← عند ارتداد بسيط
🛑 وقف الخسارة: `{z['stop_loss']}` ({z['sl_pct']}%) ← فوق المقاومة
🎯 هدف 1: `{z['target1']}`
🎯 هدف 2: `{z['target2']}`
🏆 هدف 3: `{z['target3']}`
⚖️ مخاطرة/عائد: `1:{z['rr']}`

📌 *ترتيب الأسعار (بيع):*
`{z['target3']}` 🏆 ← هدف 3
`{z['target2']}` 🎯 ← هدف 2
`{z['target1']}` 🎯 ← هدف 1
`{z['entry1']}` 🔴 ← دخول الآن
`{z['entry2']}` 🔴 ← دخول أفضل
`{z['stop_loss']}` 🛑 ← وقف خسارة
"""
    else:
        report += """
━━━━━━━━━━━━━━━━━━━━━━
⚪ *لا توجد صفقة واضحة*
━━━━━━━━━━━━━━━━━━━━━━
الاتجاه محايد — انتظر إشارة أوضح
"""

    report += f"""
━━━━━━━━━━━━━━━━━━━━━━
🤖 *القرار الكلي*
━━━━━━━━━━━━━━━━━━━━━━
*{d['decision']}* (النقاط: {d['score']})

"""
    for sig in d['signals']:
        report += f"  • {sig}\n"

    report += f"\n⏰ _{datetime.now().strftime('%Y-%m-%d %H:%M')}_"
    report += "\n⚠️ _تحليل تقني فقط، ليس توصية استثمارية_"
    return report

def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text.startswith("/start"):
        send_message(chat_id, """
🤖 *بوت تحليل الأسهم الاحترافي*
━━━━━━━━━━━━━━━━━━━━━━
`/sa 2222` — سهم سعودي
`/us AAPL` — سهم أمريكي
`/help` — المساعدة

✅ يحدد نوع الصفقة (شراء/بيع)
✅ وقف الخسارة في المكان الصح دائماً
✅ 3 أهداف ربح واضحة
✅ ترتيب الأسعار بشكل منطقي
        """)

    elif text.startswith("/sa"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "⚠️ مثال: `/sa 2222`")
            return
        send_message(chat_id, f"⏳ جاري التحليل...")
        result = full_analysis(parts[1], is_saudi=True)
        if not result:
            send_message(chat_id, "❌ ما قدرت أحصل على البيانات، تأكد من الرمز")
            return
        send_message(chat_id, format_report(result))

    elif text.startswith("/us"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "⚠️ مثال: `/us AAPL`")
            return
        send_message(chat_id, f"⏳ جاري التحليل...")
        result = full_analysis(parts[1].upper(), is_saudi=False)
        if not result:
            send_message(chat_id, "❌ ما قدرت أحصل على البيانات، تأكد من الرمز")
            return
        send_message(chat_id, format_report(result))

    elif text.startswith("/help"):
        send_message(chat_id, """
📖 *المساعدة*
━━━━━━━━━━━━━━━━━━━━━━
`/sa [رمز]` — سهم سعودي
`/us [رمز]` — سهم أمريكي

*أمثلة سعودية:*
2222 أرامكو | 1120 الراجحي
2010 سابك | 7010 STC

*أمثلة أمريكية:*
AAPL | TSLA | NVDA | AMZN
        """)
    else:
        send_message(chat_id, "❓ اكتب /help للمساعدة")

def main():
    print("🤖 البوت الاحترافي شغّال...")
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
            time.sleep(5)

if __name__ == "__main__":
    main()
