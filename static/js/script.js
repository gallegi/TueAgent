const sidebar = document.getElementById("sidebar");
const dragHandle = document.getElementById("drag-handle");

const chatContainer = document.querySelector(".chat-container");
const dragHandleChat = document.getElementById("drag-handle-chat");

let isDragging = false;
let activeHandle = null; // Track which handle is active

// Generic drag start function for both handles
function startDrag(handle) {
    isDragging = true;
    activeHandle = handle;
    document.addEventListener("mousemove", handleDrag);
    document.addEventListener("mouseup", stopDrag);
}

// Add event listeners for both drag handles
dragHandle.addEventListener("mousedown", () => startDrag(dragHandle));
dragHandleChat.addEventListener("mousedown", () => startDrag(dragHandleChat));

// Handle the dragging event
function handleDrag(e) {
    console.log("Dragging...");
    if (!isDragging) return;

    if (activeHandle === dragHandle) {
        // Sidebar resizing
        const newWidth = e.clientX;
        if (newWidth >= 150 && newWidth <= 500) { // Restrict sidebar width
            sidebar.style.width = `${newWidth}px`;
            dragHandle.style.left = `${newWidth}px`;
            document.querySelector(".content").style.marginLeft = `${newWidth + 5}px`;
        }
        
    } 
    else if (activeHandle === dragHandleChat) {
        // Chat container resizing
        const contentWidth = document.querySelector(".chat-container").offsetWidth;
        const newChatWidth = e.clientX - sidebar.offsetWidth - 10; // Adjust based on sidebar width and gap
        console.log(newChatWidth);
        console.log(contentWidth);
        chatContainer.style.width = `${newChatWidth}px`;
        // document.querySelector(".document-viewer").style.width = `${contentWidth - newChatWidth - 10}px`;
        document.querySelector(".document-viewer").style.marginLeft = `${newWidth + 5}px`;
    }
}

// Stop dragging
function stopDrag() {
    isDragging = false;
    activeHandle = null;
    document.removeEventListener("mousemove", handleDrag);
    document.removeEventListener("mouseup", stopDrag);
}

// Toggle mobile menu visibility
function toggleMenu() {
    document.querySelector('.navbar-links').classList.toggle('show');
}

// Fetch and display directory structure
async function fetchDirectoryStructure() {
    const response = await fetch('/categories');
    const data = await response.json();
    const directoryStructure = document.getElementById('directory-structure');
    
    let activeItem = null; // Track the currently active item

    directoryStructure.innerHTML = ''; // Clear existing content

    Object.entries(data.directory_structure).forEach(([folder, files]) => {
        const folderItem = document.createElement('li');

        const toggleIcon = document.createElement('span');
        toggleIcon.classList.add('toggle-icon');
        toggleIcon.textContent = '▶'; // Right arrow icon
        toggleIcon.onclick = () => toggleFolder();

        const folderName = document.createElement('span');
        folderName.textContent = folder;
        folderName.classList.add('folder-name');
        folderName.addEventListener('click', (event) => {
            event.stopPropagation();
            toggleFolder();
            setActiveItem(folderName); // Highlight folder
        });

        const fileList = document.createElement('ul');
        fileList.classList.add('show');
        files.forEach(file => {
            const fileItem = document.createElement('li');
            fileItem.textContent = file;
            fileItem.classList.add('file-item');
            fileItem.addEventListener('click', (event) => {
                event.stopPropagation();
                setActiveItem(fileItem); // Highlight clicked file
            });
            fileList.appendChild(fileItem);
        });

        folderItem.append(toggleIcon, folderName, fileList);
        directoryStructure.appendChild(folderItem);

        function toggleFolder() {
            const isVisible = fileList.style.display === 'block';
            fileList.style.display = isVisible ? 'none' : 'block';
            toggleIcon.textContent = isVisible ? '▶' : '▼';
        }

        function displayPDF(activeItem) {
            const parent = activeItem.parentElement.parentElement;
            const folder = parent.querySelector('.folder-name').textContent;
            console.log(folder);

            // Construct the PDF file path
            const pdfFilePath = "/pdf/" + folder + "/" + activeItem.textContent;

            // Get the PDF viewer element
            const pdfViewer = document.getElementById('pdf-viewer');

            // Set the src attribute to display the PDF
            pdfViewer.src = pdfFilePath;
        }

        function setActiveItem(item) {
            if (activeItem) activeItem.classList.remove('active');
            item.classList.add('active');
            activeItem = item;

            if (activeItem.classList.contains('file-item')) {
                displayPDF(activeItem);
            }
            
        }
    });

    document.addEventListener('click', () => {
        if (activeItem) {
            activeItem.classList.remove('active');
            activeItem = null;
        }
    });
}

// Fetch categories
let preloadedCategories = [];
async function fetchCategories() {
    try {
        const response = await fetch("http://127.0.0.1:8000/categories");
        if (response.ok) {
            const data = await response.json();
            preloadedCategories = Object.keys(data['directory_structure']);
        } else {
            console.error("Failed to fetch categories.");
        }
    } catch (error) {
        console.error("Error fetching categories:", error);
    }
}

// Show modal and fetch categories
function showModal() {
    fetchCategories();
    document.getElementById("upload-modal").style.display = "flex";
}

// Close modal
function closeModal() {
    document.getElementById("upload-modal").style.display = "none";
}

// Filter categories based on user input
function filterCategories() {
    const inputValue = document.getElementById("category").value.trim();
    const categorySuggestions = document.getElementById("category-suggestions");
    categorySuggestions.innerHTML = ""; // Clear previous suggestions

    if (inputValue) {
        const filteredCategories = preloadedCategories.filter(category =>
            category.toLowerCase().includes(inputValue.toLowerCase())
        );

        filteredCategories.forEach(category => {
            const suggestionItem = document.createElement("li");
            suggestionItem.textContent = category;
            suggestionItem.onclick = () => selectCategory(category);
            categorySuggestions.appendChild(suggestionItem);
        });

        if (filteredCategories.length === 0) {
            const newCategoryItem = document.createElement("li");
            newCategoryItem.textContent = `Create "${inputValue}"`;
            newCategoryItem.onclick = () => selectCategory(inputValue, true);
            categorySuggestions.appendChild(newCategoryItem);
        }
    }
}

// Select category and handle new category creation
function selectCategory(category, isNew = false) {
    document.getElementById("category").value = category;
    document.getElementById("category-suggestions").innerHTML = "";
    if (isNew) {
        console.log(`Creating new category: ${category}`);
    }
}

// Upload files and handle category selection
async function uploadFiles() {
    const fileInput = document.getElementById("files");
    const selectedCategory = document.getElementById("category").value.trim();
    const formData = new FormData();

    formData.append("category", selectedCategory);
    Array.from(fileInput.files).forEach(file => formData.append("files", file));

    try {
        const response = await fetch("http://127.0.0.1:8000/upload", {
            method: "POST",
            body: formData,
        });

        if (response.ok) {
            alert("Files uploaded successfully!");
            fileInput.value = "";
            document.getElementById("category").value = "";
            closeModal();
            fetchDirectoryStructure();
        } else {
            alert("Failed to upload files.");
        }
    } catch (error) {
        console.error("Error uploading files:", error);
        alert("Error uploading files.");
    }
}

// Handle chat message sending
async function sendMessage() {
    const inputField = document.getElementById("chat-input");
    const message = inputField.value.trim();
    if (message) {
        addMessageToChat(message, "user");
        inputField.value = "";

        try {
            const response = await fetch("http://127.0.0.1:8000/chat_reply", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ message })
            });

            if (!response.ok) throw new Error("Network response was not ok");

            const data = await response.json();
            addMessageToChat(data.message, "bot");
        } catch (error) {
            console.error("Error sending message:", error);
            addMessageToChat("Error: Could not send message.", "bot");
        }
    }
}

document.getElementById("chat-input").addEventListener("keypress", function(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        sendMessage();
    }
});

function addMessageToChat(message, sender) {
    const chatMessages = document.getElementById("chat-messages");
    const messageElem = document.createElement("div");
    messageElem.classList.add("message", sender === "user" ? "user-message" : "bot-message");
    messageElem.textContent = message;
    chatMessages.appendChild(messageElem);
    chatMessages.scrollTop = chatMessages.scrollHeight; // Auto-scroll to the bottom
}

// Fetch directory structure on page load
window.onload = fetchDirectoryStructure;