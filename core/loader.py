"""อ่านไฟล์ CSV ทั้งสอง + รวมตาราง (ทนต่อ encoding ไทยและเวลาเหลื่อม)"""
import io
import numpy as np
import pandas as pd
from core.config import _norm_key

ENCODINGS = ["utf-8-sig", "utf-8", "cp874", "tis-620", "latin-1"]


def _bytes_of(file):
    """อ่าน uploaded file / path เป็น bytes แล้วกรอกลับให้เรียบร้อย"""
    if hasattr(file, "read"):
        try:
            file.seek(0)
        except Exception:
            pass
        raw = file.read()
        try:
            file.seek(0)
        except Exception:
            pass
    else:
        with open(file, "rb") as fh:
            raw = fh.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return raw


def read_csv_any(file, **kw):
    """อ่าน CSV โดยลอง encoding หลายตัว"""
    raw = _bytes_of(file)
    last = None
    for enc in ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc, **kw)
        except UnicodeDecodeError as e:
            last = e
        except LookupError as e:
            last = e
    raise ValueError(f"อ่านไฟล์ไม่ได้ทุก encoding ที่ลอง: {last}")


def temp_columns(file):
    """อ่านเฉพาะหัวคอลัมน์ (เร็ว) ไว้ทำ dropdown"""
    head = read_csv_any(file, nrows=0)
    return [_norm_key(c) for c in head.columns]


# ------------------------------------------------------------------ TEMP
def read_temp(file, cfg):
    notes = []
    df = read_csv_any(file)
    df.columns = [_norm_key(c) for c in df.columns]

    if "Date/Time" not in df.columns:
        cand = [c for c in df.columns if "date" in c.lower()]
        if not cand:
            raise KeyError(f"ไม่พบคอลัมน์ Date/Time — มี: {list(df.columns)[:15]}")
        df = df.rename(columns={cand[0]: "Date/Time"})
        notes.append(f"ใช้คอลัมน์ '{cand[0]}' เป็น Date/Time")

    # ตัดตั้งแต่แถว Overall Average ลงไป (ถ้ามี)
    mark = df["Date/Time"].astype(str).str.strip().str.lower()
    hit = df.index[mark == "overall average"]
    if len(hit):
        df = df.loc[: hit[0] - 1]
    else:
        notes.append("ไม่พบแถว 'Overall Average' — ใช้ข้อมูลทั้งไฟล์")

    df = df.loc[:, ~df.columns.str.contains("^Unnamed", na=False)]
    df = df.replace({"-": np.nan, "--": np.nan, "": np.nan, "OL": np.nan})

    need = cfg.required_cols()
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise KeyError("ไม่พบคอลัมน์: " + ", ".join(missing) +
                       f"\nคอลัมน์ที่มี: {list(df.columns)[:20]}")

    for c in need:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    before = len(df)
    df = df.dropna(subset=need)           # ทิ้งเฉพาะแถวที่ sensor ที่ใช้จริงขาด
    dropped = before - len(df)
    if dropped:
        notes.append(f"ตัดแถวที่ sensor ขาดข้อมูล {dropped} / {before} แถว")

    df["Date/Time"] = pd.to_datetime(df["Date/Time"], errors="coerce")
    bad_t = df["Date/Time"].isna().sum()
    if bad_t:
        notes.append(f"ตัดแถวที่อ่านเวลาไม่ได้ {bad_t} แถว")
    df = df.dropna(subset=["Date/Time"])

    df = (df.sort_values("Date/Time")
            .drop_duplicates(subset=["Date/Time"], keep="last")
            .reset_index(drop=True))
    if df.empty:
        raise ValueError("ไฟล์อุณหภูมิไม่เหลือข้อมูลหลังทำความสะอาด")

    notes.append(f"ไฟล์อุณหภูมิ: ใช้ได้ {len(df)} แถว "
                 f"({df['Date/Time'].min()} → {df['Date/Time'].max()})")
    return df, notes


# ----------------------------------------------------------------- POWER
def _find_header_row(raw, max_scan=12):
    """หาแถวที่เป็นหัวตารางจริง (แถวที่มีทั้ง Date และ Avg. KW / KW)"""
    for i in range(min(max_scan, len(raw))):
        cells = [_norm_key(v).lower() for v in raw.iloc[i].tolist()]
        joined = " | ".join(cells)
        if "date" in joined and ("avg. kw" in joined or "kw" in joined):
            return i
    return None


# ----------------------------------------------------------------- POWER (แก้ไข)
def read_power(file):
    # ... (โค้ดช่วงอ่านไฟล์และหา Date/Time คงเดิม) ...

    # 1. กรองคอลัมน์ที่มีคำว่า 'kw' แต่ต้องไม่มี 'kvar' และต้องไม่ใช่ 'kw hours' / 'kwh'
    kw_cols = [
        c for c in df.columns 
        if "kw" in c.lower() 
        and "kvar" not in c.lower() 
        and "kwh" not in c.lower() 
        and "kw hours" not in c.lower()
    ]

    if not kw_cols:
        raise KeyError(f"ไม่พบคอลัมน์กำลังไฟ (KW) — มี: {list(df.columns)}")

    # 2. ค้นหาคอลัมน์ 3 Phase และ 1 Phase โดยเช็กทั้งคำว่า '3 phase' และ '3 ph'
    three = [c for c in kw_cols if "3 phase" in c.lower() or "3 ph" in c.lower()]
    one = [c for c in kw_cols if "l1 phase" in c.lower() or "l1 ph" in c.lower()]

    # 3. เจาะจงหาคอลัมน์ที่เป็น Average (ขึ้นต้นด้วย avg หรือมี avg)
    avg3 = [c for c in three if "avg" in c.lower()]
    avg1 = [c for c in one if "avg" in c.lower()]

    # 4. เลือกคอลัมน์ตามลำดับความสำคัญ
    if avg3:
        kw_col, phase = avg3[0], 3
    elif three:
        kw_col, phase = three[0], 3
    elif avg1:
        kw_col, phase = avg1[0], 1
    elif one:
        kw_col, phase = one[0], 1
    else:
        kw_col, phase = kw_cols[0], 0
        notes.append(f"ระบุเฟสไม่ได้ — ใช้คอลัมน์ '{kw_col}'")

    if phase:
        notes.append(f"ตรวจพบระบบ {phase} เฟส (คอลัมน์: {kw_col})")

    # ... (ส่วนประมวลผลต่อด้านล่างคงเดิม) ...


# ----------------------------------------------------------------- MERGE
def merge_sources(temp_df, power_df, cfg):
    """จับคู่ด้วย merge_asof — ทนเวลาที่ไม่ตรงกันเป๊ะ"""
    t = temp_df.sort_values("Date/Time").reset_index(drop=True)
    p = power_df.sort_values("Date/Time").reset_index(drop=True)
    notes = []

    ov_lo = max(t["Date/Time"].min(), p["Date/Time"].min())
    ov_hi = min(t["Date/Time"].max(), p["Date/Time"].max())
    if ov_lo > ov_hi:
        notes.append("⚠ ช่วงเวลาของสองไฟล์ไม่ทับกันเลย — ตรวจว่าเลือกไฟล์ถูกคู่")
    else:
        notes.append(f"ช่วงเวลาที่ทับกัน: {ov_lo} → {ov_hi}")

    m = pd.merge_asof(t, p, on="Date/Time", direction="nearest",
                      tolerance=pd.Timedelta(seconds=int(cfg.merge_tol_s)))
    matched = m["kw_raw"].notna().sum()
    notes.append(f"จับคู่ข้อมูลไฟฟ้าได้ {matched} / {len(m)} แถว "
                 f"(ยอมเวลาเหลื่อม ±{cfg.merge_tol_s} วินาที)")
    if matched == 0:
        notes.append("⚠ จับคู่ไม่ได้เลย — ลองเพิ่มค่า 'ยอมเวลาเหลื่อม' "
                     "หรือตรวจว่านาฬิกาสองเครื่องตั้งตรงกัน")
    return m, notes


def trim_edges(d, head, tail):
    """ตัดช่วง startup / shutdown แบบปลอดภัย"""
    head, tail = int(head), int(tail)
    if head + tail == 0:
        return d, "ไม่ตัดหัว-ท้าย"
    if len(d) <= head + tail + 3:
        return d, f"ข้อมูลมีแค่ {len(d)} แถว — ไม่ตัดหัว-ท้าย"
    return (d.iloc[head: len(d) - tail].reset_index(drop=True),
            f"ตัดหัว {head} แถว ท้าย {tail} แถว")
