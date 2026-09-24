def flag(d, cfg):
    d = d.copy()
    enth = pd.to_numeric(d["Enthapy"], errors="coerce")
    kw = pd.to_numeric(d["kw_raw"], errors="coerce")
    btu = pd.to_numeric(d["btu"], errors="coerce")
    eer = pd.to_numeric(d["EER"], errors="coerce")
    s_rh = pd.to_numeric(d[cfg.supply_rh], errors="coerce")
    r_rh = pd.to_numeric(d[cfg.return_rh], errors="coerce")

    # หาค่า Max Power ของไฟล์ชุดนี้ (ถ้าหาไม่ได้ ให้ใช้ค่าจาก cfg.min_kw สำรองไว้)
    max_kw = kw.max() if kw.notna().any() else 0
    cutoff_kw = max_kw * 0.8 if max_kw > 0 else cfg.min_kw

    F = {
        "ไม่มีข้อมูลไฟฟ้าตรงเวลานี้": kw.isna(),
        "Δh ติดลบ (ไม่ทำความเย็น)": enth <= 0,
        "Δh ต่ำผิดปกติ (< 2 kJ/kg)": (enth > 0) & (enth < 2),
        "Supply ร้อนกว่า Return": d["Delta T"] <= 0,
        "RH อิ่มตัว 100% (sensor เปียก)": (s_rh >= 99.5) | (r_rh >= 99.5),
        "Wet bulb นอกช่วงตาราง (factor อิ่มตัว)": d["wb_clipped"],
        "CDU นอกช่วงตาราง (factor อิ่มตัว)": d["cdu_clipped"],
        "ความเร็วลมหลุด ±SD": d["wind_out_of_sd"],
        "คอมเพรสเซอร์ตัด (kW ต่ำกว่า 80% ของ Max)": kw < cutoff_kw,  # <-- แก้เป็นต่ำกว่า 80% ของ Max
        "kW เกินสเปก > 20%": kw > cfg.power_spec * 1.2,
        "BTU เกินสเปก > 10%": btu > cfg.btu_spec * 1.1,
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
