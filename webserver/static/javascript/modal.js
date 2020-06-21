function showModal(func) {
    var modal = document.getElementById('modal-container');
    modal.style.display = "block";
    var confirm = document.getElementById('modal-confirm');
    confirm.onclick = func;
}

function hideModal() {
    var modal = document.getElementById('modal-container');
    modal.style.display = "none";
    var confirm = document.getElementById('modal-confirm');
    confirm.removeAttribute("onclick");
}

// Hide pop-up when user clicks outside of modal
window.onclick = function(event) {
    if (event.target == document.getElementById("modal-container")) {
        hideModal();
    }
}