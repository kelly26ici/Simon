/*!
 * Simon agent Web Chat Widget
 * Embeddable chat bubble / sidebar for external websites.
 *
 * Usage (drop on the host page BEFORE this script):
 *
 *   <script>
 *     window.SimonChatConfig = {
 *       apiBase: "https://samantha-nrev.onrender.com", // my Simon agent API URL
 *       apiKey: "YOUR-SAMANTHA-WEB-API-KEY",           // shared secret from Simon
 *       title: "Simon agent",                             // optional
 *       brandColor: "#0d6efd",                         // optional
 *       position: "right",                             // "left" | "right" (default right)
 *       welcomeMessage: "Hi! I'm Simon agent, your Kenya real-estate assistant 👋"
 *     };
 *   </script>
 *   <script src="https://samantha-nrev.onrender.com/static/chat-widget.js"></script>
 *
 * No external dependencies. All state (session id) is kept in localStorage
 * so the conversation survives page reloads.
 */

(function () {
    "use strict";

    var CFG = (typeof window !== "undefined" && window.SimonChatConfig) || {};
    var API_BASE = (CFG.apiBase || "").replace(/\/+$/, "");
    var API_KEY = CFG.apiKey || "";
    var TITLE = CFG.title || "Simon agent";
    var BRAND = CFG.brandColor || "#0d6efd";
    var POSITION = CFG.position === "left" ? "left" : "right";
    var WELCOME = CFG.welcomeMessage ||
        "Hi! I'm " + TITLE + ", your Kenya real-estate assistant \uD83D\uDE4B\u200D\u2642\uFE0F. How can I help you find a home today?";

    if (!API_BASE) {
        if (typeof console !== "undefined" && console.warn) {
            console.warn("[Simon agent] apiBase is not configured. Set window.SimonChatConfig.apiBase before loading the widget.");
        }
        return;
    }

    // ── session id (persisted) ──────────────────────────────────────────
    var STORAGE_KEY = "simon_session_id";
    function getSessionId() {
        try {
            var sid = localStorage.getItem(STORAGE_KEY);
            if (!sid) {
                sid = "web-" + Math.random().toString(36).slice(2, 12) +
                      Math.random().toString(36).slice(2, 12);
                localStorage.setItem(STORAGE_KEY, sid);
            }
            return sid;
        } catch (e) {
            return "web-" + Math.random().toString(36).slice(2, 12);
        }
    }

    // ── styles ──────────────────────────────────────────────────────────
    var css = [
        "#simon-widget-root{display:inline-block;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;z-index:2147483647}",
        "#simon-widget-root .s-chat-btn{",
        "position:fixed;bottom:20px;" + POSITION + ":20px;width:56px;height:56px;",
        "border-radius:50%;border:none;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.18);",
        "background:" + BRAND + ";color:#fff;font-size:26px;display:flex;align-items:center;justify-content:center;",
        "transition:transform .1s ease,-webkit-transform .1s ease}",
        "#simon-widget-root .s-chat-btn:hover{transform:scale(1.06)}",
        "#simon-widget-root .s-chat-panel{",
        "position:fixed;bottom:90px;" + POSITION + ":20px;width:340px;max-width:calc(100vw - 40px);",
        "background:#fff;border-radius:14px;box-shadow:0 8px 28px rgba(0,0,0,.18);",
        "display:none;flex-direction:column;border:1px solid #e6e6e6;overflow:hidden}",
        "#simon-widget-root .s-chat-open .s-chat-panel{display:flex}",
        "#simon-widget-root .s-chat-header{",
        "background:" + BRAND + ";color:#fff;padding:12px 16px;font-size:16px;font-weight:600;display:flex;align-items:center;justify-content:space-between}",
        "#simon-widget-root .s-chat-close{cursor:pointer;font-size:18px;line-height:1}",
        "#simon-widget-root .s-chat-body{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px;min-height:120px}",
        "#simon-widget-root .s-msg{padding:9px 12px;border-radius:12px;font-size:14px;line-height:1.45;max-width:85%;word-break:break-word}",
        "#simon-widget-root .s-msg.user{align-self:flex-end;background:#f1f1f1;border-bottom-right-radius:4px}",
        "#simon-widget-root .s-msg.bot{background:#f5f7ff;border-bottom-left-radius:4px}",
        "#simon-widget-root .s-typing{background:#f5f7ff;border-radius:12px;padding:9px 12px;font-size:13px;color:#666}",
        "#simon-widget-root .s-chat-form{display:flex;gap:8px;padding:10px;border-top:1px solid #eee;background:#fafafa}",
        "#simon-widget-root .s-chat-form textarea{flex:1;border:1px solid #ddd;border-radius:10px;padding:8px 10px;font-size:14px;resize:none;outline:none;min-height:38px;max-height:120px}",
        "#simon-widget-root .s-send{cursor:pointer;background:" + BRAND + ";color:#fff;border:none;border-radius:10px;width:38px;height:38px;font-size:16px;display:flex;align-items:center;justify-content:center;transition:opacity .1s}",
        "#simon-widget-root .s-send:disabled{opacity:.6;cursor:wait}"
    ].join("");

    var style = document.createElement("style");
    style.textContent = css;
    document.documentElement.head.appendChild(style);

    // ── DOM ─────────────────────────────────────────────────────────────
    var root = document.createElement("div");
    root.id = "simon-widget-root";
    root.innerHTML =
        '<button class="s-chat-btn" id="simon-toggle" aria-label="Open ' + TITLE + ' chat" title="' + TITLE + '">' +
        "&#128465;</button>" +
        '<div class="s-chat-panel" id="simon-panel">' +
        "<div class='s-chat-header'>" +
        "<span>" + TITLE + "</span>" +
        "<span class='s-chat-close' id='simon-close'>&#10005;</span>" +
        "</div>" +
        "<div class='s-chat-body' id='simon-body'></div>" +
        "<div class='s-typing' id='simon-typing' style='display:none'>Simon agent is typing…</div>" +
        "<div class='s-chat-form'>" +
        "<textarea id='simon-input' placeholder='Type a message…' rows='1' spellcheck='true'></textarea>" +
        "<button class='s-send' id='simon-send' aria-label='Send'>&#8593;</button>" +
        "</div>" +
        "</div>";
    document.body.appendChild(root);

    var toggleBtn = root.querySelector("#simon-toggle");
    var panel = root.querySelector("#simon-panel");
    var body = root.querySelector("#simon-body");
    var typing = root.querySelector("#simon-typing");
    var input = root.querySelector("#simon-input");
    var sendBtn = root.querySelector("#simon-send");
    var closeBtn = root.querySelector("#simon-close");

    var isOpen = false;
    function openPanel() {
        isOpen = true;
        panel.classList.add("s-chat-open");
        toggleBtn.style.display = "none";
    }
    function closePanel() {
        isOpen = false;
        panel.classList.remove("s-chat-open");
        toggleBtn.style.display = "";
    }

    toggleBtn.addEventListener("click", openPanel);
    closeBtn.addEventListener("click", closePanel);

    // ── messages ───────────────────────────────────────────────────────
    function addMessage(text, cls) {
        var el = document.createElement("div");
        el.className = "s-msg " + cls;
        el.textContent = text;
        body.appendChild(el);
        body.scrollTop = body.scrollHeight;
    }

    function showTyping(v) {
        typing.style.display = v ? "block" : "none";
        body.scrollTop = body.scrollHeight;
    }

    function resetInput() {
        input.value = "";
        input.disabled = false;
        sendBtn.disabled = false;
    }

    // ── send ───────────────────────────────────────────────────────────
    function sendMessage() {
        var text = (input.value || "").trim();
        if (!text) return;
        input.value = "";
        input.disabled = true;
        sendBtn.disabled = true;
        addMessage(text, "user");
        showTyping(true);

        var headers = { "Content-Type": "application/json" };
        if (API_KEY) headers["X-API-Key"] = API_KEY;

        fetch(API_BASE + "/api/chat/", {
            method: "POST",
            headers: headers,
            body: JSON.stringify({ session_id: getSessionId(), message: text })
        })
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (data) {
                showTyping(false);
                var reply = (data && data.reply) || "Sorry, I didn't get a response. Please try again.";
                addMessage(reply, "bot");
                // remember returned session id
                if (data && data.session_id) {
                    try { localStorage.setItem(STORAGE_KEY, data.session_id); } catch (e) {}
                }
            })
            .catch(function (err) {
                showTyping(false);
                addMessage("We couldn't reach Simon agent right now. Please try again in a moment.", "bot");
                if (typeof console !== "undefined" && console.error) {
                    console.error("[Simon agent] chat request failed:", err);
                }
            })
            .finally(resetInput);
    }

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-open on first load with a welcome message (only once per visitor)
    (function autoOpen() {
        var opened = false;
        try { opened = localStorage.getItem("simon_opened") === "true"; } catch (e) {}
        if (!opened) {
            openPanel();
            addMessage(WELCOME, "bot");
            try { localStorage.setItem("simon_opened", "true"); } catch (e) {}
        }
    })();

    // Expose a tiny public API for host-page control
    window.SimonChat = {
        open: openPanel,
        close: closePanel,
        sendMessage: sendMessage,
        getSessionId: getSessionId,
        reloadConfig: function () {
            var c = (window.SimonChatConfig || {});
            if (c.brandColor) { BRAND = c.brandColor; }
        }
    };
})();
