"""
update_data.py — Allocate MAF/BAF Dashboard Data Refresher
=============================================================
Run this script every month after updating your Excel file.
It reads 'Allocate MAF BAF Data.xlsx' and regenerates 'data.json'.

Usage:
  python update_data.py

Requirements:
  pip install pandas openpyxl numpy
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import date

# ── Config: Edit these paths if you move files ──────────────────
EXCEL_FILE = "Allocate MAF BAF Data.xlsx"   # Path relative to this script
OUTPUT_JSON = "data.json"                   # Output (same folder as index.html)
RF = 0.065                                  # Risk-free rate (6.5% India proxy)
TRADING_DAYS = 252
# ────────────────────────────────────────────────────────────────

def compute_metrics(df, fund, benchmark_col='Equity'):
    mask = df[fund].notna()
    fund_df = df[mask][['Date', fund]].copy().reset_index(drop=True)
    if len(fund_df) < 10:
        return None

    last_date = df['Date'].iloc[-1]
    start_nav  = fund_df[fund].iloc[0]
    end_nav    = df[mask][fund].iloc[-1]
    start_date = fund_df['Date'].iloc[0]
    years      = (last_date - start_date).days / 365.25
    cagr       = float((end_nav / start_nav) ** (1.0 / years) - 1) if years > 0 else 0.0

    daily_ret = fund_df[fund].pct_change().dropna().values
    ann_vol   = float(np.std(daily_ret, ddof=1) * np.sqrt(TRADING_DAYS))
    sharpe    = float((cagr - RF) / ann_vol) if ann_vol > 0 else None

    # Sortino: downside deviation only
    neg_ret = daily_ret[daily_ret < 0]
    if len(neg_ret) > 1:
        dd      = float(np.std(neg_ret, ddof=1) * np.sqrt(TRADING_DAYS))
        sortino = float((cagr - RF) / dd) if dd > 0 else None
    else:
        sortino = None

    # Beta & Alpha vs benchmark
    beta, alpha = None, None
    if benchmark_col in df.columns:
        both = df[fund].notna() & df[benchmark_col].notna()
        al   = df[both][[fund, benchmark_col]].copy().reset_index(drop=True)
        if len(al) >= 30:
            fr = al[fund].pct_change().dropna().values
            br = al[benchmark_col].pct_change().dropna().values
            n  = min(len(fr), len(br))
            fr, br = fr[:n], br[:n]
            bv = float(np.var(br, ddof=1))
            if bv > 0 and n >= 30:
                beta = float(np.cov(fr, br, ddof=1)[0, 1] / bv)
                b_s  = df[df[benchmark_col].notna()][['Date', benchmark_col]].reset_index(drop=True)
                b_y  = (last_date - b_s['Date'].iloc[0]).days / 365.25
                bench_cagr = float((b_s[benchmark_col].iloc[-1] / b_s[benchmark_col].iloc[0]) ** (1/b_y) - 1) if b_y > 0 else 0.0
                alpha = float(cagr - (RF + beta * (bench_cagr - RF)))

    def point_ret(days_back):
        target = last_date - pd.Timedelta(days=days_back)
        sub = fund_df[fund_df['Date'] <= target]
        if len(sub) == 0: return None
        return float(float(end_nav) / float(sub[fund].iloc[-1]) - 1)

    return {
        'cagr':           round(cagr, 6),
        'ann_vol':        round(ann_vol, 6),
        'sharpe':         round(sharpe, 4)  if sharpe  is not None else None,
        'sortino':        round(sortino, 4) if sortino is not None else None,
        'beta':           round(beta, 4)    if beta    is not None else None,
        'alpha':          round(alpha, 6)   if alpha   is not None else None,
        '1m':             round(point_ret(30),  6) if point_ret(30)  else None,
        '3m':             round(point_ret(91),  6) if point_ret(91)  else None,
        '6m':             round(point_ret(182), 6) if point_ret(182) else None,
        'inception_date': str(start_date.date()),
    }


def build_nav_series(df, funds, sample_every=3):
    """Sample every Nth row for a lean JSON; always include the last row."""
    out = {'dates': [], 'series': {f: [] for f in funds}}
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
    """Last-trading-day-of-month returns for each fund."""
    df2 = df.copy()
    df2['YM'] = df2['Date'].dt.to_period('M')
    month_end = df2.groupby('YM').last().reset_index()
    result = {}
    for fund in funds:
        valid = month_end[month_end[fund].notna()].reset_index(drop=True)
        rets  = {}
        for i in range(1, len(valid)):
            ym  = str(valid['YM'].iloc[i])
            nav_cur  = float(valid[fund].iloc[i])
            nav_prev = float(valid[fund].iloc[i - 1])
            rets[ym]  = round(float(nav_cur / nav_prev - 1), 6)
        result[fund] = rets
    return result


def cat_avg_monthly(mom_dict):
    """Average monthly return across all funds in a category."""
    months = sorted({m for f in mom_dict.values() for m in f.keys()})
    return {m: round(float(np.mean([v[m] for v in mom_dict.values() if m in v])), 6)
            for m in months}


def cat_avg_metrics(m_dict):
    """Average of each metric across a category of funds."""
    keys = ['1m', '3m', '6m', 'cagr', 'ann_vol', 'sharpe', 'sortino', 'beta', 'alpha']
    out  = {}
    for k in keys:
        vals = [m[k] for m in m_dict.values() if m and m.get(k) is not None]
        out[k] = round(float(np.mean(vals)), 6) if vals else None
    out['inception_date'] = 'Avg'
    return out


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(script_dir, EXCEL_FILE)
    json_path  = os.path.join(script_dir, OUTPUT_JSON)

    print(f"Reading: {excel_path}")
    baf_df = pd.read_excel(excel_path, sheet_name='BAF', parse_dates=['Date'])
    maf_df = pd.read_excel(excel_path, sheet_name='MAF', parse_dates=['Date'])

    baf_last = baf_df['Date'].iloc[-1].date()
    maf_last = maf_df['Date'].iloc[-1].date()
    print(f"  BAF: {len(baf_df)} rows  (last: {baf_last})")
    print(f"  MAF: {len(maf_df)} rows  (last: {maf_last})")

    BAF_FUNDS = ['Tata', 'Nippon', 'Edelweiss', 'Kotak', 'SBI', 'HDFC', 'ICICI']
    MAF_FUNDS = ['Whiteoak', 'UTI', 'HDFC', 'Nippon', 'SBI', 'Kotak', 'DSP', 'ICICI']
    ALLOCATE  = ['Moderate', 'Aggressive', 'Equity']

    print("Computing metrics…", end=' ')
    metrics = {
        'BAF':          {f: compute_metrics(baf_df, f) for f in BAF_FUNDS},
        'MAF':          {f: compute_metrics(maf_df, f) for f in MAF_FUNDS},
        'Allocate_BAF': {f: compute_metrics(baf_df, f) for f in ALLOCATE},
        'Allocate_MAF': {f: compute_metrics(maf_df, f) for f in ALLOCATE},
    }
    metrics['BAF_avg'] = cat_avg_metrics(metrics['BAF'])
    metrics['MAF_avg'] = cat_avg_metrics(metrics['MAF'])
    print("done.")

    print("Computing monthly returns…", end=' ')
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

    print("Building NAV series…", end=' ')
    navs = {
        'BAF': build_nav_series(baf_df, BAF_FUNDS + ALLOCATE),
        'MAF': build_nav_series(maf_df, MAF_FUNDS + ALLOCATE),
    }
    print("done.")

    data = {
        'last_updated':    str(date.today()),
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
    print(f"   Push index.html + data.json to GitHub Pages to deploy.\n")


if __name__ == '__main__':
    main()
