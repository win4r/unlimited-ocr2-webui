#!/usr/bin/env python3
"""Create deterministic, original documents for deployment smoke tests."""
from pathlib import Path
import fitz

OUT = Path(__file__).resolve().parent.parent / "examples"
OUT.mkdir(parents=True, exist_ok=True)


def text(page, y, value, size=12, x=48):
    page.insert_text((x, y), value, fontsize=size, fontname="china-s" if any(ord(c)>127 for c in value) else "helv")


def table(page, y, rows):
    widths = [210, 120, 120]
    for n, row in enumerate(rows):
        x = 48
        for width, value in zip(widths, row):
            page.draw_rect(fitz.Rect(x, y+n*32, x+width, y+(n+1)*32), color=(.35,.4,.5), width=.7)
            text(page, y+n*32+21, str(value), x=x+9)
            x += width


doc = fitz.open()
p = doc.new_page(width=595, height=842)
text(p, 60, "Unlimited OCR 2 - Deployment Test", 20)
text(p, 100, "中英文混排测试：云端文档解析实验室", 16)
text(p, 142, "Invoice ID: UOCR-2026-001")
text(p, 170, "Date: 2026-10-29    Currency: CNY")
text(p, 207, "请核对中文、英文、数字和表格是否完整。", 13)
table(p, 240, [("Item", "Quantity", "Amount"), ("GPU Hours", "3", "120.00"), ("Storage", "1", "8.50"), ("Total", "", "128.50")])
text(p, 430, "Formula: E = mc^2     x^2 + y^2 = r^2")
text(p, 480, "Verification marker: SINGLE_PAGE_OK_12850")
p.get_pixmap(matrix=fitz.Matrix(2,2)).save(OUT/"mixed-single.png")
doc.close()

doc = fitz.open()
for i in range(3):
    p=doc.new_page(width=595,height=842)
    text(p, 60, "2026 Regional Sales Report", 21)
    text(p, 95, f"Section {i+1} - {'Introduction' if i==0 else 'Revenue Table' if i==1 else 'Conclusion'}",16)
    text(p, 135, f"中英文跨页文档测试，第 {i+1} 页，共 3 页。",13)
    if i==0:
        text(p,190,"This report contains a table continuing onto the next page.")
        table(p,630,[("Region","Q1","Q2"),("North","120","135"),("South","98","110")])
        text(p,790,"Table 1 continues on the following page.",10)
    elif i==1:
        text(p,190,"Table 1 (continued)")
        table(p,220,[("Region","Q1","Q2"),("East","145","160"),("West","87","95"),("Total","450","500")])
        text(p,430,"The Q2 total is 500. The improvement over Q1 is 50.")
    else:
        text(p,190,"结论：第二季度总额为 500，较第一季度增加 50。",13)
        text(p,235,"Verification marker: CROSS_PAGE_COMPLETE_500")
    text(p,815,f"Page {i+1} / 3",10,x=260)
doc.save(OUT/"cross-page-demo.pdf")
doc.close()

doc=fitz.open()
for i in range(12):
    p=doc.new_page(width=595,height=842)
    text(p,65,"Long Document Continuity Test",20)
    text(p,105,f"Chapter {i+1:02d} - Page {i+1} of 12",16)
    text(p,150,f"Unique page marker: UOCR_PAGE_{i+1:02d}_CHECK_{1000+i}")
    text(p,190,f"长文档测试：第 {i+1} 页，检查页面顺序与文字完整性。",13)
    table(p,240,[("Metric","Value","Unit"),("Page index",i+1,"page"),("Reference",1000+i,"number")])
    text(p,405,"Each page must appear once in the parsed output.")
    if i==11:text(p,470,"Final verification marker: LONG_DOCUMENT_END_12",14)
    text(p,810,f"Page {i+1} / 12",10,x=260)
doc.save(OUT/"long-12-pages.pdf")
doc.close()
print("Created three original deployment examples")
