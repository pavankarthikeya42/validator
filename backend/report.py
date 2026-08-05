import pandas as pd
from jinja2 import Template

def generate_csv_report(results: dict) -> str:
    """
    Generates CSV report contents from validation results.
    """
    rows = []
    for sec in results["sections"]:
        rows.append({
            "Section Name": sec["section"],
            "Status": sec["status"],
            "Similarity (%)": sec["similarity"],
            "Matched PDF Pages": ", ".join(map(str, sec["pdf_pages"])),
            "Matched Chunks Count": len(sec["matched_text"]),
            "Missing Chunks Count": len(sec["missing_text"]),
            "Missing Text Sample": " | ".join(sec["missing_text"])[:500] if sec["missing_text"] else "None"
        })
        
    df = pd.DataFrame(rows)
    return df.to_csv(index=False)

def generate_html_report(results: dict) -> str:
    """
    Generates HTML report contents from validation results.
    """
    template_str = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Karthera Validation Report</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background-color: #f8fafc;
                color: #1e293b;
                margin: 0;
                padding: 40px 20px;
            }
            .container {
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
            }
            h1 {
                font-size: 2.25rem;
                margin-top: 0;
                margin-bottom: 20px;
                color: #0f172a;
                border-bottom: 2px solid #e2e8f0;
                padding-bottom: 15px;
            }
            .summary-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 20px;
                margin-bottom: 30px;
            }
            .summary-card {
                background: #f1f5f9;
                padding: 20px;
                border-radius: 8px;
                text-align: center;
            }
            .summary-card .value {
                font-size: 2rem;
                font-weight: 700;
                color: #0f172a;
            }
            .summary-card .label {
                font-size: 0.875rem;
                color: #64748b;
                margin-top: 5px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .badge {
                padding: 6px 12px;
                border-radius: 9999px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
                display: inline-block;
            }
            .badge.pass { background-color: #dcfce7; color: #166534; }
            .badge.partial { background-color: #fef9c3; color: #854d0e; }
            .badge.fail { background-color: #fee2e2; color: #991b1b; }
            
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }
            th, td {
                text-align: left;
                padding: 12px 16px;
                border-bottom: 1px solid #e2e8f0;
            }
            th {
                background-color: #f8fafc;
                font-weight: 600;
                color: #475569;
            }
            .details-section {
                margin-top: 40px;
            }
            .details-section h2 {
                font-size: 1.5rem;
                color: #0f172a;
                margin-bottom: 20px;
            }
            .chunk-list {
                font-size: 0.875rem;
                background-color: #f8fafc;
                padding: 12px;
                border-radius: 6px;
                border: 1px solid #e2e8f0;
                margin-top: 8px;
            }
            .chunk-item {
                margin-bottom: 6px;
            }
            .chunk-item:last-child {
                margin-bottom: 0;
            }
            .chunk-item.missing {
                color: #ef4444;
                text-decoration: line-through;
            }
            .chunk-item.matched {
                color: #10b981;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Karthera Verification Report</h1>
            
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="value">{{ results.summary.overall_accuracy }}%</div>
                    <div class="label">Overall Accuracy</div>
                </div>
                <div class="summary-card">
                    <div class="value">{{ results.summary.passed }}</div>
                    <div class="label">Passed Sections</div>
                </div>
                <div class="summary-card">
                    <div class="value">{{ results.summary.partial }}</div>
                    <div class="label">Partial Sections</div>
                </div>
                <div class="summary-card">
                    <div class="value">{{ results.summary.failed }}</div>
                    <div class="label">Failed Sections</div>
                </div>
            </div>
            
            <div style="font-size: 0.875rem; color: #64748b; margin-bottom: 30px;">
                <strong>Total Evaluated Sections:</strong> {{ results.summary.total_sections }} &nbsp;&bull;&nbsp;
                <strong>Processing Time:</strong> {{ results.summary.processing_time_seconds }}s
            </div>
            
            <div class="details-section">
                <h2>Detailed Breakdown</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Section</th>
                            <th>Status</th>
                            <th>Similarity</th>
                            <th>Matched PDF Pages</th>
                            <th>Verification Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for sec in results.sections %}
                        <tr>
                            <td><strong>{{ sec.section }}</strong></td>
                            <td><span class="badge {{ sec.status.lower() }}">{{ sec.status }}</span></td>
                            <td>{{ sec.similarity }}%</td>
                            <td>{{ sec.pdf_pages|join(', ') if sec.pdf_pages else 'N/A' }}</td>
                            <td>
                                {% if sec.missing_text %}
                                <div class="chunk-list">
                                    <strong style="color: #ef4444;">Missing Chunks:</strong>
                                    {% for chunk in sec.missing_text %}
                                    <div class="chunk-item missing">&bull; {{ chunk }}</div>
                                    {% endfor %}
                                </div>
                                {% endif %}
                                {% if sec.matched_text and sec.status != 'PASS' %}
                                <div class="chunk-list">
                                    <strong style="color: #10b981;">Matched Chunks:</strong>
                                    {% for chunk in sec.matched_text %}
                                    <div class="chunk-item matched">&bull; {{ chunk }}</div>
                                    {% endfor %}
                                </div>
                                {% endif %}
                                {% if sec.status == 'PASS' %}
                                <span style="color: #10b981; font-size: 0.875rem;">All visible text successfully validated in PDF</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    template = Template(template_str)
    return template.render(results=results)
