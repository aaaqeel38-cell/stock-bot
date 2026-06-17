import os
import requests
import json
from datetime import datetime
import time

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8323085330:AAGMhk8EqNnGbavDNZNir4ARCAPOrGY3u8c")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
RISK_PERCENT = 5  # نسبة المخاطرة

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
        timestamps = result["timestamp"]

        closes = quotes.get("close", [])
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        volumes = quotes.get("volume", [])
        opens = quotes.get("open", [])

        # تنظيف None
        def clean(lst):
            return [x if x is not None else 0 for x in lst]

        return {
            "meta": meta,
            "closes": clean(closes),
            "highs": clean(highs),
            "lows": clean(lows),
            "volumes": clean(volumes),
            "opens": clean(opens),
            "timestamps": timestamps
        }
    except Exception as e:
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
        ema_val = sum(data[:period]) / period
        for price in data[period:]:
            ema_val = price * k + ema_val * (1 - k)
        return round(ema_val, 4)

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    if ema12 is None or ema26 is None:
        return None, None, None
    macd_line = round(ema12 - ema26, 4)

    # Signal line (9 EMA of MACD) - simplified
    macd_values = []
    for i in range(26, len(closes)):
        e12 = ema(closes[:i], 12)
        e26 = ema(closes[:i], 26)
        if e12 and e26:
            macd_values.append(e12 - e26)

    signal = ema(macd_values, 9) if len(macd_values) >= 9 else None
    histogram = round(macd_line - signal, 4) if signal else None
    return macd_line, round(signal, 4) if signal else None, histogram

def calc_bollinger(closes, period=20):
    if len(closes) < period:
        return None, None, None
    recent = closes[-period:]
    ma = sum(recent) / period
    std = (sum((x - ma) ** 2 for x in recent) / period) ** 0.5
    upper = round(ma + 2 * std, 2)
    lower = round(ma - 2 * std, 2)
    return round(upper, 2), round(ma, 2), round(lower, 2)

def calc_stochastic(closes, highs, lows, k_period=14):
    if len(closes) < k_period:
        return None, None
    recent_highs = highs[-k_period:]
    recent_lows = lows[-k_period:]
    highest = max(recent_highs)
    lowest = min(recent_lows)
    if highest == lowest:
        return 50, 50
    k = round(((closes[-1] - lowest) / (highest - lowest)) * 100, 2)
    # D = 3-period SMA of K (simplified)
    d = k
    return k, d

def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    return round(atr, 4)

def calc_support_resistance(highs, lows, closes, periods=30):
    recent_highs = highs[-periods:]
    recent_lows = lows[-periods:]
    resistance = round(max(recent_highs), 2)
    support = round(min(recent_lows), 2)

    # مناطق دعم ومقاومة متعددة
    sorted_highs = sorted(set([round(h, 1) for h in recent_highs]), reverse=True)
    sorted_lows = sorted(set([round(l, 1) for l in recent_lows]))

    r1 = sorted_highs[0] if sorted_highs else resistance
    r2 = sorted_highs[1] if len(sorted_highs) > 1 else resistance
    s1 = sorted_lows[0] if sorted_lows else support
    s2 = sorted_lows[1] if len(sorted_lows) > 1 else support

    return support, resistance, s1, s2, r1, r2

def calc_volume_analysis(volumes):
    if len(volumes) < 20:
        return None, None
    avg_vol = sum(volumes[-20:]) / 20
    current_vol = volumes[-1]
    vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1
    return round(avg_vol), round(current_vol), vol_ratio

def calc_entry_exit(current_price, atr, support, resistance, rsi, trend):
    """حساب مناطق الدخول والخروج وحد الخسارة"""
    risk = RISK_PERCENT / 100

    if trend == "صاعد":
        # دخول عند الدعم أو الارتداد
        entry1 = round(current_price, 2)
        entry2 = round(current_price * 0.99, 2)  # دخول ثاني أفضل
        stop_loss = round(support - (atr * 0.5), 2)
        target1 = round(current_price + (atr * 2), 2)
        target2 = round(current_price + (atr * 3.5), 2)
        target3 = round(resistance, 2)
        risk_reward = round((target1 - entry1) / (entry1 - stop_loss), 2) if entry1 != stop_loss else 0

    else:  # هابط أو محايد
        entry1 = round(current_price, 2)
        entry2 = round(current_price * 1.01, 2)
        stop_loss = round(resistance + (atr * 0.5), 2)
        target1 = round(current_price - (atr * 2), 2)
        target2 = round(current_price - (atr * 3.5), 2)
        target3 = round(support, 2)
        risk_reward = round((entry1 - target1) / (stop_loss - entry1), 2) if entry1 != stop_loss else 0

    return {
        "entry1": entry1,
        "entry2": entry2,
        "stop_loss": stop_loss,
        "target1": target1,
        "target2": target2,
        "target3": target3,
        "risk_reward": risk_reward,
        "sl_percent": round(abs(entry1 - stop_loss) / entry1 * 100, 2)
    }

def determine_trend(closes, ma20, ma50):
    if not ma20 or not ma50:
        return "محايد"
    current = closes[-1]
    if current > ma20 > ma50:
        return "صاعد"
    elif current < ma20 < ma50:
        return "هابط"
    else:
        return "محايد"

def get_overall_signal(rsi, macd, histogram, trend, vol_ratio, stoch_k, bb_upper, bb_lower, current):
    score = 0
    signals = []

    # RSI
    if rsi:
        if rsi < 30:
            score += 2
            signals.append("RSI تشبع بيعي 🟢")
        elif rsi < 45:
            score += 1
            signals.append("RSI منطقة شراء 🟢")
        elif rsi > 70:
            score -= 2
            signals.append("RSI تشبع شرائي 🔴")
        elif rsi > 55:
            score -= 1

    # MACD
    if macd and histogram:
        if macd > 0 and histogram > 0:
            score += 2
            signals.append("MACD إيجابي 🟢")
        elif macd < 0 and histogram < 0:
            score -= 2
            signals.append("MACD سلبي 🔴")

    # Trend
    if trend == "صاعد":
        score += 2
        signals.append("اتجاه صاعد 🟢")
    elif trend == "هابط":
        score -= 2
        signals.append("اتجاه هابط 🔴")

    # Volume
    if vol_ratio and vol_ratio > 1.5:
        signals.append(f"حجم مرتفع x{vol_ratio} ⚡")

    # Bollinger
    if bb_lower and current < bb_lower:
        score += 1
        signals.append("تحت بولينجر السفلي 🟢")
    elif bb_upper and current > bb_upper:
        score -= 1
        signals.append("فوق بولينجر العلوي 🔴")

    # Stochastic
    if stoch_k and stoch_k < 20:
        score += 1
        signals.append("ستوكاستك تشبع بيعي 🟢")
    elif stoch_k and stoch_k > 80:
        score -= 1
        signals.append("ستوكاستك تشبع شرائي 🔴")

    # القرار النهائي
    if score >= 4:
        decision = "🟢 شراء قوي"
    elif score >= 2:
        decision = "🟡 شراء محتمل"
    elif score <= -4:
        decision = "🔴 بيع قوي"
    elif score <= -2:
        decision = "🟠 بيع محتمل"
    else:
        decision = "⚪ محايد — انتظر"

    return decision, signals, score

def full_analysis(symbol, is_saudi=False):
    ticker = f"{symbol}.SR" if is_saudi else symbol.upper()

    # جلب بيانات يومية
    data = get_ohlcv(ticker, period="6mo", interval="1d")
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

    name = meta.get("longName", symbol)
    currency = meta.get("currency", "SAR" if is_saudi else "USD")

    # المؤشرات
    rsi = calc_rsi(closes)
    macd_line, signal_line, histogram = calc_macd(closes)
    bb_upper, bb_mid, bb_lower = calc_bollinger(closes)
    stoch_k, stoch_d = calc_stochastic(closes, highs, lows)
    atr = calc_atr(highs, lows, closes)
    support, resistance, s1, s2, r1, r2 = calc_support_resistance(highs, lows, closes)

    # المتوسطات
    ma20 = round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None
    ma50 = round(sum(closes[-50:]) / 50, 2) if len(closes) >= 50 else None
    ma200 = round(sum(closes[-200:]) / 200, 2) if len(closes) >= 200 else None

    # حجم التداول
    avg_vol, curr_vol, vol_ratio = calc_volume_analysis(volumes)

    # الاتجاه
    trend = determine_trend(closes, ma20, ma50)

    # مناطق الدخول والخروج
    zones = calc_entry_exit(current, atr or 1, support, resistance, rsi, trend)

    # القرار الكلي
    decision, signals_list, score = get_overall_signal(
        rsi, macd_line, histogram, trend, vol_ratio, stoch_k, bb_upper, bb_lower, current
    )

    return {
        "name": name,
        "symbol": symbol.upper(),
        "currency": currency,
        "current": current,
        "change": change,
        "change_pct": change_pct,
        "rsi": rsi,
        "macd": macd_line,
        "macd_signal": signal_line,
        "histogram": histogram,
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "atr": atr,
        "support": support,
        "resistance": resistance,
        "s1": s1, "s2": s2, "r1": r1, "r2": r2,
        "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "avg_vol": avg_vol, "curr_vol": curr_vol, "vol_ratio": vol_ratio,
        "trend": trend,
        "zones": zones,
        "decision": decision,
        "signals": signals_list,
        "score": score
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
• RSI (14): `{d['rsi']}` {'🔴 تشبع شرائي' if d['rsi'] and d['rsi']>70 else '🟢 تشبع بيعي' if d['rsi'] and d['rsi']<30 else '⚪ محايد'}
• MACD: `{d['macd']}` | إشارة: `{d['macd_signal']}` | هيستوجرام: `{d['histogram']}`
• ستوكاستك K: `{d['stoch_k']}` | D: `{d['stoch_d']}`
• ATR (14): `{d['atr']}`

━━━━━━━━━━━━━━━━━━━━━━
📈 *المتوسطات المتحركة*
━━━━━━━━━━━━━━━━━━━━━━
• MA20: `{d['ma20']}` {'✅' if d['current'] > (d['ma20'] or 0) else '❌'}
• MA50: `{d['ma50']}` {'✅' if d['current'] > (d['ma50'] or 0) else '❌'}
• MA200: `{d['ma200'] or 'غير متاح'}` {'✅' if d['ma200'] and d['current'] > d['ma200'] else '❌' if d['ma200'] else ''}
• الاتجاه العام: *{d['trend']}*

━━━━━━━━━━━━━━━━━━━━━━
🎯 *بولينجر باند*
━━━━━━━━━━━━━━━━━━━━━━
• العلوي: `{d['bb_upper']}`
• الوسط: `{d['bb_mid']}`
• السفلي: `{d['bb_lower']}`

━━━━━━━━━━━━━━━━━━━━━━
🏗️ *الدعم والمقاومة*
━━━━━━━━━━━━━━━━━━━━━━
• مقاومة 2: `{d['r2']}`
• مقاومة 1: `{d['r1']}` ⬆️
• السعر الحالي: `{d['current']:.2f}` 📍
• دعم 1: `{d['s1']}` ⬇️
• دعم 2: `{d['s2']}`

━━━━━━━━━━━━━━━━━━━━━━
📦 *حجم التداول*
━━━━━━━━━━━━━━━━━━━━━━
• الحالي: `{d['curr_vol']:,}`
• المتوسط (20): `{d['avg_vol']:,}`
• النسبة: `x{d['vol_ratio']}` {'⚡ مرتفع' if d['vol_ratio'] and d['vol_ratio']>1.5 else ''}

━━━━━━━━━━━━━━━━━━━━━━
🎯 *مناطق الدخول والخروج*
━━━━━━━━━━━━━━━━━━━━━━
🟢 دخول 1: `{z['entry1']}`
🟢 دخول 2 (أفضل): `{z['entry2']}`
🛑 وقف الخسارة: `{z['stop_loss']}` ({z['sl_percent']}%)
🎯 هدف 1: `{z['target1']}`
🎯 هدف 2: `{z['target2']}`
🏆 هدف 3: `{z['target3']}`
⚖️ نسبة المخاطرة/العائد: `1:{z['risk_reward']}`

━━━━━━━━━━━━━━━━━━━━━━
🤖 *القرار الكلي*
━━━━━━━━━━━━━━━━━━━━━━
*{d['decision']}*
النقاط: {d['score']}/10

📋 *الإشارات:*
"""
    for sig in d['signals']:
        report += f"  • {sig}\n"

    report += f"""
━━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
⚠️ _هذا تحليل تقني فقط، ليس توصية استثمارية_
"""
    return report

def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text.startswith("/start"):
        send_message(chat_id, """
🤖 *بوت تحليل الأسهم الاحترافي*
━━━━━━━━━━━━━━━━━━━━━━

*الأوامر:*
📌 `/sa 2222` — تحليل سهم سعودي
📌 `/us AAPL` — تحليل سهم أمريكي
📌 `/help` — المساعدة

*ما يقدمه البوت:*
✅ RSI | MACD | ستوكاستك
✅ بولينجر باند | ATR
✅ دعم ومقاومة متعددة
✅ مناطق الدخول والخروج
✅ حد الخسارة (Stop Loss)
✅ أهداف الربح (3 أهداف)
✅ نسبة المخاطرة/العائد
✅ حجم التداول
✅ قرار شامل بالنقاط
        """)

    elif text.startswith("/sa"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "⚠️ مثال: `/sa 2222`")
            return
        symbol = parts[1]
        send_message(chat_id, f"⏳ جاري التحليل الكامل لـ {symbol}...")
        result = full_analysis(symbol, is_saudi=True)
        if not result:
            send_message(chat_id, f"❌ ما قدرت أحصل على بيانات للرمز `{symbol}`\nتأكد من الرمز (مثال: 2222 لأرامكو)")
            return
        send_message(chat_id, format_report(result))

    elif text.startswith("/us"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "⚠️ مثال: `/us AAPL`")
            return
        symbol = parts[1].upper()
        send_message(chat_id, f"⏳ جاري التحليل الكامل لـ {symbol}...")
        result = full_analysis(symbol, is_saudi=False)
        if not result:
            send_message(chat_id, f"❌ ما قدرت أحصل على بيانات للرمز `{symbol}`")
            return
        send_message(chat_id, format_report(result))

    elif text.startswith("/help"):
        send_message(chat_id, """
📖 *دليل البوت الاحترافي*
━━━━━━━━━━━━━━━━━━━━━━

*أوامر التحليل:*
`/sa [رمز]` — سهم سعودي
`/us [رمز]` — سهم أمريكي

*أمثلة سعودية:*
`/sa 2222` أرامكو
`/sa 1120` الراجحي
`/sa 2010` سابك
`/sa 7010` STC
`/sa 4200` مدى

*أمثلة أمريكية:*
`/us AAPL` آبل
`/us TSLA` تسلا
`/us NVDA` نفيديا
`/us AMZN` أمازون
`/us MSFT` مايكروسوفت

*المؤشرات المحسوبة:*
• RSI، MACD، ستوكاستك
• بولينجر باند، ATR
• دعم ومقاومة (مستويين)
• مناطق الدخول والخروج
• حد الخسارة، 3 أهداف ربح
• نسبة المخاطرة/العائد (1:X)
• حجم التداول مقارنة بالمتوسط
        """)
    else:
        send_message(chat_id, "❓ اكتب /help للمساعدة")

def main():
    print("🤖 بوت التحليل الاحترافي شغّال...")
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
