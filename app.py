import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.config import Cfg
from core import detect, loader, physics, quality

st.set_page_config(page_title="AC EER Analyzer", layout="wide")
st.title("วิเคราะห์สมรรถนะเครื่องปรับอากาศ (EER / BTU)")


def get_secret(key):
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


# ---------- Sidebar: preset ----------
with st.sidebar:
    st.header("Preset")
    up = st.file_uploader("โหลดค่าที่บันทึกไว้ (.json)", type=["json"], key="preset_up")
    if up is not None:
        try:
            st.session_state["preset"] = Cfg.from_json(up.read().decode("utf-8"))
            st.success("โหลด preset แล้ว")
        except Exception as e:
            st.error(f"อ่าน preset ไม่ได้: {e}")
    if "cfg" in st.session_state:
        st.download_button("บันทึกค่าปัจจุบัน",
                           st.session_state["cfg"].to_json().encode("utf-8"),
                           file_name="eer_preset.json", mime="application/json")

P = st.session_state.get("preset", Cfg())

# ---------- STEP 1 ----------
st.subheader("1 · อัพโหลดไฟล์")
c1, c2 = st.columns(2)
f_temp = c1.file_uploader("ไฟล์อุณหภูมิ / ความชื้น / ลม", type=["csv"], key="ft")
f_power = c2.file_uploader("ไฟล์ Power Logger", type=["csv"], key="fp")
if f_temp:
    c1.caption(f"ไฟล์: **{f_temp.name}**")
if f_power:
    c2.caption(f"ไฟล์: **{f_power.name}**")

if not (f_temp and f_power):
    st.info("อัพโหลดครบทั้ง 2 ไฟล์เพื่อไปขั้นต่อไป")
    st.stop()

try:
    cols = loader.temp_columns(f_temp)
except Exception as e:
    st.error(f"อ่านหัวคอลัมน์ไฟล์อุณหภูมิไม่ได้: {e}")
    st.stop()

cat = detect.sensor_catalog(cols)
if not cat:
    st.error("อ่านเลข sensor จากหัวคอลัมน์ไม่ได้")
    st.write(cols)
    st.stop()
sug = detect.suggest(cat)

# ---------- STEP 2 ----------
st.subheader("2 · จับคู่ sensor")
st.caption(f"พบ sensor {len(cat)} ตัวในไฟล์ — ระบบเดาให้แล้ว แก้ได้ถ้าไม่ถูก")


def pick(col, label, kind, default, help_):
    opts = detect.options(cat, kind)
    if not opts:
        col.error(f"ไม่พบ sensor ชนิด {kind}")
        return None
    idx = opts.index(default) if default in opts else 0
    return col.selectbox(label, opts, index=idx, help=help_)


s1, s2, s3, s4 = st.columns(4)
cdu_n = pick(s1, "CDU (คอยล์ร้อน)", "temp", P.cdu_number or sug["cdu"],
             "อุณหภูมิอากาศเข้าคอยล์ร้อน — ใช้เปิดตาราง correction")
ret_n = pick(s2, "Return (ลมกลับ)", "wetbulb", P.return_number or sug["return"],
             "ต้องมีทั้ง [°C], [%RH] และ Wet Bulb")
sup_n = pick(s3, "Supply (ลมออก)", "rh", P.supply_number or sug["supply"],
             "ต้องมีทั้ง [°C] และ [%RH]")
flw_n = pick(s4, "Flow (ความเร็วลม)", "flow", P.flow_number or sug["flow"],
             "anemometer หน้าช่องลมออก")

with st.expander("ดู sensor ทั้งหมดในไฟล์"):
    st.dataframe(pd.DataFrame(
        [{"sensor": n, "มีข้อมูล": ", ".join(sorted(k))}
         for n, k in sorted(cat.items(), key=lambda x: int(x[0]))]),
        use_container_width=True)

# ---------- STEP 3 ----------
st.subheader("3 · ข้อมูลเครื่องและช่องลม")
with st.form("cfg_form"):
    a, b, c = st.columns(3)
    site = a.text_input("สถานที่ / ห้อง", P.site_name)
    brand = b.text_input("ยี่ห้อแอร์", P.air_brand)
    model = c.text_input("รุ่น", P.air_model)

    st.markdown("**ขนาดช่องลมออก (เมตร)**")
    d, e, f = st.columns(3)
    w = d.number_input("ความกว้าง (m)", value=float(P.air_width),
                       min_value=0.001, max_value=5.0, step=0.01, format="%.3f")
    l = e.number_input("ความยาว (m)", value=float(P.air_length),
                       min_value=0.001, max_value=5.0, step=0.01, format="%.3f")
    f.metric("พื้นที่หน้าตัด", f"{w * l:.4f} m²")

    st.markdown("**สเปกเครื่อง (ตาม nameplate)**")
    g, h, i = st.columns(3)
    btu = g.number_input("BTU/hr", value=float(P.btu_spec),
                         min_value=1000.0, step=500.0, format="%.0f")
    kwsp = h.number_input("กำลังไฟ (kW)", value=float(P.power_spec),
                          min_value=0.01, step=0.01, format="%.3f")
    eersp = i.number_input("EER", value=float(P.eer_spec),
                           min_value=1.0, step=0.1, format="%.2f")
    i.caption(f"จาก BTU/W = {btu / (kwsp * 1000):.2f}")

    with st.expander("ตั้งค่าขั้นสูง"):
        j, k, m_, n_ = st.columns(4)
        sd = j.number_input("กรองลมที่ ±SD", value=float(P.wind_sd),
                            min_value=0.5, max_value=4.0, step=0.1)
        tol = k.number_input("ยอมเวลาเหลื่อม (วินาที)", value=int(P.merge_tol_s),
                             min_value=0, max_value=600, step=10,
                             help="ใช้จับคู่เวลาไฟฟ้ากับอุณหภูมิที่ไม่ตรงกันเป๊ะ")
        th = m_.number_input("ตัดหัว (แถว)", value=int(P.trim_head),
                             min_value=0, max_value=120)
        tt = n_.number_input("ตัดท้าย (แถว)", value=int(P.trim_tail),
                             min_value=0, max_value=120)

    go_btn = st.form_submit_button("วิเคราะห์", type="primary",
                                   use_container_width=True)

cfg = Cfg(cdu_number=cdu_n, supply_number=sup_n, return_number=ret_n,
          flow_number=flw_n, air_width=w, air_length=l, air_brand=brand,
          air_model=model, site_name=site, btu_spec=btu, power_spec=kwsp,
          eer_spec=eersp, wind_sd=sd, merge_tol_s=int(tol),
          trim_head=int(th), trim_tail=int(tt))

errs, warns = cfg.validate(available_cols=cols)
for e_ in errs:
    st.error(e_)
for w_ in warns:
    st.warning(w_)
if errs:
    st.stop()
if not go_btn:
    st.info("กดปุ่ม **วิเคราะห์** เพื่อเริ่มประมวลผล")
    st.stop()

# ---------- STEP 4 ----------
st.session_state["cfg"] = cfg
with st.spinner("กำลังประมวลผล..."):
    try:
        t_df, n1 = loader.read_temp(f_temp, cfg)
        p_df, kw_col, phase, n2 = loader.read_power(f_power)
        t_df = physics.compute(t_df, cfg)
        m, n3 = loader.merge_sources(t_df, p_df, cfg)
        m = physics.add_power(m, cfg)
        m, n4 = loader.trim_edges(m, cfg.trim_head, cfg.trim_tail)
        m = quality.flag(m, cfg)
    except Exception as e:
        st.error(f"ประมวลผลไม่สำเร็จ: {e}")
        st.exception(e)
        st.stop()

if m.empty:
    st.error("ไม่เหลือข้อมูลหลังประมวลผล — ลองลดค่าตัดหัว-ท้าย")
    st.stop()

st.success("ประมวลผลเสร็จ")
with st.expander("บันทึกการประมวลผล", expanded=True):
    for n in n1 + n2 + n3 + [n4]:
        st.caption("• " + n)

ok = m[~m["suspect"]]
# กรองเอาเฉพาะช่วงที่แอร์ทำงาน (ตัดช่วงแอร์ตัดออก โดยเช็กว่า Power > 0.05 kW หรือไม่)
air_on = m[m["Power_Corrected (kW)"] > 0.05]

k1, k2, k3, k4 = st.columns(4)
k1.metric("EER เฉลี่ย (ขณะแอร์ทำงาน)",
          f"{air_on['EER'].mean():.2f}" if air_on["EER"].notna().any() else "-",
          f"สเปก {cfg.eer_spec:.2f}")

k2.metric("BTU เฉลี่ย",
          f"{air_on['btu'].mean():,.0f}" if air_on["btu"].notna().any() else "-",
          f"สเปก {cfg.btu_spec:,.0f}")

k3.metric("kW เฉลี่ย",
          f"{air_on['Power_Corrected (kW)'].mean():.3f}"
          if air_on["Power_Corrected (kW)"].notna().any() else "-",
          f"สเปก {cfg.power_spec:.3f}")

k4.metric("แถวน่าสงสัย (Defect)", f"{int(m['suspect'].sum())} / {len(m)}")


fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                    subplot_titles=("EER", "Power (kW)", "BTU/hr"))
sus = m[m["suspect"]]
for idx, colname in enumerate(["EER", "Power_Corrected (kW)", "btu"], start=1):
    fig.add_trace(go.Scatter(x=m["Date/Time"], y=m[colname], mode="lines",
                             name=colname), row=idx, col=1)
    fig.add_trace(go.Scatter(x=sus["Date/Time"], y=sus[colname], mode="markers",
                             marker=dict(color="red", size=7, symbol="x"),
                             name="น่าสงสัย", showlegend=(idx == 1)),
                  row=idx, col=1)
fig.add_hline(y=cfg.eer_spec, line_dash="dot", line_color="green", row=1, col=1)
fig.add_hline(y=cfg.power_spec, line_dash="dot", line_color="green", row=2, col=1)
fig.add_hline(y=cfg.btu_spec, line_dash="dot", line_color="green", row=3, col=1)
fig.update_layout(height=800, hovermode="x unified",
                  legend=dict(orientation="h", y=1.06))
st.plotly_chart(fig, use_container_width=True)

st.subheader("สรุปจุดที่ผิดปกติ")
fl = {k: v for k, v in quality.flag_counts(m).items() if v > 0}
if fl:
    tbl = pd.DataFrame(sorted(fl.items(), key=lambda x: -x[1]),
                       columns=["ปัญหา", "จำนวนแถว"])
    tbl["สัดส่วน"] = (tbl["จำนวนแถว"] / len(m) * 100).round(1).astype(str) + "%"
    st.dataframe(tbl, use_container_width=True, hide_index=True)
else:
    st.success("ไม่พบจุดผิดปกติ")

with st.expander("ดูแถวที่น่าสงสัยที่สุด 20 แถว"):
    show = ["Date/Time", "Enthapy", "Delta T", "btu", "kw_raw",
            "Power_Corrected (kW)", "EER", "n_flags"]
    st.dataframe(m[m["suspect"]].nlargest(20, "n_flags")[show].round(3),
                 use_container_width=True, hide_index=True)

st.download_button("ดาวน์โหลดผลลัพธ์ CSV",
                   m.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"eer_result_{f_temp.name}", mime="text/csv")
