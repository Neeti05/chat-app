var socket = io();
var myId = null;

// store your socket id
socket.on("connect", function() {
    myId = socket.id;
});

function sendMessage() {
    let input = document.getElementById("messageInput");
    let message = input.value.trim();

    if (message === "") return;

    socket.send(message);
    input.value = "";
}

socket.on('message', function(data) {
    let messages = document.getElementById("messages");

    let div = document.createElement("div");
    let p = document.createElement("p");

    p.innerText = data.msg;

    // decide side
    if (data.id === myId) {
        div.classList.add("my-message");
    } else {
        div.classList.add("other-message");
    }

    div.appendChild(p);
    messages.appendChild(div);

    // auto scroll
    messages.scrollTop = messages.scrollHeight;
});