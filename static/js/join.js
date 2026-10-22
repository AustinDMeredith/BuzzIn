let socket;

document.body.addEventListener('htmx:wsOpen', (evt) => {
    socket = evt.detail.socketWrapper;
});

function join() {
    const name = document.getElementById("player").value;
    socket.send(JSON.stringify({ type: 'join', player: name }));
}
