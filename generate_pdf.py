import os
import re
import subprocess
import markdown
import pypdf

MD_PATH = r"C:\Users\Suman sahu\.gemini\antigravity-ide\brain\285f3acf-e232-4166-8a48-8e5b10cf1f12\MEIL_ESG_Control_Tower_Complete_Jury_Viva_Guide.md"
HTML_PATH = r"C:\Users\Suman sahu\.gemini\antigravity-ide\brain\285f3acf-e232-4166-8a48-8e5b10cf1f12\scratch\viva_guide.html"
PDF_ARTIFACT_PATH = r"C:\Users\Suman sahu\.gemini\antigravity-ide\brain\285f3acf-e232-4166-8a48-8e5b10cf1f12\MEIL_ESG_Control_Tower_Complete_Jury_Viva_Guide.pdf"
PDF_WORKSPACE_PATH = r"c:\ESG_PLatform_2\MEIL_ESG_Control_Tower_Complete_Jury_Viva_Guide.pdf"

def build_pdf():
    print("Reading markdown...")
    with open(MD_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()

    # Pre-process markdown tags
    # Replace badges with nice html badges
    md_text = md_text.replace("[Verified in Source]", '<span class="badge badge-source">✓ Verified in Source</span>')
    md_text = md_text.replace("[Verified in Database]", '<span class="badge badge-db">✓ Verified in Database</span>')
    md_text = md_text.replace("[External Research]", '<span class="badge badge-ext">🔍 External Research</span>')
    md_text = md_text.replace("[Inferred]", '<span class="badge badge-inferred">ℹ Inferred</span>')

    # Convert markdown to HTML
    print("Converting Markdown to HTML...")
    html_content = markdown.markdown(
        md_text,
        extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.codehilite',
            'markdown.extensions.toc',
            'markdown.extensions.sane_lists'
        ]
    )

    # Post-process HTML for section styling
    # Add page-break class to h2 tags starting from Section 1
    # Replace <h2>1. Executive Summary</h2> with <h2 class="section-heading"><span class="section-num">01</span> Executive Summary</h2>
    def format_h2(match):
        full = match.group(0)
        content = match.group(1).strip()
        # Check if starts with a number like "1. Executive Summary"
        m = re.match(r"^(\d+)\.\s*(.*)$", content)
        if m:
            num = int(m.group(1))
            title = m.group(2)
            return f'<h2 class="section-heading" id="section-{num}"><span class="sec-pill">SECTION {num:02d}</span><span class="sec-title">{title}</span></h2>'
        return f'<h2 class="section-heading">{content}</h2>'

    html_content = re.sub(r'<h2>(.*?)</h2>', format_h2, html_content)

    # Style Q&A blocks: **Q:** or **Question:**
    # Pattern: <strong>Q(\d*)?:(.*?)</strong>
    def format_q(match):
        q_id = match.group(1) or ""
        q_text = match.group(2).strip()
        label = f"QUESTION {q_id}" if q_id else "JURY QUESTION"
        return f'<div class="qa-box"><div class="q-header"><span class="q-badge">{label}</span><span class="q-text">{q_text}</span></div>'

    # Assemble complete HTML document with executive print styling
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MEIL ESG Control Tower — Complete Jury Viva Preparation & Technical Research Guide</title>
<style>
  @page {{
    size: A4 portrait;
    margin: 18mm 16mm 18mm 16mm;
    @top-right {{
      content: "MEIL ESG Control Tower — Technical Jury Reference Guide";
      font-family: 'Segoe UI', -apple-system, Arial, sans-serif;
      font-size: 8pt;
      color: #64748b;
      font-weight: 500;
    }}
    @bottom-right {{
      content: "Page " counter(page);
      font-family: 'Segoe UI', -apple-system, Arial, sans-serif;
      font-size: 8pt;
      color: #475569;
      font-weight: 600;
    }}
    @bottom-left {{
      content: "CONFIDENTIAL • UNIVERSITY TECHNICAL JURY VIVA 2026";
      font-family: 'Segoe UI', -apple-system, Arial, sans-serif;
      font-size: 7.5pt;
      color: #94a3b8;
      letter-spacing: 0.5px;
    }}
  }}

  @page:first {{
    margin: 0;
    @top-right {{ content: normal; }}
    @bottom-right {{ content: normal; }}
    @bottom-left {{ content: normal; }}
  }}

  * {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    background: #ffffff;
    line-height: 1.6;
    font-size: 10.5pt;
    margin: 0;
    padding: 0;
  }}

  /* COVER PAGE */
  .cover-page {{
    page-break-after: always;
    min-height: 100vh;
    padding: 45mm 25mm 30mm 25mm;
    background: linear-gradient(145deg, #0f172a 0%, #1e293b 45%, #064e3b 100%);
    color: #ffffff;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-sizing: border-box;
  }}

  .cover-top {{
    display: flex;
    flex-direction: column;
    gap: 14px;
  }}

  .cover-tag {{
    display: inline-block;
    align-self: flex-start;
    padding: 6px 14px;
    background: rgba(16, 185, 129, 0.2);
    border: 1px solid #10b981;
    color: #34d399;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 1.5px;
    border-radius: 9999px;
    text-transform: uppercase;
  }}

  .cover-title {{
    font-size: 32pt;
    font-weight: 800;
    line-height: 1.15;
    color: #ffffff;
    margin: 12px 0 6px 0;
    letter-spacing: -0.5px;
  }}

  .cover-subtitle {{
    font-size: 14pt;
    font-weight: 400;
    color: #cbd5e1;
    line-height: 1.4;
    max-width: 650px;
    margin-bottom: 24px;
  }}

  .cover-quote {{
    border-left: 4px solid #10b981;
    padding: 12px 20px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 0 8px 8px 0;
    font-size: 11.5pt;
    font-weight: 500;
    color: #6ee7b7;
    margin: 15px 0 35px 0;
  }}

  .cover-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-top: 20px;
  }}

  .cover-card {{
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 14px 18px;
  }}

  .cover-card-label {{
    font-size: 8pt;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #94a3b8;
    margin-bottom: 4px;
    font-weight: 600;
  }}

  .cover-card-val {{
    font-size: 10.5pt;
    color: #f1f5f9;
    font-weight: 600;
  }}

  .cover-footer {{
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid rgba(255, 255, 255, 0.15);
    display: flex;
    justify-content: space-between;
    font-size: 8.5pt;
    color: #94a3b8;
  }}

  /* MAIN CONTENT STYLES */
  .document-body {{
    padding: 0;
  }}

  h1, h2, h3, h4, h5, h6 {{
    color: #0f172a;
    font-weight: 700;
    page-break-after: avoid;
    break-after: avoid;
  }}

  h1 {{
    font-size: 20pt;
    border-bottom: 2.5px solid #059669;
    padding-bottom: 8px;
    margin-top: 0;
    margin-bottom: 16px;
  }}

  .section-heading {{
    page-break-before: always;
    break-before: page;
    margin-top: 0;
    padding-top: 10px;
    margin-bottom: 18px;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  .sec-pill {{
    background: #0f172a;
    color: #ffffff;
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 10px;
    border-radius: 6px;
    display: inline-block;
  }}

  .sec-title {{
    font-size: 15pt;
    color: #0f172a;
    font-weight: 700;
  }}

  h3 {{
    font-size: 12.5pt;
    color: #1e293b;
    margin-top: 22px;
    margin-bottom: 10px;
    border-left: 3px solid #059669;
    padding-left: 8px;
  }}

  h4 {{
    font-size: 11pt;
    color: #334155;
    margin-top: 16px;
    margin-bottom: 8px;
  }}

  p {{
    margin: 8px 0;
    text-align: justify;
  }}

  /* TABLES */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
    break-inside: avoid;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    overflow: hidden;
  }}

  thead th {{
    background-color: #0f172a;
    color: #ffffff;
    font-weight: 600;
    text-align: left;
    padding: 8px 10px;
    border: 1px solid #1e293b;
    font-size: 9pt;
    letter-spacing: 0.3px;
  }}

  tbody td {{
    padding: 7px 10px;
    border: 1px solid #e2e8f0;
    vertical-align: top;
    line-height: 1.45;
  }}

  tbody tr:nth-child(even) {{
    background-color: #f8fafc;
  }}

  /* CODE BLOCKS */
  pre {{
    background: #0f172a;
    color: #f1f5f9;
    border-radius: 6px;
    padding: 12px 14px;
    font-size: 8.5pt;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    overflow-x: auto;
    page-break-inside: avoid;
    break-inside: avoid;
    border: 1px solid #334155;
    line-height: 1.45;
    margin: 12px 0;
  }}

  code {{
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 9pt;
  }}

  p code, li code, td code {{
    background: #f1f5f9;
    color: #0f172a;
    padding: 1px 5px;
    border-radius: 4px;
    border: 1px solid #e2e8f0;
    font-size: 8.5pt;
    font-weight: 500;
  }}

  /* BLOCKQUOTES */
  blockquote {{
    border-left: 4px solid #059669;
    background: #f0fdf4;
    padding: 10px 14px;
    margin: 14px 0;
    border-radius: 0 6px 6px 0;
    color: #064e3b;
    font-size: 10pt;
    page-break-inside: avoid;
    break-inside: avoid;
  }}

  blockquote p {{
    margin: 4px 0;
  }}

  /* LISTS */
  ul, ol {{
    margin: 8px 0 12px 20px;
    padding: 0;
  }}

  li {{
    margin-bottom: 5px;
    line-height: 1.5;
  }}

  /* BADGES */
  .badge {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 9999px;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 0.3px;
    margin: 0 2px;
    vertical-align: middle;
  }}

  .badge-source {{
    background: #dcfce7;
    color: #166534;
    border: 1px solid #86efac;
  }}

  .badge-db {{
    background: #e0f2fe;
    color: #075985;
    border: 1px solid #7dd3fc;
  }}

  .badge-ext {{
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #fcd34d;
  }}

  .badge-inferred {{
    background: #f3e8ff;
    color: #6b21a8;
    border: 1px solid #d8b4fe;
  }}

  hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 20px 0;
  }}

  /* TABLE OF CONTENTS */
  .toc {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 18px 24px;
    margin: 20px 0;
    page-break-inside: avoid;
    break-inside: avoid;
  }}

  .toc ul {{
    list-style: none;
    padding-left: 0;
    margin: 0;
    columns: 2;
    column-gap: 30px;
  }}

  .toc li {{
    margin-bottom: 8px;
    font-size: 9.5pt;
  }}

  .toc a {{
    color: #0284c7;
    text-decoration: none;
    font-weight: 500;
  }}

  .toc a:hover {{
    text-decoration: underline;
  }}

  /* CALLOUT BOX */
  .callout-box {{
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-left: 4px solid #0284c7;
    border-radius: 0 6px 6px 0;
    padding: 10px 14px;
    margin: 12px 0;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover-page">
  <div class="cover-top">
    <div class="cover-tag">MEIL TECHNICAL JURY VIVA REFERENCE MANUAL 2026</div>
    <div class="cover-title">MEIL ESG CONTROL TOWER</div>
    <div class="cover-subtitle">Complete System Architecture, Data Pipeline, Carbon Accounting Mathematics, OCR Intelligence, Security & Jury Defense Guide</div>
    <div class="cover-quote">"Capture Once. Verify Intelligently. Calculate Consistently. Trace Everything."</div>
    
    <div class="cover-grid">
      <div class="cover-card">
        <div class="cover-card-label">Target Organization</div>
        <div class="cover-card-val">Megha Engineering & Infrastructures Ltd (MEIL)</div>
      </div>
      <div class="cover-card">
        <div class="cover-card-label">Compliance Frameworks</div>
        <div class="cover-card-val">SEBI BRSR Core • GHG Protocol (Scope 1, 2, 3)</div>
      </div>
      <div class="cover-card">
        <div class="cover-card-label">Technology Architecture</div>
        <div class="cover-card-val">Monolithic Django 5 • PostgreSQL • Celery Services • Vercel</div>
      </div>
      <div class="cover-card">
        <div class="cover-card-label">Audited Codebase Scope</div>
        <div class="cover-card-val">5,277 Model Lines • 34+ Models • 15 Services • 45 Test Suites</div>
      </div>
      <div class="cover-card">
        <div class="cover-card-label">Defense Team</div>
        <div class="cover-card-val">5 Engineering Roles (Architecture, Backend, OCR, Anomaly, Security)</div>
      </div>
      <div class="cover-card">
        <div class="cover-card-label">Document Version</div>
        <div class="cover-card-val">Version 1.0 (Final Jury Edition) • Complete 20 Sections</div>
      </div>
    </div>
  </div>

  <div class="cover-footer">
    <div>CONFIDENTIAL &amp; PROPRIETARY — ACADEMIC TECHNICAL JURY PRESENTATION</div>
    <div>OCTOBER 2026</div>
  </div>
</div>

<!-- DOCUMENT BODY -->
<div class="document-body">
{html_content}
</div>

</body>
</html>
"""

    os.makedirs(os.path.dirname(HTML_PATH), exist_ok=True)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Wrote styled HTML to {HTML_PATH}")

    # Compile to PDF using Headless Edge
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    print("Compiling PDF with Microsoft Edge Headless...")
    cmd = [
        edge_path,
        "--headless=new",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_ARTIFACT_PATH}",
        HTML_PATH
    ]
    subprocess.run(cmd, check=True)

    # Copy to Project Root
    import shutil
    shutil.copyfile(PDF_ARTIFACT_PATH, PDF_WORKSPACE_PATH)
    print(f"Copied PDF to workspace root: {PDF_WORKSPACE_PATH}")

    # Inspect generated PDF
    reader = pypdf.PdfReader(PDF_ARTIFACT_PATH)
    page_count = len(reader.pages)
    size_mb = os.path.getsize(PDF_ARTIFACT_PATH) / (1024 * 1024)
    print(f"SUCCESS: Generated PDF with {page_count} pages! File size: {size_mb:.2f} MB")

if __name__ == "__main__":
    build_pdf()
