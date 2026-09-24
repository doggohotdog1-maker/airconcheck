"""ตรวจจับจุดที่ทำให้ EER / BTU เพี้ยน"""
import numpy as np
import pandas as pd

FLAG_PREFIX = "flag::"


def mad_outlier(s, window=15, z=3.5):
    """rolling MAD z-score — ทนต่อคอลัมน์ที่ NaN เยอะ"""
    s = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() < 8:
        return pd.Series(False, index=s.index)
    med = s.rolling(window, center=True, min_periods=5).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=5).median()
    score = 0.6745 * (s - med) / mad.replace(0, np.nan)
    return (score.abs() > z).fillna(False)


def flag(d, cfg):
    d = d.copy()
    enth = pd.to_numeric(d["Enthapy"], errors="coerce")
    kw = pd.to_numeric(d["kw_raw"], errors="coerce")
    btu = pd.to_numeric(d["btu"], errors="coerce")
    eer = pd.to_numeric(d["EER"], errors="coerce")
    s_rh = pd.to_numeric(d[cfg.supply_rh], errors="coerce")
    r_rh = pd.to_numeric(d[cfg.return_rh], errors="coerce")

    F = {
        "ไม่มีข้อมูลไฟฟ้าตรงเวลานี้": kw.isna(),
        "Δh ติดลบ (ไม่ทำความเย็น)": enth <= 0,
        "Δh ต่ำผิดปกติ (< 2 kJ/kg)": (enth > 0) & (enth < 2),
        "Supply ร้อนกว่า Return": d["Delta T"] <= 0,
        "RH อิ่มตัว 100% (sensor เปียก)": (s_rh >= 99.5) | (r_rh >= 99.5),
        "Wet bulb นอกช่วงตาราง (factor อิ่มตัว)": d["wb_clipped"],
        "CDU นอกช่วงตาราง (factor อิ่มตัว)": d["cdu_clipped"],
        "ความเร็วลมหลุด ±SD": d["wind_out_of_sd"],
        "คอมเพรสเซอร์ตัด (kW ต่ำมาก)": kw < cfg.min_kw,
        "kW เกินสเปก > 20%": kw > cfg.power_spec * 1.2,
        "BTU เกินสเปก > 30%": btu > cfg.btu_spec * 1.3,
        "BTU ต่ำกว่าครึ่งของสเปก": btu < cfg.btu_spec * 0.5,
        "EER สูงเกินจริง (> 1.5 เท่าสเปก)": eer > cfg.eer_spec * 1.5,
        "EER ติดลบ": eer < 0,
        "ลมกระโดด (spike)": mad_outlier(d[cfg.wind_speed]),
        "kW กระโดด (spike)": mad_outlier(kw),
    }

    for name, mask in F.items():
        d[FLAG_PREFIX + name] = pd.Series(mask, index=d.index).fillna(False).astype(bool)

    cols = [c for c in d.columns if c.startswith(FLAG_PREFIX)]
    d["n_flags"] = d[cols].sum(axis=1).astype(int)
    d["suspect"] = d["n_flags"] > 0
    return d


def flag_counts(d):
    return {c[len(FLAG_PREFIX):]: int(d[c].sum())
            for c in d.columns if c.startswith(FLAG_PREFIX)}


def _safe(x, nd=2):
    try:
        v = float(x)
        return None if pd.isna(v) else round(v, nd)
    except (TypeError, ValueError):
        return None


def summary(d, cfg):
    ok = d[~d["suspect"]]
    stat_cols = [c for c in ["Enthapy", "Delta T", "btu",
                             "Power_Corrected (kW)", "EER"] if c in d.columns]
    wind = d["Average Wind Speed (1.5 SD)"].dropna()
    return {
        "สถานที่": cfg.site_name,
        "ยี่ห้อ/รุ่น": f"{cfg.air_brand} / {cfg.air_model}",
        "ช่วงเวลา": [str(d["Date/Time"].min()), str(d["Date/Time"].max())],
        "จำนวนแถวทั้งหมด": int(len(d)),
        "แถวที่ติด flag": int(d["suspect"].sum()),
        "แถวสะอาด": int(len(ok)),
        "สเปกเครื่อง": {"BTU": cfg.btu_spec, "kW": cfg.power_spec, "EER": cfg.eer_spec},
        "ค่าเฉลี่ยเฉพาะแถวสะอาด": {
            "BTU": _safe(ok["btu"].mean(), 0) if len(ok) else None,
            "kW": _safe(ok["Power_Corrected (kW)"].mean(), 3) if len(ok) else None,
            "EER": _safe(ok["EER"].mean(), 2) if len(ok) else None,
        },
        "สถิติรวม": d[stat_cols].describe().round(2).to_dict(),
        "จำนวนแต่ละ flag": {k: v for k, v in flag_counts(d).items() if v > 0},
        "พื้นที่หน้าคอยล์ (m²)": round(cfg.air_size, 4),
        "ลมเฉลี่ยที่ใช้คำนวณ (m/s)": _safe(wind.iloc[0], 3) if len(wind) else None,
        "CMM": _safe(d["cmm"].dropna().iloc[0], 2) if d["cmm"].notna().any() else None,
    }
