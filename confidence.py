def confidence_score(df):
    score = 0
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last.close < last.vwap:
        score += 25
    if last.ema20 < prev.ema20:
        score += 25
    if abs(prev.high - prev.low) < abs(df.iloc[-3].high - df.iloc[-3].low):
        score += 20
    if prev.high - prev.close > prev.close - prev.low:
        score += 20
    if last.volume > df.volume.mean():
        score += 10

    return score
