document.addEventListener('DOMContentLoaded', () => {
  const fileInput = document.getElementById('pdf-upload');
  const fileNameDisplay = document.getElementById('file-name');
  const btnValidate = document.getElementById('btn-validate');
  const progressContainer = document.getElementById('progress-container');
  const progressFill = document.getElementById('progress-fill');
  const progressText = document.getElementById('progress-text');
  
  const resultsArea = document.getElementById('results-area');
  const statAccuracy = document.getElementById('stat-accuracy');
  const statPassed = document.getElementById('stat-passed');
  const statPartial = document.getElementById('stat-partial');
  const statFailed = document.getElementById('stat-failed');
  const breakdownList = document.getElementById('breakdown-list');
  
  const btnExportHtml = document.getElementById('btn-export-html');
  const btnExportCsv = document.getElementById('btn-export-csv');
  const btnExportJson = document.getElementById('btn-export-json');
  const btnExtract = document.getElementById('btn-extract');

  let selectedFile = null;
  let reportData = null; // Stores reports from backend
  let rawValidationResult = null; // Stores raw JSON validation response

  // Click handler for extracting DOM data directly
  btnExtract.addEventListener('click', async () => {
    try {
      showProgress("Extracting DOM data...", 50);
      const domData = await getDOMData();
      hideProgress();
      if (!domData || (Object.keys(domData).length === 1 && Object.keys(domData["General Information"] || {}).length === 0)) {
        alert("No structured data was found on the page to extract. Please make sure the section elements are present.");
        return;
      }
      const jsonString = JSON.stringify(domData, null, 2);
      downloadFile(jsonString, "application/json", "extracted_dom_data.json");
    } catch (error) {
      hideProgress();
      console.error(error);
      alert("Extraction failed:\n" + error.message);
    }
  });

  // 1. File Upload Handler
  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      selectedFile = file;
      fileNameDisplay.textContent = file.name;
      btnValidate.disabled = false;
    }
  });

  // 2. Validate Data Handler
  btnValidate.addEventListener('click', async () => {
    if (!selectedFile) {
      alert("Please upload a PDF first.");
      return;
    }

    try {
      showProgress("Extracting webpage data...", 20);
      
      // Get DOM Data from active page
      const domData = await getDOMData();
      if (!domData || Object.keys(domData).length === 0) {
        throw new Error("Could not extract any data from the active tab. Please make sure you are on the Karthera comparison page.");
      }

      showProgress("Uploading PDF and DOM data to FastAPI...", 55);

      // Send to FastAPI
      const formData = new FormData();
      formData.append("pdf", selectedFile);
      formData.append("dom_data", JSON.stringify(domData));

      const response = await fetch("http://localhost:8000/validate", {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        const errorDetail = await response.json();
        throw new Error(errorDetail.detail || "Validation request failed");
      }

      showProgress("Generating reports...", 90);

      const result = await response.json();
      rawValidationResult = result;
      hideProgress();
      displayResults(result);

    } catch (error) {
      hideProgress();
      console.error(error);
      alert("Validation failed:\n" + error.message);
    }
  });

  // 3. Helper: DOM Extractor via Scripting / Messages
  async function getDOMData() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) {
        throw new Error("No active tab found. Please make sure your window is focused on the page.");
      }

      // Try messaging content script first (much safer if page has CSP or activeTab sandbox boundaries)
      try {
        const response = await new Promise((resolve, reject) => {
          chrome.tabs.sendMessage(tab.id, { action: "extractDOM" }, (res) => {
            if (chrome.runtime.lastError) {
              reject(chrome.runtime.lastError);
            } else {
              resolve(res);
            }
          });
        });
        if (response && response.success && response.data) {
          return response.data;
        }
      } catch (msgErr) {
        console.warn("Message passing failed, falling back to scripting.executeScript:", msgErr);
      }

      // Fallback: Try scripting API directly
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          const uiData = {};
          
          const requestedGeneralFields = [
            "Generic Name", "Review Type", "Priority / Standard", "Application #",
            "Division / Office", "Therapeutic Areas", "Dosage Form", "Dosing Regimen",
            "Pharmacologic Class", "Approval Date", "Submit Date", "Received Date",
            "Review Completion", "Review Name"
          ];

          const requestedSections = [
            "Indication", "Executive / Product / Summary Review", "Background / Therapeutic Context",
            "Regulatory Background / History / Considerations", "CMC / Product Quality",
            "Nonclinical Pharmacology / Toxicology", "Clinical Pharmacology", "Clinical Filing Checklist",
            "Clinical Data and Review Strategy", "Efficacy", "Safety", "Risk Assessments / Risk Evaluation and Mitigation",
            "Postmarketing Requirements", "Labeling Recommendations", "Advisory Committee Review",
            "Ethics and Good Clinical Practices", "Other Significant Issues Identified", "Appendices"
          ];

          // Initialize all requested general fields to empty string
          requestedGeneralFields.forEach(field => {
            uiData[field] = "";
          });

          // Initialize all requested sections to empty string
          requestedSections.forEach(section => {
            uiData[section] = "";
          });

          const firstTbody = document.querySelector('.cmp-table > tbody:not(.cmp-section-group)');
          if (firstTbody) {
            const rows = firstTbody.querySelectorAll('tr');
            rows.forEach(row => {
              const labelEl = row.querySelector('.cmp-td-label');
              const valueEl = row.querySelector('.cmp-td-value span') || row.querySelector('.cmp-td-value');
              if (labelEl && valueEl) {
                const labelText = labelEl.textContent.trim();
                const normalizedLabel = labelText.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
                const matchedField = requestedGeneralFields.find(f => f.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() === normalizedLabel);
                if (matchedField) {
                  uiData[matchedField] = valueEl.textContent.trim();
                }
              }
            });
          }
          
          const sectionRows = document.querySelectorAll('.cmp-sec-row');
          sectionRows.forEach(secRow => {
            const sectionName = secRow.querySelector('.cmp-sec-text')?.textContent.trim();
            if (sectionName) {
              const normalizedSec = sectionName.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
              const matchedSec = requestedSections.find(s => s.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() === normalizedSec);
              if (matchedSec) {
                let nextEl = secRow.nextElementSibling;
                if (nextEl && nextEl.classList.contains('cmp-sec-content')) {
                  const content = nextEl.querySelector('.cmp-content-inner')?.textContent.trim() || nextEl.textContent.trim();
                  if (content) {
                    uiData[matchedSec] = content;
                  }
                }
              }
            }
          });
          
          return uiData;
        }
      });

      if (results && results[0] && results[0].result) {
        return results[0].result;
      }
    } catch (e) {
      console.error("DOM Extraction failed:", e);
      throw e;
    }
    return null;
  }

  // 4. UI Helper Functions
  function showProgress(text, percent) {
    progressContainer.classList.remove('hidden');
    progressFill.style.width = `${percent}%`;
    progressText.textContent = text;
    resultsArea.classList.add('hidden');
  }

  function hideProgress() {
    progressContainer.classList.add('hidden');
  }

  function displayResults(data) {
    resultsArea.classList.remove('hidden');
    
    // Summary metrics
    statAccuracy.textContent = `${data.summary.overall_accuracy}%`;
    statPassed.textContent = data.summary.passed;
    statPartial.textContent = data.summary.partial;
    statFailed.textContent = data.summary.failed;
    
    // Cache reports
    reportData = data.reports;

    // Populate breakdown
    breakdownList.innerHTML = '';
    data.sections.forEach(sec => {
      const item = document.createElement('div');
      item.className = 'breakdown-item';

      const nameDiv = document.createElement('div');
      nameDiv.className = 'section-name';
      nameDiv.textContent = sec.section;
      nameDiv.title = sec.section;

      const badgeSpan = document.createElement('span');
      badgeSpan.className = `badge ${sec.status.toLowerCase()}`;
      badgeSpan.textContent = `${sec.status} (${sec.similarity}%)`;

      item.appendChild(nameDiv);
      item.appendChild(badgeSpan);
      breakdownList.appendChild(item);
    });
  }

  // 5. Download Triggers
  btnExportHtml.addEventListener('click', () => {
    if (!reportData || !reportData.html) {
      alert("No HTML report content available.");
      return;
    }
    downloadFile(reportData.html, "text/html", "validation_report.html");
  });

  btnExportCsv.addEventListener('click', () => {
    if (!reportData || !reportData.csv) {
      alert("No CSV report content available.");
      return;
    }
    downloadFile(reportData.csv, "text/csv", "validation_report.csv");
  });

  btnExportJson.addEventListener('click', () => {
    if (!rawValidationResult) {
      alert("No validation result JSON available. Please run a validation first.");
      return;
    }
    const jsonString = JSON.stringify(rawValidationResult, null, 2);
    downloadFile(jsonString, "application/json", "validation_report.json");
  });

  function downloadFile(content, mimeType, filename) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
});
