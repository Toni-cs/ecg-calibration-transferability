# -*- coding: utf-8 -*-
"""Deployment-bar comparator for the sample-level TS run.

Reads samplelevel_ts_60cells.csv and computes the strict post-TS
deployment-safety check per cell (cal_smoothECE <= 0.05 AND delta < 0),
plus the total- of the deployment-metr strict delta convention
(delta <= -0.01). Same bar the paper uses for its deployment table.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BAR = 0.05          # paper's registered SmoothECE bar for post-cal factor
SAFE = -0.001       # paper's strict delta-ece requirement (deployment table convention)


def main() -> None:
    df = pd.read_csv(ROOT / "results" / "samplelevel_ts_60cells.csv")
    for col, label in (("delta_perbranch", "ATS per-branch"), ("delta_shared", "ATS legacy-shared")):
        strict = df[(df["cal_smoothECE"] <= BAR) & (df[col] < 0)]
        soft = df[df[col] < 0]
        ultra = df[(df["cal_smoothECE"] <= BAR) & (df[col] <= -0.01)]
        print(f"{label}: delta<0 {len(soft)}/60 "
              f"delta<0 AND cal<=0.05: {len(strict)}/60 "
              f"delta<=-0.01 AND cal<=0.05: {len(ultra)}/60")

    df["ts_cal_smoothECE"] = np.nan
    cols = "pair,arch,seed"
    print("wrote nothing back; delivered-comparator coverage is in the delivered file")


if __name__ == "__main__":
    main()
