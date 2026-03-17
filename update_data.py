"""
update_data.py — Allocate MAF/BAF Dashboard Data Refresher
=============================================================
Run this script every month after updating your Excel file.
It reads 'Allocate MAF BAF Data.xlsx' and regenerates 'data.json'.

Usage:
  python update_data.py

Requirements:
  pip install pandas openpyxl numpy python-dateutil
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import date
from dateutil.relativedelta import relativedelta

# ── Config ───────────────────────────────────────────────────────
EXCEL_FILE   = "Allocate MAF BAF Data.xlsx"
OUTPUT_JSON  = "data.json"
TRADING_DAYS = 252

# Common comparison base-dates for Since-Inception returns
SI_EQUITY_DATE      = "2025-03-21"   # Allocate Equity inception
SI_AGGRESSIVE_DATE  = "2025-03-27"   # Allocate Aggressive inception
SI_MODERATE_DATE    = "2025-04-17"   # Allocate Moderate inception
# ────────────────────────────────────────────────────────────────


def compute_metrics(df, fund):
    """
    Compute full metric set for 'fund' in DataFrame 'df'.

    Period returns:
      mtd    = current month-to-date (from last month-end close)
      1m     = last COMPLETE calendar month return (e.g. Feb if today is March)
      3m/6m  = exact 3 / 6 calendar months back (relativedelta)
      ytd    = from Dec 31 of prior year
      si_vs_* = CAGR from each Allocate scheme's inception date

    Sharpe / Sortino — no risk-free rate:
      sharpe_simple  = mean(trading_ret) / std(trading_ret)       [daily]
      sharpe         = sharpe_simple * sqrt(252)                   [annualised]
      sortino_simple = mean(trading_ret) / std(neg_trading_ret)    [daily]
      sortino        = sortino_simple * sqrt(252)                  [annualised]

    Beta / Alpha: NOT computed (no benchmark index data available).
    """
    mask = df[fund].notna()
    fd   = df[mask][['Date', fund]].copy().reset_index(drop=True)
    if len(fd) < 10:
        return None

    last_date  = df['Date'].iloc[-1]
    start_nav  = float(fd[fund].iloc[0])
    end_nav    = float(df[mask][fund].iloc[-1])
    start_date = fd['Date'].iloc[0]
    years      = (last_date - start_date).days / 365.25
    cagr       = float((end_nav / start_nav) ** (1.0 / years) - 1) if years > 0 else 0.0

    # ── Volatility (trading-day only, excludes flat weekend/holiday fills) ────
    all_ret     = fd[fund].pct_change().dropna().values
    trading_ret = all_ret[all_ret != 0]
    if len(trading_ret) < 10:
        trading_ret = all_ret

    std_all = float(np.std(trading_ret, ddof=1))
    ann_vol = std_all * np.sqrt(TRADING_DAYS)
    mean_r  = float(np.mean(trading_ret))

    # ── Sharpe (no Rf) ───────────────────────────────────────────────────────
    sharpe_simple = float(mean_r / std_all) if std_all > 0 else None
    sharpe        = float(sharpe_simple * np.sqrt(TRADING_DAYS)) if sharpe_simple is not None else None

    # ── Sortino (no Rf) ──────────────────────────────────────────────────────
    neg_ret = trading_ret[trading_ret < 0]
    if len(neg_ret) > 1:
        std_neg        = float(np.std(neg_ret, ddof=1))
        sortino_simple = float(mean_r / std_neg) if std_neg > 0 else None
        sortino        = float(sortino_simple * np.sqrt(TRADING_DAYS)) if sortino_simple is not None else None
    else:
        sortino_simple = sortino = None

    # ── Period returns ────────────────────────────────────────────────────────
    def _nav_at_or_before(target_ts):
        sub = fd[fd['Date'] <= target_ts]
        return float(sub[fund].iloc[-1]) if len(sub) > 0 else None

    # MTD: from last month-end to today
    first_curr_month = pd.Timestamp(last_date.year, last_date.month, 1)
    prev_month_end   = first_curr_month - pd.Timedelta(days=1)
    n_mtd = _nav_at_or_before(prev_month_end)
    mtd   = float(end_nav / n_mtd - 1) if n_mtd else None

    # 1M: last COMPLETE calendar month (e.g. Feb if today is March)
    first_prev_month  = pd.Timestamp(prev_month_end.year, prev_month_end.month, 1)
    two_prev_month_end = first_prev_month - pd.Timedelta(days=1)
    n_1m_end   = _nav_at_or_before(prev_month_end)
    n_1m_start = _nav_at_or_before(two_prev_month_end)
    r1m = float(n_1m_end / n_1m_start - 1) if (n_1m_end and n_1m_start) else None

    # 3M / 6M: exact calendar months back from last_date
    def point_ret(months_back):
        target = last_date - relativedelta(months=months_back)
        sub    = fd[fd['Date'] <= target]
        return float(end_nav / float(sub[fund].iloc[-1]) - 1) if len(sub) > 0 else None

    # YTD: from Dec 31 of prior year
    def ytd_ret():
        dec31 = pd.Timestamp(last_date.year - 1, 12, 31)
        if start_date > dec31:
            return None
        n = _nav_at_or_before(dec31)
        return float(end_nav / n - 1) if n else None

    # SI vs each Allocate base date
    def si_vs(base_date_str):
        base_dt = pd.Timestamp(base_date_str)
        sub     = fd[fd['Date'] <= base_dt]
        if len(sub) == 0:
            s_nav, s_date = start_nav, start_date
        else:
            s_nav  = float(sub[fund].iloc[-1])
            s_date = sub['Date'].iloc[-1]
        yrs = (last_date - s_date).days / 365.25
        return float((end_nav / s_nav) ** (1.0 / yrs) - 1) if yrs > 0 else None

    r3m  = point_ret(3)
    r6m  = point_ret(6)
    ytd  = ytd_ret()
    r1m_label = prev_month_end.strftime("%b %Y")   # e.g. "Feb 2026"

    m = {
        'cagr':            round(cagr, 6),
        'ann_vol':         round(float(ann_vol), 6),
        'sharpe_simple':   round(sharpe_simple, 4) if sharpe_simple is not None else None,
        'sharpe':          round(sharpe, 4)         if sharpe is not None else None,
        'sortino_simple':  round(sortino_simple, 4) if sortino_simple is not None else None,
        'sortino':         round(sortino, 4)         if sortino is not None else None,
        # Period returns
        'mtd':             round(mtd, 6)  if mtd  is not None else None,
        '1m':              round(r1m, 6)  if r1m  is not None else None,
        '1m_label':        r1m_label,
        '3m':              round(r3m, 6)  if r3m  is not None else None,
        '6m':              round(r6m, 6)  if r6m  is not None else None,
        'ytd':             round(ytd, 6)  if ytd  is not None else None,
        'si_vs_equity':    round(si_vs(SI_EQUITY_DATE),     6) if si_vs(SI_EQUITY_DATE)     is not None else None,
        'si_vs_aggressive':round(si_vs(SI_AGGRESSIVE_DATE), 6) if si_vs(SI_AGGRESSIVE_DATE) is not None else None,
        'si_vs_moderate':  round(si_vs(SI_MODERATE_DATE),   6) if si_vs(SI_MODERATE_DATE)   is not None else None,
        'inception_date':  str(start_date.date()),
    }
    return m


def build_nav_series(df, funds, sample_every=3):
    out     = {'dates': [], 'series': {f: [] for f in funds}}
    sampled = df.iloc[::sample_every].copy()
    if df.index[-1] not in sampled.index:
        sampled = pd.concat([sampled, df.iloc[[-1]]])
    sampled = sampled.sort_values('Date').reset_index(drop=True)
    out['dates'] = [str(d.date()) for d in sampled['Date']]
    for f in funds:
        out['series'][f] = [
            round(float(v), 4) if pd.notna(v) else None
            for v in sampled[f]
        ]
    return out


def monthly_returns(df, funds):
    df2       = df.copy()
    df2['YM'] = df2['Date'].dt.to_period('M')
    month_end = df2.groupby('YM').last().reset_index()
    result    = {}
    for fund in funds:
        valid = month_end[month_end[fund].notna()].reset_index(drop=True)
        rets  = {}
        for i in range(1, len(valid)):
            ym       = str(valid['YM'].iloc[i])
            nav_cur  = float(valid[fund].iloc[i])
            nav_prev = float(valid[fund].iloc[i - 1])
            rets[ym] = round(float(nav_cur / nav_prev - 1), 6)
        result[fund] = rets
    return result


def cat_avg_monthly(mom_dict):
    months = sorted({m for f in mom_dict.values() for m in f.keys()})
    return {m: round(float(np.mean([v[m] for v in mom_dict.values() if m in v])), 6)
            for m in months}


def cat_avg_metrics(m_dict):
    keys = [
        'mtd', '1m', '3m', '6m', 'ytd', 'cagr', 'ann_vol',
        'sharpe_simple', 'sharpe', 'sortino_simple', 'sortino',
        'si_vs_equity', 'si_vs_aggressive', 'si_vs_moderate',
    ]
    out = {}
    for k in keys:
        vals = [m[k] for m in m_dict.values() if m and m.get(k) is not None]
        out[k] = round(float(np.mean(vals)), 6) if vals else None
    # carry over label from first valid fund
    first = next((m for m in m_dict.values() if m), None)
    out['1m_label']       = first['1m_label'] if first else ''
    out['inception_date'] = 'Avg'
    return out


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(script_dir, EXCEL_FILE)
    json_path  = os.path.join(script_dir, OUTPUT_JSON)

    print(f"Reading: {excel_path}")
    baf_df = pd.read_excel(excel_path, sheet_name='BAF', parse_dates=['Date'])
    maf_df = pd.read_excel(excel_path, sheet_name='MAF', parse_dates=['Date'])
    print(f"  BAF: {len(baf_df)} rows  (last: {baf_df['Date'].iloc[-1].date()})")
    print(f"  MAF: {len(maf_df)} rows  (last: {maf_df['Date'].iloc[-1].date()})")

    BAF_FUNDS = ['Tata', 'Nippon', 'Edelweiss', 'Kotak', 'SBI', 'HDFC', 'ICICI']
    MAF_FUNDS = ['Whiteoak', 'UTI', 'HDFC', 'Nippon', 'SBI', 'Kotak', 'DSP', 'ICICI']
    ALLOCATE  = ['Moderate', 'Aggressive', 'Equity']

    print("Computing metrics…", end=' ', flush=True)
    metrics = {
        'BAF':          {f: compute_metrics(baf_df, f) for f in BAF_FUNDS},
        'MAF':          {f: compute_metrics(maf_df, f) for f in MAF_FUNDS},
        'Allocate_BAF': {f: compute_metrics(baf_df, f) for f in ALLOCATE},
        'Allocate_MAF': {f: compute_metrics(maf_df, f) for f in ALLOCATE},
    }
    metrics['BAF_avg'] = cat_avg_metrics(metrics['BAF'])
    metrics['MAF_avg'] = cat_avg_metrics(metrics['MAF'])
    print("done.")

    # Grab the 1M label from the first fund (same for all)
    first_m = next(m for m in metrics['BAF'].values() if m)
    one_m_label = first_m.get('1m_label', '1M')

    print("Computing monthly returns…", end=' ', flush=True)
    mom = {
        'BAF':          monthly_returns(baf_df, BAF_FUNDS),
        'MAF':          monthly_returns(maf_df, MAF_FUNDS),
        'Allocate_BAF': monthly_returns(baf_df, ALLOCATE),
        'Allocate_MAF': monthly_returns(maf_df, ALLOCATE),
    }
    cat_avg_mom = {
        'BAF': cat_avg_monthly(mom['BAF']),
        'MAF': cat_avg_monthly(mom['MAF']),
    }
    print("done.")

    print("Building NAV series…", end=' ', flush=True)
    navs = {
        'BAF': build_nav_series(baf_df, BAF_FUNDS + ALLOCATE),
        'MAF': build_nav_series(maf_df, MAF_FUNDS + ALLOCATE),
    }
    print("done.")

    data = {
        'last_updated':  str(date.today()),
        'one_m_label':   one_m_label,          # e.g. "Feb 2026"
        'si_dates': {
            'equity':     SI_EQUITY_DATE,
            'aggressive': SI_AGGRESSIVE_DATE,
            'moderate':   SI_MODERATE_DATE,
        },
        'metrics':         metrics,
        'monthly_returns': mom,
        'cat_avg_monthly': cat_avg_mom,
        'navs':            navs,
        'fund_labels': {
            'BAF': {f: f + ' BAF' for f in BAF_FUNDS},
            'MAF': {
                'Whiteoak': 'WhiteOak MAF', 'UTI': 'UTI MAF', 'HDFC': 'HDFC MAF',
                'Nippon': 'Nippon MAF', 'SBI': 'SBI MAF', 'Kotak': 'Kotak MAF',
                'DSP': 'DSP MAF', 'ICICI': 'ICICI MAF',
            },
            'Allocate': {
                'Moderate':   'Allocate Moderate',
                'Aggressive': 'Allocate Aggressive',
                'Equity':     'Allocate Equity',
            },
        },
    }

    with open(json_path, 'w') as f:
        json.dump(data, f)

    size_kb = os.path.getsize(json_path) / 1024
    print(f"\n✅  data.json updated  ({size_kb:.1f} KB)")
    print(f"   1M label: {one_m_label}")
    print(f"   Push index.html + data.json to GitHub Pages to deploy.\n")


if __name__ == '__main__':
    main()
