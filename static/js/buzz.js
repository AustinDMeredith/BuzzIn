// Spacebar buzzes in by clicking the buzz button, which sends {"type": "buzz"}
// through htmx-ext-ws. A disabled (or missing) button means buzzing is closed.
document.addEventListener("keydown", (event) => {
    if (event.code !== "Space" || event.repeat) {
        return;
    }
    // let people type spaces in the name and chat inputs
    if (event.target.matches("input, textarea")) {
        return;
    }
    event.preventDefault();
    document.getElementById("buzz-button")?.click();
});
