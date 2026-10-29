from pathlib import Path

p = Path("evaluation/sow_report.py")
content = p.read_text(encoding="utf-8")
old = 'report["clinical_metrics"]["status"]'
new = 'report["clinical_metrics"].get("status", "MEASURED")'
if old in content:
    content = content.replace(old, new)
    p.write_text(content, encoding="utf-8")
    print("Replaced successfully!")
else:
    print("Old string not found!")
