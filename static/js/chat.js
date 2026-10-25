// Every update swaps in a fresh #chat-log scrolled to the top; jump it to the newest message.
document.addEventListener("htmx:wsAfterMessage", () => {
    const log = document.getElementById("chat-log");
    if (log) {
        log.scrollTop = log.scrollHeight;
    }
});
