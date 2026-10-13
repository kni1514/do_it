const bridgeUrl = "http://127.0.0.1:1514";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "local-chatgpt-bridge-request") return;

    (async () => {
        const response = await fetch(`${bridgeUrl}${message.path}`, {
            method: message.method || "GET",
            headers: message.body === undefined
                ? undefined
                : { "Content-Type": "application/json" },
            body: message.body === undefined
                ? undefined
                : JSON.stringify(message.body),
        });
        const raw = await response.text();
        let data = {};
        if (raw) {
            try {
                data = JSON.parse(raw);
            } catch {
                data = { text: raw };
            }
        }
        sendResponse({ status: response.status, data });
    })().catch((error) => sendResponse({ error: error.message }));

    return true;
});
