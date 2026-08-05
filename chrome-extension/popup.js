document.addEventListener('DOMContentLoaded', () => {
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
  const customFilenameInput = document.getElementById('custom-filename');

  // Attempt to pre-populate custom filename from the page (.cmp-th-name and .cmp-th-sponsor)
  (async () => {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) {
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => {
            const nameEl = document.querySelector('.cmp-th-name');
            const sponsorEl = document.querySelector('.cmp-th-sponsor');
            return {
              name: nameEl ? nameEl.textContent.trim() : "",
              sponsor: sponsorEl ? sponsorEl.textContent.trim() : ""
            };
          }
        }, (results) => {
          if (results && results[0] && results[0].result) {
            const { name, sponsor } = results[0].result;
            if (name) {
              let defaultName = name;
              if (sponsor) {
                defaultName += `_${sponsor}`;
              }
              defaultName = defaultName.replace(/[^a-zA-Z0-9_-]/g, '_').replace(/__+/g, '_');
              if (customFilenameInput) {
                customFilenameInput.value = defaultName;
              }
            }
          }
        });
      }
    } catch (e) {
      console.warn("Could not pre-populate filename:", e);
    }
  })();

  let reportData = null; // Stores reports from backend
  let rawValidationResult = null; // Stores raw JSON validation response

  // Click handler for extracting DOM data directly
  btnExtract.addEventListener('click', async () => {
    try {
      showProgress("Extracting DOM data...", 50);
      const domData = await getDOMData();
      hideProgress();
      if (!domData || Object.keys(domData).length === 0) {
        alert("No structured data was found on the page to extract. Please make sure the section elements are present.");
        return;
      }
      const jsonString = JSON.stringify(domData, null, 2);
      let filename = "extracted_dom_data.json";
      if (customFilenameInput && customFilenameInput.value.trim()) {
        filename = customFilenameInput.value.trim();
        if (!filename.toLowerCase().endsWith('.json')) {
          filename += '.json';
        }
      }
      downloadFile(jsonString, "application/json", filename);
    } catch (error) {
      hideProgress();
      console.error(error);
      alert("Extraction failed:\n" + error.message);
    }
  });

  // 1. Validate Data Handler
  btnValidate.addEventListener('click', async () => {
    try {
      showProgress("Extracting webpage data...", 20);

      // Get DOM Data from active page
      const domDataResponse = await getDOMData();
      let fileToUpload = null;
      let pdfBase64 = null;
      let domData = domDataResponse;
      let pdfUrl = null;
      
      // Handle the case where content.js returns { uiData, pdfUrl, pdfBase64 }
      if (domDataResponse && domDataResponse.uiData) {
        domData = domDataResponse.uiData;
        pdfUrl = domDataResponse.pdfUrl;
        pdfBase64 = domDataResponse.pdfBase64;
      }

      if (!domData || Object.keys(domData).length === 0) {
        throw new Error("Could not extract any data from the active tab. Please make sure you are on the Karthera comparison page.");
      }

      // Process intercepted PDF
      if (pdfBase64) {
        showProgress("Processing intercepted PDF...", 40);
        try {
          const res = await fetch(pdfBase64);
          const pdfBlob = await res.blob();
          fileToUpload = new File([pdfBlob], "downloaded_document.pdf", { type: "application/pdf" });
        } catch (fetchErr) {
          console.error(fetchErr);
          throw new Error("Failed to process intercepted PDF.");
        }
      } else if (pdfUrl) {
        showProgress("Downloading PDF automatically...", 40);
        try {
          const pdfRes = await fetch(pdfUrl);
          if (!pdfRes.ok) throw new Error("Failed to fetch PDF from URL");
          const pdfBlob = await pdfRes.blob();
          fileToUpload = new File([pdfBlob], "downloaded_document.pdf", { type: "application/pdf" });
        } catch (fetchErr) {
          console.error(fetchErr);
          throw new Error("Failed to download PDF automatically.");
        }
      } else {
        alert("No PDF intercept found. Please click on the document link in the Karthera page before validating.");
        hideProgress();
        return;
      }

      showProgress("Uploading PDF and DOM data to FastAPI...", 55);

      // Send to FastAPI
      const formData = new FormData();
      formData.append("pdf", fileToUpload);
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

      // Try messaging content script first
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
        } else if (response && !response.success) {
          throw new Error("Content script error: " + response.error);
        }
      } catch (msgErr) {
        if (msgErr.message && msgErr.message.includes("Content script error")) {
          throw msgErr; // Re-throw actual content script runtime errors
        }
        console.warn("Message passing failed:", msgErr);
        throw new Error("The extension script is not loaded on this page. Please refresh the Karthera webpage (F5) and click Validate again.");
      }
      
      return null;
    } catch (err) {
      console.error(err);
      throw err;
    }
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
      if (sec.status === 'NULL') {
        badgeSpan.textContent = `NULL`;
      } else {
        badgeSpan.textContent = `${sec.status} (${sec.similarity}%)`;
      }

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
    let filename = "validation_report.json";
    if (customFilenameInput && customFilenameInput.value.trim()) {
      filename = customFilenameInput.value.trim();
      if (!filename.toLowerCase().endsWith('.json')) {
        filename += '.json';
      }
    }
    downloadFile(jsonString, "application/json", filename);
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
