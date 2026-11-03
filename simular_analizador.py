"""Simula un analizador enviando un mensaje HL7 ORU^R01. Uso: python simular_analizador.py OC-DEMO-00006"""
import sys, urllib.request
folio = sys.argv[1] if len(sys.argv) > 1 else "OC-DEMO-00006"
msg = "\r".join(["MSH|^~\\&|ANALIZADOR|LAB|OCAC|HOSP|20261030120000||ORU^R01|1|P|2.5", "PID|1||EXP-0006||Cabrera^Sofia",
                 f"OBR|1||{folio}|4548-4^HbA1c^LN", "OBX|1|NM|4548-4^HbA1c^LN||6.9|%|4.0-5.6|H|||F"])
r = urllib.request.Request("http://127.0.0.1:8000/api/analizador/hl7", msg.encode(),
                           {"X-API-Key": "analizador-demo-key", "Content-Type": "text/plain"})
print(urllib.request.urlopen(r).read().decode())
