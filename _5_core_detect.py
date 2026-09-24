"""อ่านหัวคอลัมน์ → รู้ว่ามี sensor เบอร์อะไร วัดอะไรได้บ้าง"""
import re
from core.config import _norm_key

_PAT = re.compile(r"^(\d+)\s*(.*)$")


def sensor_catalog(cols):
    """คืน {'672': {'temp','rh','wetbulb'}, '213': {'flow'}, ...}"""
    cat = {}
    for c in cols:
        c = _norm_key(c)
        m = _PAT.match(c)
        if not m:
            continue
        num, rest = m.group(1), m.group(2).lower()
        if "wet bulb" in rest:
            kind = "wetbulb"
        elif "%rh" in rest:
            kind = "rh"
        elif "m/s" in rest:
            kind = "flow"
        elif "[°c]" in rest or "[c]" in rest or "[oc]" in rest:
            kind = "temp"
        else:
            continue
        cat.setdefault(num, set()).add(kind)
    return cat


def options(cat, kind=None):
    if kind is None:
        keys = cat.keys()
    else:
        keys = [n for n, k in cat.items() if kind in k]
    return sorted(keys, key=lambda x: int(x))


def suggest(cat):
    """เดาบทบาทจาก field ที่แต่ละ sensor มี"""
    flow = options(cat, "flow")
    wetb = options(cat, "wetbulb")
    rh = options(cat, "rh")
    temp = options(cat, "temp")
    only_temp = [n for n in temp if cat[n] == {"temp"}]

    ret = wetb[0] if wetb else (rh[0] if rh else None)
    sup = next((n for n in rh if n != ret), None)
    cdu = only_temp[0] if only_temp else next(
        (n for n in temp if n not in (ret, sup)), None)
    return {"cdu": cdu, "return": ret, "supply": sup,
            "flow": flow[0] if flow else None}