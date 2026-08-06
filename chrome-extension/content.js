// Helper to pause execution
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// Extraction helper for Karthera comparison application
async function extractDOM() {
  const uiData = {};
  
  // The specific fields to extract from General Information (REMS)
  const requestedGeneralFields = [
    "Generic Name", "Brand / Program Name", "Sponsor", "Application #",
    "Therapeutic Area", "REMS Approved", "Last Updated"
  ];

  // Initialize all requested fields to empty string
  requestedGeneralFields.forEach(field => uiData[field] = "");

  // Automation: Click Expand All
  const expandBtn = document.querySelector('.cmp-expand-all, .expand-all-btn') || 
                    Array.from(document.querySelectorAll('button')).find(b => b.textContent.toLowerCase().includes('expand all') || b.textContent.toLowerCase().includes('collapse all'));
  if (expandBtn) {
    expandBtn.click();
    // Wait for all sections to become open
    for (let i = 0; i < 10; i++) {
      await sleep(500);
      const rows = document.querySelectorAll('.cmp-sec-row');
      let allOpen = true;
      rows.forEach(r => {
        if (!r.classList.contains('cmp-sec-open')) {
          allOpen = false;
        }
      });
      if (allOpen) break;
    }
  } else {
    // Fallback manual clicking if button not found
    const closedRows = document.querySelectorAll('.cmp-sec-row:not(.cmp-sec-open)');
    closedRows.forEach(r => r.click());
    if (closedRows.length > 0) await sleep(1000);
  }

  // 1. General Information (Dynamic)
  const firstTbody = document.querySelector('.cmp-table > tbody:not(.cmp-section-group)');
  if (firstTbody) {
    const rows = firstTbody.querySelectorAll('tr');
    rows.forEach(row => {
      const labelEl = row.querySelector('.cmp-td-label');
      const valueEl = row.querySelector('.cmp-td-value span') || row.querySelector('.cmp-td-value');
      if (labelEl && valueEl) {
        let labelText = labelEl.textContent.trim();
        // Normalize label aliases if needed
        if (labelText.toLowerCase() === 'generic') labelText = 'Generic Name';
        if (labelText.toLowerCase() === 'mah') labelText = 'Marketing Authorisation Holder';
        uiData[labelText] = valueEl.textContent.trim();
      }
    });
  }
  
  // 2. Extracted Sections (Dynamic for REMS)
  const sectionRows = document.querySelectorAll('.cmp-sec-row');
  sectionRows.forEach(secRow => {
    const sectionName = secRow.querySelector('.cmp-sec-text')?.textContent.trim();
    if (sectionName) {
        // Look ahead for the content container in case it's not the immediate next sibling
        let nextEl = secRow.nextElementSibling;
        while (nextEl && !nextEl.classList.contains('cmp-sec-content') && !nextEl.classList.contains('cmp-sec-row')) {
            nextEl = nextEl.nextElementSibling;
        }
        
        let content = "";
        if (nextEl && nextEl.classList.contains('cmp-sec-content')) {
          content = nextEl.querySelector('.cmp-content-inner')?.textContent.trim() || nextEl.textContent.trim();
        } else {
          // Fallback: sometimes content is nested inside the row itself in newer Karthera versions
          content = secRow.textContent.replace(sectionName, '').trim();
        }
        
        uiData[sectionName] = content ? content : "no data or null";
    }
  });

  // Extract PDF URL automatically
  let pdfUrl = null;
  let pdfBase64 = null;
  const pdfBtn = document.querySelector('.dl-pdf-btn, .cmp-th-pdf, a[href$=".pdf"]');
  if (pdfBtn) {
    if (pdfBtn.href) {
      pdfUrl = pdfBtn.href;
    } else {
      // It's a JS button without an href. We must intercept the download.
        pdfUrl = await new Promise((resolve) => {
          const listener = (event) => {
            if (event.data) {
              if (event.data.type === 'PDF_URL_INTERCEPTED') {
                window.removeEventListener('message', listener);
                pdfBase64 = event.data.base64;
                resolve("base64");
              } else if (event.data.type === 'PDF_URL_FOUND') {
                window.removeEventListener('message', listener);
                resolve(event.data.url);
              }
            }
          };
          window.addEventListener('message', listener);
          
          const script = document.createElement('script');
          script.src = chrome.runtime.getURL('inject.js');
          document.documentElement.appendChild(script);
          script.onload = () => {
            script.remove();
            pdfBtn.click();
          };
        
        setTimeout(() => {
          window.removeEventListener('message', listener);
          resolve(null);
        }, 5000);
      });
      
      // If we intercepted base64, return it in the payload
      if (pdfBase64) {
        return { uiData, pdfUrl: null, pdfBase64: pdfBase64 };
      }
    }
  }
  
  return { uiData, pdfUrl };
}

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "extractDOM") {
    extractDOM().then(data => {
      sendResponse({ success: true, data: data });
    }).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true; // Keep message channel open for async response
  }
});
