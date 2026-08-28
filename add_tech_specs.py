import re

with open('generate_report.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update TOC
toc_old = "        ('11.', 'Deployment Architecture', GOLD),\n        ('12.', 'References', GRAY_400),\n    ]"
toc_new = "        ('11.', 'Deployment Architecture', GOLD),\n        ('12.', 'Technical Specifications', BLUE),\n        ('13.', 'References', GRAY_400),\n    ]"
content = content.replace(toc_old, toc_new)

# 2. Add Section 12 before References
sec12_content = """
    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 12: TECHNICAL SPECIFICATIONS
    # ══════════════════════════════════════════════════════════════════════════
    story += section_header('12. Technical Specifications',
        'Data schemas, project directory structure, and essential execution commands.', styles, BLUE)

    # 12.1 CSV Schemas
    story.append(Paragraph('12.1 Explicit CSV Schemas', styles['h2']))
    story.append(Paragraph('The synthetic data generator produces three standardized CSV files. Below are their schemas and sample rows:', styles['body']))
    
    csv_data = [
        ['Bank / Gateway Feed (bank.csv)', 'txn_id, date, amount, description, reference, currency\\nB001, 2024-01-15, 1195.00, "RAZORPAY SETTLEMENT", "RZP-A1B2", INR'],
        ['Internal Ledger (ledger.csv)', 'txn_id, date, amount, description, invoice_id, currency\\nL001, 2024-01-14, 1200.00, "Invoice #INV-101 - Software License", "INV-101", INR'],
        ['Ground Truth (ground_truth.csv)', 'bank_txn_id, ledger_txn_id, mismatch_type, notes\\nB001, L001, amount_fee, "Razorpay 0.4% fee deducted"'],
    ]
    
    c_rows = []
    for name, code in csv_data:
        c_rows.append([Paragraph(f'<b>{name}</b>', ParagraphStyle('cname', fontName='Helvetica-Bold', fontSize=9, textColor=TEAL))])
        c_rows.append([Paragraph(code.replace('\\n', '<br/>'), styles['code'])])
    
    c_tbl = Table(c_rows, colWidths=[15.5*cm])
    c_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), DARK_CARD),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, DARK_BORDER)
    ]))
    story.append(c_tbl)
    story.append(Spacer(1, 0.4*cm))

    # 12.2 File Tree
    story.append(Paragraph('12.2 Visual File Tree', styles['h2']))
    story.append(Paragraph('The complete monolithic project structure for the AI Finance Controller:', styles['body']))
    
    tree_text = '''razorpay_track4/
├── backend/
│   ├── main.py              # FastAPI app, all routes + SSE
│   ├── data_generator.py    # 60+ synthetic records, 9 mismatch types
│   ├── blocker.py           # DeepBlocker-inspired SIF embeddings
│   ├── normalizer.py        # Ditto-inspired span normalization
│   ├── reconciler.py        # 4-tier engine: Exact → JaroWinkler+FS → LLM
│   ├── scorer.py            # Precision/Recall/F1 vs ground truth
│   ├── llm_agent.py         # Gemini API: Ditto serialization
│   ├── qa_agent.py          # Settlement Q&A via Gemini
│   ├── models.py            # Pydantic schemas
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── UploadZone.jsx, PipelineProgress.jsx, MatchTable.jsx...
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
└── .env                     # GEMINI_API_KEY'''

    story.append(Table([[Paragraph(tree_text.replace('\\n', '<br/>').replace(' ', '&nbsp;'), styles['code'])]], colWidths=[15.5*cm], 
                 style=TableStyle([('BACKGROUND', (0,0), (-1,-1), DARK_CARD), ('PADDING', (0,0), (-1,-1), 10)])))
    
    story.append(Spacer(1, 0.4*cm))
    story.append(PageBreak())

    # 12.3 Terminal Commands
    story.append(Paragraph('12.3 Terminal Execution Commands', styles['h2']))
    story.append(Paragraph('The precise bash execution blocks for automated testing, local running, and deployment:', styles['body']))
    
    cmd_data = [
        ['Automated Verification Tests', 'pytest backend/tests/ -v'],
        ['Local Backend (FastAPI)', 'cd backend && uvicorn main:app --reload --port 8000'],
        ['Local Frontend (React+Vite)', 'cd frontend && npm install && npm run dev'],
        ['Vercel Deployment (Frontend)', 'cd frontend && npm run build && vercel --prod'],
    ]
    
    cmd_rows = []
    for name, cmd in cmd_data:
        cmd_rows.append([Paragraph(f'<b>{name}</b>', ParagraphStyle('cmd_name', fontName='Helvetica-Bold', fontSize=9, textColor=ORANGE))])
        cmd_rows.append([Paragraph(cmd, styles['code'])])
    
    cmd_tbl = Table(cmd_rows, colWidths=[15.5*cm])
    cmd_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), DARK_CARD),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(cmd_tbl)
    story.append(PageBreak())
"""

content = content.replace("    # SECTION 12: REFERENCES", sec12_content + "\n    # ══════════════════════════════════════════════════════════════════════════\n    # SECTION 13: REFERENCES")
content = content.replace("story += section_header('12. References', '', styles, GRAY_600)", "story += section_header('13. References', '', styles, GRAY_600)")

with open('generate_report.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Technical specifications section added successfully.')
