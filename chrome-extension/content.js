// Extraction helper for Karthera comparison application
function extractDOM() {
  const uiData = {};
  
  // The specific fields to extract from General Information
  const requestedGeneralFields = [
    "Generic Name", "Review Type", "Priority / Standard", "Application #",
    "Division / Office", "Therapeutic Areas", "Dosage Form", "Dosing Regimen",
    "Pharmacologic Class", "Approval Date", "Submit Date", "Received Date",
    "Review Completion", "Review Name"
  ];

  // The specific sections to extract
  const requestedSections = [
    "Indication", "Executive / Product / Summary Review", "Background / Therapeutic Context",
    "Regulatory Background / History / Considerations", "CMC / Product Quality",
    "Nonclinical Pharmacology / Toxicology", "Clinical Pharmacology", "Clinical Filing Checklist",
    "Clinical Data and Review Strategy", "Efficacy", "Safety", "Risk Assessments / Risk Evaluation and Mitigation",
    "Postmarketing Requirements", "Labeling Recommendations", "Advisory Committee Review",
    "Ethics and Good Clinical Practices", "Other Significant Issues Identified", "Appendices"
  ];
  
  // Initialize all requested general fields to empty string in the flat object
  requestedGeneralFields.forEach(field => {
    uiData[field] = "";
  });

  // Initialize all requested sections to empty string in the flat object
  requestedSections.forEach(section => {
    uiData[section] = "";
  });

  // 1. General Information
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
  
  // 2. Extracted Sections (only those present/visible in the DOM)
  const sectionRows = document.querySelectorAll('.cmp-sec-row');
  sectionRows.forEach(secRow => {
    const sectionName = secRow.querySelector('.cmp-sec-text')?.textContent.trim();
    if (sectionName) {
      const normalizedSec = sectionName.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
      const matchedSec = requestedSections.find(s => s.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() === normalizedSec);
      if (matchedSec) {
        // Try finding next element sibling which holds the content
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

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "extractDOM") {
    try {
      const data = extractDOM();
      sendResponse({ success: true, data: data });
    } catch (err) {
      sendResponse({ success: false, error: err.message });
    }
  }
  return true; // Keep message channel open for async response
});
