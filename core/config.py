"""ค่าตั้งต้นทั้งหมด (แทน @param ของ Colab)"""
from dataclasses import dataclass, asdict, fields
import json


def _norm_key(s: str) -> str:
    """ล้างช่องว่างซ้ำ / \r\n / non-breaking space ออกจากชื่อคอลัมน์"""
    import re
    s = str(s).replace("\r", " ").replace("\n", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Cfg:
    # --- sensor ---
    cdu_number: str = "993"
    supply_number: str = "740"
    return_number: str = "672"
    flow_number: str = "213"
    # --- ช่องลม ---
    air_width: float = 0.05
    air_length: float = 0.66
    # --- ข้อมูลเครื่อง ---
    air_brand: str = "-"
    air_model: str = "-"
    site_name: str = "-"
    btu_spec: float = 13000.0
    power_spec: float = 1.03
    eer_spec: float = 10.0
    # --- ขั้นสูง ---
    trim_head: int = 5
    trim_tail: int = 5
    wind_sd: float = 1.5
    merge_tol_s: int = 90
    min_kw: float = 0.10          # ต่ำกว่านี้ถือว่าคอมเพรสเซอร์ตัด

    # ---------- derived ----------
    @property
    def air_size(self) -> float:
        return float(self.air_width) * float(self.air_length)

    @property
    def cdu_temp(self) -> str:
        return _norm_key(f"{self.cdu_number} [°C]")

    @property
    def wetbulb_temp(self) -> str:
        return _norm_key(f"{self.return_number} Wet Bulb Temperature [°C]")

    @property
    def supply_temp(self) -> str:
        return _norm_key(f"{self.supply_number} [°C]")

    @property
    def supply_rh(self) -> str:
        return _norm_key(f"{self.supply_number} [%RH]")

    @property
    def return_temp(self) -> str:
        return _norm_key(f"{self.return_number} [°C]")

    @property
    def return_rh(self) -> str:
        return _norm_key(f"{self.return_number} [%RH]")

    @property
    def wind_speed(self) -> str:
        return _norm_key(f"{self.flow_number} [m/s]")

    def required_cols(self):
        return [self.cdu_temp, self.wetbulb_temp, self.supply_temp,
                self.supply_rh, self.return_temp, self.return_rh, self.wind_speed]

    # ---------- validate ----------
    def validate(self, available_cols=None):
        errs, warns = [], []
        nums = [self.cdu_number, self.supply_number,
                self.return_number, self.flow_number]
        if any(n in (None, "") for n in nums):
            errs.append("ยังเลือก sensor ไม่ครบทั้ง 4 ตัว")
        elif len(set(nums)) != 4:
            errs.append("เลข sensor ซ้ำกัน — CDU / Supply / Return / Flow ต้องไม่ซ้ำ")

        if self.air_width <= 0 or self.air_length <= 0:
            errs.append("ขนาดช่องลมต้องมากกว่า 0")
        elif self.air_size > 2:
            warns.append(f"พื้นที่หน้าคอยล์ {self.air_size:.3f} m² ใหญ่ผิดปกติ "
                         "— ตรวจหน่วยว่าเป็นเมตร ไม่ใช่เซนติเมตร")

        if self.btu_spec <= 0 or self.power_spec <= 0:
            errs.append("BTU spec และ kW spec ต้องมากกว่า 0")
        else:
            implied = self.btu_spec / (self.power_spec * 1000)
            if abs(implied - self.eer_spec) > 1.5:
                warns.append(f"EER spec ที่กรอก ({self.eer_spec:.2f}) "
                             f"ไม่ตรงกับ BTU/W ที่คำนวณได้ ({implied:.2f})")

        if available_cols is not None:
            have = {_norm_key(c) for c in available_cols}
            miss = [c for c in self.required_cols() if c not in have]
            if miss:
                errs.append("ไม่พบคอลัมน์ในไฟล์อุณหภูมิ: " + ", ".join(miss))
        return errs, warns

    # ---------- preset ----------
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(s: str) -> "Cfg":
        data = json.loads(s)
        allowed = {f.name for f in fields(Cfg)}
        return Cfg(**{k: v for k, v in data.items() if k in allowed})
