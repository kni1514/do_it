const bridgeVersion = "8";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
console.info(`[Local ChatGPT Bridge v${bridgeVersion}] loaded`);

function bridgeRequest(path, method = "GET", body) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
            {
                type: "local-chatgpt-bridge-request",
                path,
                method,
                body,
            },
            (response) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                } else if (response?.error) {
                    reject(new Error(response.error));
                } else {
                    resolve(response);
                }
            }
        );
    });
}

async function postResponse(id, response) {
    const result = await bridgeRequest("/response", "POST", { id, response });
    if (result.status < 200 || result.status >= 300) {
        throw new Error(`Bridge response failed: HTTP ${result.status}`);
    }
    console.info(`[Local ChatGPT Bridge] delivered response (${response.length} chars)`);
}

async function userInput() {
    while (true) {
        const result = await bridgeRequest("/query");
        if (result.status === 200) return result.data;
        await sleep(500);
    }
}

function findComposer() {
    return document.querySelector("textarea") || document.querySelector(
        '[contenteditable="true"][role="textbox"], [contenteditable="true"][data-testid*="prompt"], [contenteditable="true"]'
    );
}

function findSendButton() {
    return document.querySelector('button[aria-label="Send message"]') ||
        document.querySelector('button[data-testid="send-button"]') ||
        document.querySelector('button[aria-label="Send prompt"]') ||
        document.querySelector('button[aria-label^="Send "]') ||
        document.querySelector('form button[type="submit"]');
}

async function waitForComposer() {
    for (let attempt = 0; attempt < 30; attempt++) {
        const composer = findComposer();
        if (composer) return composer;
        await sleep(500);
    }
    const buttons = [...document.querySelectorAll("button")]
        .slice(0, 12)
        .map((button) => `${button.getAttribute("aria-label") || ""}/${button.dataset.testid || ""}/${(button.innerText || "").trim().slice(0, 24)}`)
        .join(", ");
    throw new Error(
        `Composer/send button not found at ${location.href}; ` +
        `textareas=${document.querySelectorAll("textarea").length}, ` +
        `editables=${document.querySelectorAll('[contenteditable="true"]').length}, ` +
        `buttons=${buttons || "none"}. Open a normal ChatGPT conversation.`
    );
}

async function waitForSendButton() {
    for (let attempt = 0; attempt < 30; attempt++) {
        const send = findSendButton();
        if (send && !send.disabled && send.getAttribute("aria-disabled") !== "true") {
            return send;
        }
        await sleep(200);
    }
    throw new Error("ChatGPT did not enable a send button after the prompt was entered.");
}

function messageElements() {
    return [...document.querySelectorAll("[data-dil-source-message-id]")];
}

function getMessages() {
    return messageElements().map((element) => element.innerText || "");
}

function getLatestResponse() {
    const messages = getMessages();
    return messages[messages.length - 1] ?? null;
}

function assistantIsStreaming() {
    return [...document.querySelectorAll(
        'button[aria-label*="Stop"], [data-testid*="stop-button"]'
    )].some((button) => {
        const style = getComputedStyle(button);
        return button.getClientRects().length > 0 &&
            style.visibility !== "hidden" &&
            style.display !== "none" &&
            button.getAttribute("aria-hidden") !== "true";
    });
}

async function waitForAssistantResponse(previous, query) {
    const deadline = Date.now() + 10 * 60 * 1000;
    let current = null;
    let lastText = "";
    let stableSince = 0;

    while (Date.now() < deadline) {
        const msgs = messageElements();
        const curt = msgs.filter((element) => !previous.has(element)).at(-1);

        if (curt) {
            if (curt !== current) {
                current = curt;
                lastText = "";
                stableSince = 0;
            }

            const resp = (curt.innerText || "").trim();
            if (resp === query.trim()) {
                await sleep(200);
                continue;
            }
            if (resp) {
                if (!lastText) {
                    console.info("[Local ChatGPT Bridge] assistant response detected; waiting for completion");
                }
                if (resp !== lastText) {
                    lastText = resp;
                    stableSince = Date.now();
                }

                const complete = Boolean(curt.closest("[data-message-complete]"));
                const stable = stableSince && Date.now() - stableSince >= 1200;
                if (complete || (stable && !assistantIsStreaming())) return resp;
            }
        }
        await sleep(200);
    }
    throw new Error(
        `Timed out waiting for a new message; matched ${messageElements().length} message element(s).`
    );
}

async function ask(item) {
    const query = item.query;
    const composer = await waitForComposer();

    const previous = new Set(messageElements());
    if (composer instanceof HTMLTextAreaElement) {
        const setter = Object.getOwnPropertyDescriptor(
            HTMLTextAreaElement.prototype,
            "value"
        ).set;
        setter.call(composer, query);
    } else {
        composer.focus();
        composer.replaceChildren();
        const range = document.createRange();
        range.selectNodeContents(composer);
        range.collapse(false);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        const inserted = document.execCommand("insertText", false, query);
        if (!inserted || !(composer.innerText || "").trim()) {
            composer.textContent = query;
        }
    }
    composer.dispatchEvent(new InputEvent("input", {
        bubbles: true,
        inputType: "insertText",
        data: query,
    }));
    const send = await waitForSendButton();

    const responsePromise = waitForAssistantResponse(previous, query);
    send.click();
    const response = await responsePromise;
    await postResponse(item.id, response);
}

async function runBridge() {
    let connectionErrorShown = false;
    while (true) {
        try {
            const item = await userInput();
            connectionErrorShown = false;
            try {
                await ask(item);
            } catch (error) {
                console.error("ChatGPT bridge request failed:", error);
                await postResponse(item.id, `Error: ${error.message}`);
            }
        } catch (error) {
            if (!connectionErrorShown) {
                console.error(
                    "Local ChatGPT bridge connection failed. Start the bridge by running python do_it.py:",
                    error
                );
                connectionErrorShown = true;
            }
            await sleep(1500);
        }
    }
}

if (window.top === window) {
    runBridge();
} else {
    console.info("[Local ChatGPT Bridge] skipped nested frame");
}
