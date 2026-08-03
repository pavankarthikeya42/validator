/**
 * background.js — Service Worker
 * Relays messages from the content script to the local validation server.
 * Content scripts cannot directly fetch cross-origin localhost in MV3,
 * so all API calls are proxied through here.
 */

const SERVER = "http://localhost:8765";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "API_CALL") {
    const { method, endpoint, body } = msg;

    const fetchOpts = {
      method: method || "GET",
      headers: { "Content-Type": "application/json" },
    };

    // Forward a JSON body for POST requests (e.g. the target page URL)
    if (body && method === "POST") {
      fetchOpts.body = JSON.stringify(body);
    }

    fetch(`${SERVER}${endpoint}`, fetchOpts)
      .then((r) => r.json())
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) =>
        sendResponse({
          ok: false,
          error: err.message.includes("Failed to fetch")
            ? "Server offline — double-click run_server.bat first"
            : err.message,
        })
      );

    return true; // keep the message channel open for the async response
  }
});
