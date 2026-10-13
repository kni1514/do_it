const bridgeVersion = "9";
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
    const candidates = [...document.querySelectorAll(
        'textarea, [contenteditable="true"][role="textbox"], [contenteditable="true"][data-testid*="prompt"], [contenteditable="true"]'
    )];
    return candidates.find((element) => {
        const style = getComputedStyle(element);
        return element.getClientRects().length > 0 && style.visibility !== "hidden" &&
            style.display !== "none" && !element.disabled && element.getAttribute("aria-disabled") !== "true";
    }) || null;
}

function findSendButton(composer) {
    const form = composer?.closest("form");
    const scope = form || composer?.parentElement || document;
    const candidates = [...scope.querySelectorAll(
        'button[data-testid*="send" i], button[aria-label*="send" i], button[type="submit"]'
    )];
    return candidates.find((button) => !button.disabled && button.getAttribute("aria-disabled") !== "true") || null;
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

async function waitForSendButton(composer) {
    for (let attempt = 0; attempt < 50; attempt++) {
        const send = findSendButton(composer);
        if (send && !send.disabled && send.getAttribute("aria-disabled") !== "true") {
            return send;
        }
        await sleep(200);
    }
    const buttons = [...(composer.closest("form") || composer.parentElement || document).querySelectorAll("button")]
        .map((button) => `${button.getAttribute("aria-label") || button.title || ""}/${button.dataset.testid || ""}/disabled=${button.disabled || button.getAttribute("aria-disabled") === "true"}`)
        .join(", ");
    throw new Error(
        `ChatGPT did not enable a send button after the prompt was entered ` +
        `(composer=${composer.tagName.toLowerCase()}, text=${(composer.innerText || composer.value || "").trim().length} chars, buttons=${buttons || "none"}).`
    );
}

const messageSelectors = globalThis.chatMessageSelectors;
let messageStrategy = { path: location.pathname, selector: null };

function syncMessageStrategy() {
    if (messageStrategy.path !== location.pathname) {
        messageStrategy = { path: location.pathname, selector: null };
    }
}

function messageElements(selector = messageStrategy.selector) {
    const elements = new Set();
    for (const candidate of selector ? [selector] : messageSelectors) {
        document.querySelectorAll(candidate).forEach((element) => elements.add(element));
    }
    return [...elements].sort((a, b) => {
        if (a === b) return 0;
        return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });
}

function findNewAssistantMessage(previous) {
    const selectors = messageStrategy.selector
        ? [messageStrategy.selector, ...messageSelectors.filter((selector) => selector !== messageStrategy.selector)]
        : messageSelectors;

    for (const selector of selectors) {
        const candidate = [...document.querySelectorAll(selector)]
            .filter((element) => !previous.has(element) && messageRole(element) === "assistant")
            .at(-1);
        if (candidate) {
            messageStrategy.selector = selector;
            return candidate;
        }
    }
    return null;
}

function messageRole(element) {
    if (element.matches('[data-markdown-text-style="assistant-message"]')) return "assistant";

    const directRole = element.getAttribute("data-message-author-role");
    if (directRole) return directRole;

    const messageRole = element.getAttribute("data-message-role");
    if (messageRole) return messageRole;

    if (element.matches("[data-assistant-markdown-root], [data-assistant-markdown]")) return "assistant";

    const unit = element.closest("[data-chatgpt-search-unit-key]");
    const roleNode = element.matches("[data-conversation-role]")
        ? element
        : element.querySelector("[data-conversation-role]") || unit?.querySelector("[data-conversation-role]");
    const semanticRole = roleNode?.getAttribute("data-conversation-role");
    if (semanticRole) return semanticRole;
    const unitKey = element.getAttribute("data-chatgpt-search-unit-key") || unit?.getAttribute("data-chatgpt-search-unit-key") || "";
    if (unitKey.endsWith(":assistant")) return "assistant";
    if (unitKey.endsWith(":user") || element.querySelector("[data-user-message-bubble]")) return "user";

    const contentSearchUnit = element.closest("[data-content-search-unit-key]") ||
        element.querySelector('[data-content-search-unit-key$=":user"], [data-content-search-unit-key$=":assistant"]');
    const contentSearchUnitKey = contentSearchUnit?.getAttribute("data-content-search-unit-key") || "";
    if (contentSearchUnitKey.endsWith(":assistant")) return "assistant";
    if (contentSearchUnitKey.endsWith(":user")) return "user";

    return null;
}

function messageText(element) {
    const clone = element.cloneNode(true);
    clone.querySelectorAll(
        "[data-conversation-role], [data-message-attribution], [data-message-actions], [data-message-intervention]"
    ).forEach((node) => node.remove());
    return (clone.innerText || element.innerText || "").trim();
}

function getMessages() {
    return messageElements().map(messageText);
}

function getLatestResponse() {
    const messages = getMessages();
    return messages[messages.length - 1] ?? null;
}

function assistantIsStreaming() {
    return [...document.querySelectorAll(
        'button[aria-label*="stop generating" i], button[aria-label="stop" i], [data-testid="stop-button"]'
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
        const curt = findNewAssistantMessage(previous);

        if (curt) {
            if (curt !== current) {
                current = curt;
                lastText = "";
                stableSince = 0;
            }

            const resp = messageText(curt);
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

                const stable = stableSince && Date.now() - stableSince >= 1200;
                if (stable && !assistantIsStreaming()) return resp;
            }
        }
        await sleep(200);
    }
    const selectorCounts = messageSelectors
        .map((selector) => `${selector}: ${document.querySelectorAll(selector).length}`)
        .join("; ");
    throw new Error(
        `Timed out because no supported selector identified the new assistant message. ` +
        `Selectors checked: ${selectorCounts}. ` +
        `To add support, open the assistant message in the browser, choose Inspect, ` +
        `copy the complete assistant message element (Copy > Copy outerHTML), and provide it ` +
        `to an AI assistant together with message-selectors.js. Ask it to add the matching selector ` +
        `to the array in message-selectors.js.`
    );
}

async function ask(item) {
    syncMessageStrategy();
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
    const send = await waitForSendButton(composer);

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
