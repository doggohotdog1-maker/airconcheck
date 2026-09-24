"""เรียก Gemini API ให้อ่านสรุป + ตัวอย่างแถวน่าสงสัย แล้วอธิบายเชิงวิศวกรรม"""
import json

SYSTEM = """คุณเป็นวิศวกรทดสอบสมรรถนะเครื่องปรับอากาศหน้างาน ใช้วิธี air-enthalpy
วิเคราะห์จาก context ที่ให้เท่านั้น ห้ามเดาตัวเลขที่ไม่มีใน context
ตอบภาษาไทย กระชับ เป็นหัวข้อดังนี้

1. คุณภาพข้อมูลโดยรวม — เชื่อถือได้ประมาณกี่เปอร์เซ็นต์ เพราะอะไร
2. จุดที่ทำให้ EER / BTU เพี้ยน — ระบุเวลาและ flag ที่เกี่ยวข้อง
3. สาเหตุเชิงวิศวกรรมที่เป็นไปได้ เช่น
   - sensor wet bulb เปียกเกิน หรือผ้าแห้ง
   - ลมรั่วที่หน้ากาก / anemometer วางไม่กลางช่องลม
   - คอมเพรสเซอร์ตัดระหว่างวัด
   - CDU อยู่นอกช่วงตาราง correction factor
   - นาฬิกา power logger กับ data logger ไม่ตรงกัน
4. ค่าที่ควรใช้รายงาน (หลังตัดจุดเสีย) เทียบกับสเปก พร้อมบอกว่าผ่านหรือไม่ผ่าน
5. ข้อควรปรับปรุงในการวัดครั้งหน้า"""


def analyze(ctx, samples, api_key, model="gemini-2.5-flash"):
    if not api_key:
        return "ยังไม่ได้ใส่ API Key"
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "ยังไม่ได้ติดตั้งไลบรารี google-genai (รบกวนเพิ่ม google-genai ใน requirements.txt)"

    payload = {"สรุปผลการวัด": ctx, "ตัวอย่างแถวที่น่าสงสัย": samples}
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=json.dumps(payload, ensure_ascii=False, default=str),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                temperature=0.2,
            ),
        )
        return response.text
    except Exception as e:
        return f"เรียก Gemini AI ไม่สำเร็จ: {e}"
