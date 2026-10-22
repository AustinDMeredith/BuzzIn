let socket;

document.addEventListener("keydown", (event) => {
    if (event.code !== "Space") {
        return;
    }
    event.preventDefault();
    // TODO: send a {"type": "buzz"} message over the htmx-ext-ws socket
    socket = evt.detail.socketWrapper; // { send, sendImmediately, queue }
    socket.send(JSON.stringify({ type: 'buzz' }));
});

