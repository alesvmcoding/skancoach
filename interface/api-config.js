// Set this to the public backend URL when the interface is hosted on GitHub Pages.
// Example: window.SKAN_API_BASE = "https://skan-hunt-api.onrender.com";
window.SKAN_API_BASE = window.SKAN_API_BASE || "";
window.skanApiUrl = (path) => `${window.SKAN_API_BASE.replace(/\/$/, "")}${path}`;
