"""correction factor / enthalpy / Ton / BTU / EER"""
import math
import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

# แกน X = wet bulb ของลมกลับ (°C), แกน Y = อุณหภูมิอากาศเข้า CDU (°C)
X = [16.0, 18.0, 19.0, 19.4, 20.0, 22.0, 24.0]
Y = [25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0]

Z_TON = [
    [0.96, 0.92, 0.89, 0.85, 0.81, 0.76, 0.76],
    [1.03, 0.99, 0.95, 0.91, 0.86, 0.81, 0.81],
    [1.07, 1.02, 0.98, 0.94, 0.89, 0.84, 0.84],
    [1.08, 1.04, 1.00, 0.95, 0.91, 0.86, 0.86],
    [1.10, 1.06, 1.02, 0.97, 0.92, 0.87, 0.87],
    [1.18, 1.14, 1.09, 1.04, 0.98, 0.93, 0.93],
    [1.18, 1.14, 1.09, 1.04, 0.98, 0.93, 0.93],
]

Z_KW = [
    [0.83, 0.89, 0.95, 1.01, 1.08, 1.15, 1.15],
    [0.85, 0.91, 0.98, 1.04, 1.11, 1.18, 1.18],
    [0.86, 0.93, 0.99, 1.06, 1.13, 1.20, 1.20],
    [0.87, 0.93, 1.00, 1.07, 1.14, 1.21, 1.21],
    [0.88, 0.94, 1.01, 1.08, 1.15, 1.22, 1.22],
    [0.90, 0.97, 1.04, 1.11, 1.18, 1.26, 1.26],
    [0.90, 0.97, 1.04, 1.11, 1.18, 1.26, 1.26],
]

_F_TON = RegularGridInterpolator((X, Y), np.asarray(Z_TON, dtype=float))
_F_KW = RegularGridInterpolator((X, Y), np.asarray(Z_KW, dtype=float))


def _interp(fn, xs, ys):
    """interpolate แบบทน NaN (แถวที่ NaN คืน NaN ไม่ทำให้ทั้งไฟล์พัง)"""
    xs = pd.to_numeric(pd.Series(xs).reset_index(drop=True), errors="coerce").to_numpy(float)
    ys = pd.to_numeric(pd.Series(ys).reset_index(drop=True), errors="coerce").to_numpy(float)
    bad = np.isnan(xs) | np.isnan(ys)
    xs_f = np.clip(np.where(bad, X[0], xs), X[0], X[-1])
    ys_f = np.clip(np.where(bad, Y[0], ys), Y[0], Y[-1])
    out = fn(np.column_stack([xs_f, ys_f])).astype(float)
    out[bad] = np.nan
    return np.round(out, 3)


def enthalpy(t_c, rh_pct):
    """เอนทัลปีอากาศชื้น (kJ/kg dry air)"""
    if pd.isna(t_c) or pd.isna(rh_pct):
        return np.nan
    t_c = float(t_c)
    rh = float(rh_pct) / 100.0
    if not (-40 < t_c < 80) or not (0 <= rh <= 1.2):
        return np.nan
    T = t_c + 273.16
    try:
        pv = 10 ** (28.59051 - 8.2 * math.log10(T) + 0.0024804 * T - (3142.31 / T))
    except (ValueError, OverflowError):
        return np.nan
    pa = pv * rh
    denom = 1.01325 - pa
    if denom <= 1e-6:                      # กันหารด้วยศูนย์เมื่ออากาศอิ่มตัวมาก
        return np.nan
    w = 0.622 * pa / denom
    return round(1.006 * t_c + w * (1.84 * t_c + 2501.0), 2)


def compute(df, cfg):
    """คำนวณฝั่งความเย็น (ยังไม่รวมไฟฟ้า)"""
    d = df.copy().reset_index(drop=True)
    wb = pd.to_numeric(d[cfg.wetbulb_temp], errors="coerce")
    cdu = pd.to_numeric(d[cfg.cdu_temp], errors="coerce")

    # บันทึกว่าแถวไหนหลุดกรอบตาราง (correction factor อิ่มตัว = ไม่น่าเชื่อถือ)
    d["wb_clipped"] = ((wb < X[0]) | (wb > X[-1])).fillna(False)
    d["cdu_clipped"] = ((cdu < Y[0]) | (cdu > Y[-1])).fillna(False)

    d["ton_corrected_factor"] = _interp(_F_TON, wb, cdu)
    d["kw_corrected_factor"] = _interp(_F_KW, wb, cdu)

    d["Enthalpy Supply"] = [enthalpy(t, r) for t, r in
                            zip(d[cfg.supply_temp], d[cfg.supply_rh])]
    d["Enthalpy Return"] = [enthalpy(t, r) for t, r in
                            zip(d[cfg.return_temp], d[cfg.return_rh])]
    d["Enthapy"] = d["Enthalpy Return"] - d["Enthalpy Supply"]
    d["Delta T"] = (pd.to_numeric(d[cfg.return_temp], errors="coerce")
                    - pd.to_numeric(d[cfg.supply_temp], errors="coerce"))

    # ความเร็วลม: หาค่าเฉลี่ยหลังกรอง ±SD
    v = pd.to_numeric(d[cfg.wind_speed], errors="coerce")
    sd = v.std()
    mean = v.mean()
    if pd.isna(sd) or sd == 0:
        lo, hi = -np.inf, np.inf
        v_avg = mean
    else:
        lo, hi = mean - cfg.wind_sd * sd, mean + cfg.wind_sd * sd
        inside = v[(v >= lo) & (v <= hi)]
        v_avg = inside.mean() if len(inside) else mean
    if pd.isna(v_avg) or v_avg <= 0:
        raise ValueError("คำนวณความเร็วลมเฉลี่ยไม่ได้ — ตรวจคอลัมน์ [m/s]")

    d["wind_out_of_sd"] = ((v < lo) | (v > hi)).fillna(False)
    d["Average Wind Speed (1.5 SD)"] = float(v_avg)

    d["cmm"] = cfg.air_size * float(v_avg) * 60.0
    d["cmm_inst"] = cfg.air_size * v * 60.0
    d["Ton"] = 0.005707 * d["Enthapy"] * d["cmm"]

    f_ton = d["ton_corrected_factor"].replace(0, np.nan)
    d["Ton_Corrected"] = d["Ton"] / f_ton
    d["btu"] = d["Ton_Corrected"] * 12000.0
    return d


def add_power(d, cfg):
    """รวมฝั่งไฟฟ้าและคำนวณ EER"""
    d = d.copy()
    d["kw_raw"] = pd.to_numeric(d.get("kw_raw"), errors="coerce")

    f_kw = d["kw_corrected_factor"].replace(0, np.nan)
    d["Power_Corrected (kW)"] = d["kw_raw"] / f_kw

    p = d["Power_Corrected (kW)"].where(
        d["Power_Corrected (kW)"] > cfg.min_kw, np.nan)
    d["EER"] = 12.0 * d["Ton_Corrected"] / p
    d = d.replace([np.inf, -np.inf], np.nan)
    return d