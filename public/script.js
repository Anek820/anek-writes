// Anek Writes - the code that runs in the browser.
// Steps: read the topic -> ask our server -> show the writing -> save it to history.

var form = document.getElementById("form");
var topicBox = document.getElementById("topic");
var goButton = document.getElementById("go");
var output = document.getElementById("output");
var list = document.getElementById("list");
var emptyNote = document.getElementById("empty");
var clearButton = document.getElementById("clear");

var HISTORY_KEY = "anek-writes-history";
var savedPieces = loadHistory();

// Little messages shown while the research happens
var waitingMessages = [
  "Reading the internet so you don't have to...",
  "Checking the facts twice...",
  "Hunting for a good opening line...",
  "Finding a comparison that actually works...",
  "Almost there..."
];
var timer = null;

// ---------- history (saved in this browser) ----------

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch (e) {
    return [];
  }
}

function saveHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(savedPieces));
  } catch (e) {
    // If saving is blocked, the site still works, it just won't remember.
  }
}

function renderHistory() {
  list.textContent = "";
  emptyNote.classList.toggle("hidden", savedPieces.length > 0);
  clearButton.classList.toggle("hidden", savedPieces.length === 0);

  savedPieces.forEach(function (item, index) {
    var li = document.createElement("li");
    var btn = document.createElement("button");
    btn.type = "button";

    var title = document.createElement("span");
    title.className = "t";
    title.textContent = item.title;

    var date = document.createElement("span");
    date.className = "d";
    date.textContent = item.date;

    btn.appendChild(title);
    btn.appendChild(date);
    btn.addEventListener("click", function () {
      showPiece(item);
      output.scrollIntoView({ behavior: "smooth" });
    });

    li.appendChild(btn);
    list.appendChild(li);
  });
}

// ---------- showing things ----------

function showStatus() {
  var i = 0;
  output.textContent = "";
  var box = document.createElement("div");
  box.className = "status";
  box.textContent = waitingMessages[0];
  output.appendChild(box);

  timer = setInterval(function () {
    i = (i + 1) % waitingMessages.length;
    box.textContent = waitingMessages[i];
  }, 3000);
}

function stopStatus() {
  clearInterval(timer);
}

function showError(message) {
  output.textContent = "";
  var box = document.createElement("div");
  box.className = "error";
  box.textContent = message;
  output.appendChild(box);
}

function showPiece(item) {
  output.textContent = "";
  var piece = document.createElement("article");
  piece.className = "piece";

  var words = item.text.split(/\s+/).length;
  var meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = item.length + " · " + words + " words";
  piece.appendChild(meta);

  var h2 = document.createElement("h2");
  h2.textContent = item.title;
  piece.appendChild(h2);

  // Be honest when the web wasn't searched
  if (item.searched === false) {
    var note = document.createElement("p");
    note.className = "note";
    note.textContent = "Written from Gemini's own knowledge. Live web search isn't available on this Google key, so double-check any numbers or dates.";
    piece.appendChild(note);
  }

  // Blank line = new paragraph. A line starting with "## " is a heading.
  item.text.split(/\n\s*\n/).forEach(function (block) {
    block = block.trim();
    if (!block) return;
    var tag = "p";
    if (block.indexOf("## ") === 0) {
      tag = "h3";
      block = block.slice(3);
    }
    var el = document.createElement(tag);
    el.textContent = block;
    piece.appendChild(el);
  });

  if (item.sources && item.sources.length > 0) {
    var box = document.createElement("div");
    box.className = "sources";
    var head = document.createElement("h4");
    head.textContent = "Where this came from";
    var ol = document.createElement("ol");
    item.sources.forEach(function (s) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = s.title;
      li.appendChild(a);
      ol.appendChild(li);
    });
    box.appendChild(head);
    box.appendChild(ol);
    piece.appendChild(box);
  }

  output.appendChild(piece);
}

// ---------- asking for a topic ----------

form.addEventListener("submit", function (event) {
  event.preventDefault();
  var topic = topicBox.value.trim();
  if (!topic) return;
  var length = form.elements.size.value;

  goButton.disabled = true;
  showStatus();
  output.scrollIntoView({ behavior: "smooth" });

  fetch("/api/write", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic: topic, length: length })
  })
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      stopStatus();
      if (data.error) {
        showError(data.error);
        return;
      }
      var item = {
        title: data.title,
        text: data.text,
        sources: data.sources,
        length: length,
        searched: data.searched,
        topic: topic,
        date: new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short" })
      };
      showPiece(item);
      savedPieces.unshift(item);
      savedPieces = savedPieces.slice(0, 30);
      saveHistory();
      renderHistory();
    })
    .catch(function () {
      stopStatus();
      showError("Couldn't reach the server. Is the black start.bat window still open?");
    })
    .then(function () {
      goButton.disabled = false;
    });
});

// Example topic buttons fill the box
document.querySelectorAll(".chip").forEach(function (chip) {
  chip.addEventListener("click", function () {
    topicBox.value = chip.textContent;
    topicBox.focus();
  });
});

clearButton.addEventListener("click", function () {
  if (confirm("Delete all your saved topics?")) {
    savedPieces = [];
    saveHistory();
    renderHistory();
  }
});

renderHistory();
