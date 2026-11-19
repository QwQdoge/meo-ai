const box = document.getElementById("enabled");
chrome.storage.local.get("enabled").then(({ enabled }) => { box.checked = enabled === true; });
box.addEventListener("change", () => chrome.storage.local.set({ enabled: box.checked }));
