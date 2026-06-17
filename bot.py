import os
import requests
import json
from datetime import datetime
import time
import threading

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8323085330:AAGMhk8EqNnGbavDNZNir4ARCAPOrGY3u8c")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# قاعدة بيانات التنبيهات في الذاكرة
# alerts = { chat_id: [ {symbol, is_saudi, target_price, direction, label}, ... ] }
alerts = {}
alerts_lock = threading.Lock()

def send_message(chat_id, text, parse_mode="Markdown"):
    url = f"{TELEGRAM_API}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(url, json=data, timeout=10)
    except:
        pass

def get_current_price(symbol, is_saudi=False):
    ticker = f"{symbol}.SR" if is_saudi else symbol.upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        return meta.get("regularMarketPrice", None)
    except:
        return None

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
    if avg_loss == 0: return 100
    return round(100 - (100 / (1 + avg_gain/avg_loss)), 2)

def calc_macd(closes):
    def ema(data, period):
        if len(data) < period: return None
        k = 2 / (period + 1)
        val = sum(data[:period]) / period
        for p in data[period:]: val = p * k + val * (1 - k)
        return round(val, 4)
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    if not e12 or not e26: return None, None, None
    macd_line = round(e12 - e26, 4)
    macd_vals = []
    for i in range(26, len(closes)):
        a = ema(closes[:i], 12)
        b = ema(closes[:i], 26)
        if a and b: macd_vals.append(a - b)
    signal = ema(macd_vals, 9) if len(macd_vals) >= 9 else None
    histogram = round(macd_line - signal, 4) if signal else None
    return macd_line, round(signal, 4) if signal else None, histogram

def calc_bollinger(closes, period=20):
    if len(closes) < period: return None, None, None
    recent = closes[-period:]
    ma = sum(recent) / period
    std = (sum((x-ma)**2 for x in recent) / period) ** 0.5
    return round(ma+2*std, 2), round(ma, 2), round(ma-2*std, 2)

def calc_stochastic(closes, highs, lows, k_period=14):
    if len(closes) < k_period: return None, None
    highest = max(highs[-k_period:])
    lowest = min(lows[-k_period:])
    if highest == lowest: return 50, 50
    k = round(((closes[-1] - lowest) / (highest - lowest)) * 100, 2)
    return k, k

def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1: return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 4)

def calc_support_resistance(highs, lows, periods=30):
    rh = sorted(set([round(h,1) for h in highs[-periods:]]), reverse=True)
    rl = sorted(set([round(l,1) for l in lows[-periods:]]))
    return (rl[0] if rl else 0), (rl[1] if len(rl)>1 else 0), (rh[0] if rh else 0), (rh[1] if len(rh)>1 else 0)

def calc_volume(volumes):
    if len(volumes) < 20: return 0, 0, 1
    avg = sum(volumes[-20:]) / 20
    curr = volumes[-1]
    return round(avg), round(curr), round(curr/avg, 2) if avg > 0 else 1

def determine_trend(closes, ma20, ma50):
    if not ma20 or not ma50: return "محايد"
    c = closes[-1]
    if c > ma20 and ma20 > ma50: return "صاعد"
    elif c < ma20 and ma20 < ma50: return "هابط"
    return "محايد"

def calc_trade_zones(current, atr, s1, r1, trend):
    if atr is None or atr == 0: atr = current * 0.02
    if trend == "صاعد":
        entry1 = round(current, 2)
        entry2 = round(current * 0.99, 2)
        stop_loss = round(s1 - atr * 0.3, 2)
        target1 = round(current + atr * 1.5, 2)
        target2 = round(current + atr * 3.0, 2)
        target3 = round(r1, 2)
        sl_pct = round(abs(entry1 - stop_loss) / entry1 * 100, 2)
        rr = round((target1 - entry1) / (entry1 - stop_loss), 2) if entry1 != stop_loss else 0
        trade_type = "🟢 شراء (Long)"
    elif trend == "هابط":
        entry1 = round(current, 2)
        entry2 = round(current * 1.01, 2)
        stop_loss = round(r1 + atr * 0.3, 2)
        target1 = round(current - atr * 1.5, 2)
        target2 = round(current - atr * 3.0, 2)
        target3 = round(s1, 2)
        sl_pct = round(abs(stop_loss - entry1) / entry1 * 100, 2)
        rr = round((entry1 - target1) / (stop_loss - entry1), 2) if entry1 != stop_loss else 0
        trade_type = "🔴 بيع (Short)"
    else:
        return None
    return {
        "trade_type": trade_type, "entry1": entry1, "entry2": entry2,
        "stop_loss": stop_loss, "target1": target1, "target2": target2,
        "target3": target3, "sl_pct": sl_pct, "rr": rr
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
    if not data: return None
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
        "name": meta.get("longName", symbol), "symbol": symbol.upper(),
        "currency": meta.get("currency", "SAR" if is_saudi else "USD"),
        "current": current, "change": change, "change_pct": change_pct,
        "rsi": rsi, "macd": macd_line, "macd_signal": signal_line, "histogram": histogram,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
        "stoch_k": stoch_k, "atr": atr,
        "s1": s1, "s2": s2, "r1": r1, "r2": r2,
        "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "avg_vol": avg_vol, "curr_vol": curr_vol, "vol_ratio": vol_ratio,
        "trend": trend, "zones": zones, "decision": decision, "signals": signals, "score": score,
        "is_saudi": is_saudi
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
• MACD: `{d['macd']}` | إشارة: `{d['macd_signal']}` | هيستوجرام: `{d['histogram']}`
• ستوكاستك: `{d['stoch_k']}` | ATR: `{d['atr']}`

━━━━━━━━━━━━━━━━━━━━━━
📈 *المتوسطات المتحركة*
━━━━━━━━━━━━━━━━━━━━━━
• MA20: `{d['ma20']}` {'✅' if d['current'] > (d['ma20'] or 0) else '❌'}
• MA50: `{d['ma50']}` {'✅' if d['current'] > (d['ma50'] or 0) else '❌'}
• MA200: `{d['ma200'] or 'غير متاح'}`
• الاتجاه: *{d['trend']}*

━━━━━━━━━━━━━━━━━━━━━━
🏗️ *الدعم والمقاومة*
━━━━━━━━━━━━━━━━━━━━━━
• مقاومة 2: `{d['r2']}` | مقاومة 1: `{d['r1']}` ⬆️
• السعر: `{d['current']:.2f}` 📍
• دعم 1: `{d['s1']}` | دعم 2: `{d['s2']}` ⬇️

━━━━━━━━━━━━━━━━━━━━━━
🎯 *بولينجر باند*
━━━━━━━━━━━━━━━━━━━━━━
• العلوي: `{d['bb_upper']}` | الوسط: `{d['bb_mid']}` | السفلي: `{d['bb_lower']}`

━━━━━━━━━━━━━━━━━━━━━━
📦 *حجم التداول*
━━━━━━━━━━━━━━━━━━━━━━
• الحالي: `{d['curr_vol']:,}` | المتوسط: `{d['avg_vol']:,}` | النسبة: `x{d['vol_ratio']}` {'⚡' if d['vol_ratio'] and d['vol_ratio']>1.5 else ''}
"""
    if z:
        is_buy = "شراء" in z['trade_type']
        report += f"""
━━━━━━━━━━━━━━━━━━━━━━
💼 *نوع الصفقة: {z['trade_type']}*
━━━━━━━━━━━━━━━━━━━━━━
"""
        if is_buy:
            report += f"""🛑 وقف الخسارة: `{z['stop_loss']}` ({z['sl_pct']}%) ← تحت الدعم
🟢 دخول 2 (أفضل): `{z['entry2']}`
🟢 دخول 1: `{z['entry1']}`
🎯 هدف 1: `{z['target1']}`
🎯 هدف 2: `{z['target2']}`
🏆 هدف 3: `{z['target3']}`
⚖️ مخاطرة/عائد: `1:{z['rr']}`"""
        else:
            report += f"""🏆 هدف 3: `{z['target3']}`
🎯 هدف 2: `{z['target2']}`
🎯 هدف 1: `{z['target1']}`
🔴 دخول 1: `{z['entry1']}`
🔴 دخول 2 (أفضل): `{z['entry2']}`
🛑 وقف الخسارة: `{z['stop_loss']}` ({z['sl_pct']}%) ← فوق المقاومة
⚖️ مخاطرة/عائد: `1:{z['rr']}`"""
    else:
        report += "\n⚪ *لا توجد صفقة واضحة — انتظر إشارة أوضح*"

    report += f"""

━━━━━━━━━━━━━━━━━━━━━━
🤖 *القرار: {d['decision']}* ({d['score']} نقاط)
━━━━━━━━━━━━━━━━━━━━━━
"""
    for sig in d['signals']:
        report += f"• {sig}\n"

    # اقتراح تنبيه تلقائي
    if z:
        cmd = "sa" if d['is_saudi'] else "us"
        report += f"\n💡 تبي تنبيه عند الدخول؟\n`/watch {cmd.upper()} {d['symbol']}`"

    report += f"\n\n⏰ _{datetime.now().strftime('%Y-%m-%d %H:%M')}_"
    report += "\n⚠️ _تحليل تقني فقط، ليس توصية استثمارية_"
    return report

# ═══════════════════════════════════════
# نظام التنبيهات
# ═══════════════════════════════════════

def add_alert(chat_id, symbol, is_saudi, target_price, direction, label):
    with alerts_lock:
        if chat_id not in alerts:
            alerts[chat_id] = []
        # تجنب التكرار
        for a in alerts[chat_id]:
            if a['symbol'] == symbol and abs(a['target_price'] - target_price) < 0.01:
                return False
        alerts[chat_id].append({
            "symbol": symbol,
            "is_saudi": is_saudi,
            "target_price": target_price,
            "direction": direction,  # "above" أو "below"
            "label": label,
            "created": datetime.now().strftime('%H:%M')
        })
        return True

def remove_alert(chat_id, symbol):
    with alerts_lock:
        if chat_id not in alerts:
            return 0
        before = len(alerts[chat_id])
        alerts[chat_id] = [a for a in alerts[chat_id] if a['symbol'] != symbol.upper()]
        return before - len(alerts[chat_id])

def check_alerts():
    """خيط مستقل يتحقق من التنبيهات كل دقيقة"""
    while True:
        time.sleep(60)
        try:
            with alerts_lock:
                all_chats = list(alerts.items())

            for chat_id, user_alerts in all_chats:
                triggered = []
                remaining = []

                for alert in user_alerts:
                    price = get_current_price(alert['symbol'], alert['is_saudi'])
                    if price is None:
                        remaining.append(alert)
                        continue

                    hit = False
                    if alert['direction'] == 'below' and price <= alert['target_price']:
                        hit = True
                    elif alert['direction'] == 'above' and price >= alert['target_price']:
                        hit = True

                    if hit:
                        triggered.append((alert, price))
                    else:
                        remaining.append(alert)

                with alerts_lock:
                    alerts[chat_id] = remaining

                for alert, price in triggered:
                    msg = f"""
🔔 *تنبيه — {alert['label']}!*
━━━━━━━━━━━━━━━━━━━━━━
📊 السهم: *{alert['symbol']}*
🎯 السعر المستهدف: `{alert['target_price']}`
💰 السعر الحالي: `{price:.2f}`
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}

{'🟢 وصل نقطة الدخول — راجع التحليل!' if 'دخول' in alert['label'] else '⚠️ ' + alert['label']}
"""
                    send_message(chat_id, msg)
        except Exception as e:
            print(f"Alert error: {e}")

def handle_watch(chat_id, parts):
    """تنبيه تلقائي عند نقطة الدخول المحسوبة"""
    if len(parts) < 3:
        send_message(chat_id, "⚠️ مثال:\n`/watch SA 2222`\n`/watch US AAPL`")
        return
    market = parts[1].upper()
    symbol = parts[2].upper()
    is_saudi = market == "SA"

    send_message(chat_id, f"⏳ أحسب نقطة الدخول لـ {symbol}...")
    result = full_analysis(symbol, is_saudi)
    if not result or not result['zones']:
        send_message(chat_id, "❌ ما قدرت أحدد نقطة دخول — الاتجاه محايد")
        return

    z = result['zones']
    is_buy = "شراء" in z['trade_type']
    entry = z['entry2']  # الدخول الأفضل
    direction = "below" if is_buy else "above"
    label = f"نقطة دخول {'شراء' if is_buy else 'بيع'}"

    added = add_alert(chat_id, symbol, is_saudi, entry, direction, label)
    if added:
        send_message(chat_id, f"""
✅ *تم إضافة التنبيه!*
━━━━━━━━━━━━━━━━━━━━━━
📊 السهم: *{symbol}*
🎯 السعر المستهدف: `{entry}`
📌 النوع: {label}
🔔 راح أنبّهك لما يوصل السعر لـ `{entry}`

لعرض تنبيهاتك: /alerts
لإلغاء التنبيه: `/cancel {symbol}`
        """)
    else:
        send_message(chat_id, f"⚠️ عندك تنبيه مشابه لـ {symbol} موجود أصلاً")

def handle_alert_cmd(chat_id, parts):
    """تنبيه يدوي عند سعر معين: /alert SA 2222 400"""
    if len(parts) < 4:
        send_message(chat_id, "⚠️ مثال:\n`/alert SA 2222 400`\n`/alert US AAPL 200`")
        return
    market = parts[1].upper()
    symbol = parts[2].upper()
    is_saudi = market == "SA"
    try:
        target = float(parts[3])
    except:
        send_message(chat_id, "❌ السعر غير صحيح")
        return

    price = get_current_price(symbol, is_saudi)
    if price is None:
        send_message(chat_id, f"❌ ما قدرت أحصل على سعر {symbol}")
        return

    direction = "below" if target < price else "above"
    label = f"وصل لـ {target}"
    added = add_alert(chat_id, symbol, is_saudi, target, direction, label)

    if added:
        send_message(chat_id, f"""
✅ *تم إضافة التنبيه!*
━━━━━━━━━━━━━━━━━━━━━━
📊 السهم: *{symbol}*
💰 السعر الحالي: `{price:.2f}`
🎯 السعر المستهدف: `{target}`
📌 التنبيه: {'عند الانخفاض لـ' if direction=='below' else 'عند الارتفاع لـ'} `{target}`

لعرض تنبيهاتك: /alerts
لإلغاء التنبيه: `/cancel {symbol}`
        """)
    else:
        send_message(chat_id, f"⚠️ عندك تنبيه مشابه لـ {symbol} موجود أصلاً")

def handle_alerts_list(chat_id):
    with alerts_lock:
        user_alerts = alerts.get(chat_id, [])
    if not user_alerts:
        send_message(chat_id, "📭 ما عندك تنبيهات نشطة\n\nأضف تنبيه:\n`/watch SA 2222`\n`/alert SA 2222 400`")
        return
    msg = "🔔 *تنبيهاتك النشطة:*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, a in enumerate(user_alerts, 1):
        msg += f"{i}. *{a['symbol']}* ← `{a['target_price']}` ({a['label']}) — أُضيف {a['created']}\n"
    msg += f"\nالإجمالي: {len(user_alerts)} تنبيه\nلإلغاء: `/cancel SYMBOL`"
    send_message(chat_id, msg)

def handle_cancel(chat_id, parts):
    if len(parts) < 2:
        send_message(chat_id, "⚠️ مثال: `/cancel 2222`")
        return
    symbol = parts[1].upper()
    count = remove_alert(chat_id, symbol)
    if count:
        send_message(chat_id, f"✅ تم إلغاء {count} تنبيه لـ *{symbol}*")
    else:
        send_message(chat_id, f"❌ ما وجدت تنبيه لـ *{symbol}*")

def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    parts = text.split()
    cmd = parts[0].lower() if parts else ""

    if cmd == "/start":
        send_message(chat_id, """
🤖 *بوت تحليل الأسهم الاحترافي*
━━━━━━━━━━━━━━━━━━━━━━
*📊 التحليل:*
`/sa 2222` — سهم سعودي
`/us AAPL` — سهم أمريكي

*🔔 التنبيهات:*
`/watch SA 2222` — تنبيه عند نقطة الدخول
`/alert SA 2222 400` — تنبيه عند سعر معين
`/alerts` — عرض تنبيهاتي
`/cancel 2222` — إلغاء تنبيه

`/help` — المساعدة الكاملة
        """)

    elif cmd == "/sa":
        if len(parts) < 2:
            send_message(chat_id, "⚠️ مثال: `/sa 2222`")
            return
        send_message(chat_id, "⏳ جاري التحليل...")
        result = full_analysis(parts[1], is_saudi=True)
        if not result:
            send_message(chat_id, "❌ ما قدرت أحصل على البيانات")
            return
        send_message(chat_id, format_report(result))

    elif cmd == "/us":
        if len(parts) < 2:
            send_message(chat_id, "⚠️ مثال: `/us AAPL`")
            return
        send_message(chat_id, "⏳ جاري التحليل...")
        result = full_analysis(parts[1].upper(), is_saudi=False)
        if not result:
            send_message(chat_id, "❌ ما قدرت أحصل على البيانات")
            return
        send_message(chat_id, format_report(result))

    elif cmd == "/watch":
        handle_watch(chat_id, parts)

    elif cmd == "/alert":
        handle_alert_cmd(chat_id, parts)

    elif cmd == "/alerts":
        handle_alerts_list(chat_id)

    elif cmd == "/cancel":
        handle_cancel(chat_id, parts)

    elif cmd == "/help":
        send_message(chat_id, """
📖 *دليل البوت الكامل*
━━━━━━━━━━━━━━━━━━━━━━
*التحليل:*
`/sa [رمز]` سهم سعودي
`/us [رمز]` سهم أمريكي

*التنبيهات:*
`/watch SA 2222` ← ينبّهك تلقائياً عند نقطة الدخول المحسوبة
`/watch US AAPL` ← نفس الشيء للأسهم الأمريكية
`/alert SA 2222 400` ← تنبيه عند سعر تحدده أنت
`/alerts` ← عرض كل تنبيهاتك
`/cancel 2222` ← إلغاء تنبيه

*أمثلة سعودية:*
2222 أرامكو | 1120 الراجحي | 2010 سابك | 7010 STC

*أمثلة أمريكية:*
AAPL | TSLA | NVDA | AMZN | MSFT
━━━━━━━━━━━━━━━━━━━━━━
⚠️ _التنبيهات تُفحص كل دقيقة_
        """)
    else:
        send_message(chat_id, "❓ اكتب /help للمساعدة")

def main():
    print("🤖 البوت الاحترافي + التنبيهات شغّال...")
    # تشغيل خيط التنبيهات
    alert_thread = threading.Thread(target=check_alerts, daemon=True)
    alert_thread.start()

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
