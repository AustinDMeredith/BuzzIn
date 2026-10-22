// Ticks down any .countdown element. The server owns the real deadline; this is display only.
// The end time is taken from when the element first appears, so client/server clock skew doesn't matter.
setInterval(() => {
    for (const el of document.querySelectorAll(".countdown[data-seconds-left]")) {
        if (!el.dataset.endsAt) {
            el.dataset.endsAt = Date.now() + Number(el.dataset.secondsLeft) * 1000;
        }
        el.textContent = Math.max(0, Math.ceil((Number(el.dataset.endsAt) - Date.now()) / 1000));
    }
}, 250);
