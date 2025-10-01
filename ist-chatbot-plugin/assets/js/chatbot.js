/**
 * IST Chatbot Widget JavaScript
 * Handles the chatbot interface and API communication
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        apiUrl: 'http://localhost:8001/api/chat',
        initialGreeting: 'Hello! Welcome to Institute of Science and Technology. I\'m here to help you with questions about IST. How can I help you today?',
        placeholderText: 'Ask me about IST...',
        errorMessage: 'Sorry, I\'m having trouble connecting right now. Please try again in a moment.',
        botName: 'IST AI Chatbot',
        botAvatar: '<img src="assets/img/ist-chatbot.png" alt="IST Chatbot Logo">',
        botAvatarInside: '<img src="assets/img/ist-chatbot.png" alt="IST ChatbotLogo" style="width:24px;height:24px;border-radius:50%;">',
        // studentAvatar: '<img src="assets/img/person-icon.png" alt="Student Avatar" style="width:24px;height:24px;border-radius:50%;">'
    };

    // Widget state
    let isWidgetOpen = false;
    let isLoading = false;
    let messageHistory = [];

    // DOM elements
    let toggleButton, widget, messagesContainer, inputField, sendButton, loadingIndicator;

    /**
     * Initialize the chatbot widget
     */
    function initializeChatbot() {
        createWidgetHTML();
        bindEventListeners();
        showInitialGreeting();
        showBotStatus();
        console.log('IST Chatbot initialized successfully');
    }

    /**
     * Create the chatbot widget HTML structure
     */
    function createWidgetHTML() {
        // Create toggle button
        toggleButton = document.createElement('button');
        toggleButton.className = 'ist-chatbot-toggle';
        toggleButton.innerHTML = CONFIG.botAvatar;
        toggleButton.setAttribute('aria-label', 'Open IST Chatbot');
        toggleButton.title = 'Chat with IST Assistant';

        // Create widget container
        widget = document.createElement('div');
        widget.className = 'ist-chatbot-widget';
        widget.innerHTML = `
            <div class="ist-chatbot-header">
                <h3 class="ist-chatbot-title">
                    ${CONFIG.botAvatarInside} ${CONFIG.botName}
                </h3>
                <br>
                <div class="ist-chatbot-status" id="ist-chatbot-status" style="font-size:8px; color:white; display:none;">
                    🟢 Online
                </div>
                <button class="ist-chatbot-close" aria-label="Close chat">✕</button>
            </div>
            
            <div class="ist-chatbot-messages" id="ist-chatbot-messages">
                <!-- Messages will be inserted here -->
            </div>
            
            <div class="ist-chatbot-input-area">
                <textarea 
                    class="ist-chatbot-input" 
                    placeholder="${CONFIG.placeholderText}"
                    rows="1"
                    maxlength="500"
                ></textarea>
                <button class="ist-chatbot-send" aria-label="Send message">
                    <span>➤</span>
                </button>
            </div>
        `;

        // Append to body
        document.body.appendChild(toggleButton);
        document.body.appendChild(widget);

        // Cache DOM elements
        messagesContainer = document.getElementById('ist-chatbot-messages');
        inputField = widget.querySelector('.ist-chatbot-input');
        sendButton = widget.querySelector('.ist-chatbot-send');
    }

    /**
     * Bind event listeners
     */
    function bindEventListeners() {
        // Toggle button click
        toggleButton.addEventListener('click', function() {
            // Close popup instantly if visible
            if (window.istChatbotActivePopup && window.istChatbotActivePopup.parentNode) {
                window.istChatbotActivePopup.parentNode.removeChild(window.istChatbotActivePopup);
                window.istChatbotActivePopup = null;
            }
            toggleWidget();
        });

        // Close button click
        const closeButton = widget.querySelector('.ist-chatbot-close');
        closeButton.addEventListener('click', closeWidget);

        // Send button click
        sendButton.addEventListener('click', handleSendMessage);

        // Input field events
        inputField.addEventListener('keypress', handleKeyPress);
        inputField.addEventListener('input', handleInputChange);

        // Auto-resize textarea
        inputField.addEventListener('input', autoResizeTextarea);

        // Close widget when clicking outside
        document.addEventListener('click', handleOutsideClick);

        // Prevent widget from closing when clicking inside
        widget.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }

    /**
     * Handle keypress events in input field
     */
    function handleKeyPress(event) {
        if (event.key === 'Enter') {
            if (event.shiftKey) {
                // Allow new line with Shift+Enter
                return;
            } else {
                // Send message with Enter
                event.preventDefault();
                handleSendMessage();
            }
        }
    }

    /**
     * Handle input changes (character count, etc.)
     */
    function handleInputChange(event) {
        const message = event.target.value.trim();
        sendButton.disabled = !message || isLoading;
    }

    /**
     * Auto-resize textarea based on content
     */
    function autoResizeTextarea() {
        inputField.style.height = 'auto';
        const newHeight = Math.min(inputField.scrollHeight, 60);
        inputField.style.height = newHeight + 'px';
    }

    /**
     * Handle clicks outside the widget
     */
    function handleOutsideClick(event) {
        if (isWidgetOpen && 
            !widget.contains(event.target) && 
            !toggleButton.contains(event.target)) {
            closeWidget();
        }
    }

    /**
     * Toggle widget visibility
     */
    function toggleWidget() {
        if (isWidgetOpen) {
            closeWidget();
        } else {
            openWidget();
        }
    }

    /**
     * Open the chatbot widget
     */
    function openWidget() {
        isWidgetOpen = true;
        widget.classList.add('active');
        toggleButton.classList.add('active');
        toggleButton.innerHTML = CONFIG.botAvatar;
        inputField.focus();
        scrollToBottom();
    }

    /**
     * Close the chatbot widget
     */
    function closeWidget() {
        isWidgetOpen = false;
        widget.classList.remove('active');
        toggleButton.classList.remove('active');
        toggleButton.innerHTML = CONFIG.botAvatar;
    }

    /**
     * Show initial greeting message
     */
    function showInitialGreeting() {
        addMessage('bot', CONFIG.initialGreeting);
    }

    /**
     * Handle sending a message
     */
    async function handleSendMessage() {
        const message = inputField.value.trim();
        if (!message || isLoading) return;

        // Add user message to chat
        addMessage('user', message);

        // Clear input
        inputField.value = '';
        inputField.style.height = 'auto';

        // Store message in history
        messageHistory.push({ role: 'user', content: message });

        // Now show typing indicator
        setLoadingState(true);

        try {
            // Send message to API
            const response = await sendMessageToAPI(message);

            // Add bot response to chat
            addMessage('bot', response.response, response.context_sources);

            // Store bot response in history
            messageHistory.push({
                role: 'bot',
                content: response.response,
                sources: response.context_sources
            });

        } catch (error) {
            console.error('Chatbot error:', error);
            addMessage('bot', CONFIG.errorMessage);
        } finally {
            setLoadingState(false);
        }
    }

    /**
     * Send message to the backend API
     */
    async function sendMessageToAPI(message) {
        const response = await fetch(CONFIG.apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    /**
     * Add a message to the chat
     */
    function addMessage(sender, content, sources = null) {
        const messageElement = document.createElement('div');
        messageElement.className = `ist-chatbot-message ${sender}`;

        let sourceInfo = '';
        if (sources && sources.length > 0) {
            const uniqueSources = [...new Set(sources)];
            sourceInfo = `<div class="ist-chatbot-sources">Sources: ${uniqueSources.join(', ')}</div>`;
        }

        const formattedContent = formatMessage(content);

        if (sender === 'bot') {
            messageElement.innerHTML = `
                <div class="ist-chatbot-avatar">${CONFIG.botAvatarInside}</div>
                <div class="ist-chatbot-message-content"></div>
            `;
            messagesContainer.appendChild(messageElement);
            const contentDiv = messageElement.querySelector('.ist-chatbot-message-content');
            typeMessage(contentDiv, formattedContent);
        } else {
            messageElement.innerHTML = `
                <div class="ist-chatbot-message-content"></div>
                <!--<div class="ist-chatbot-avatar">${CONFIG.studentAvatar}</div>-->
            `;
            messagesContainer.appendChild(messageElement);
            const contentDiv = messageElement.querySelector('.ist-chatbot-message-content');
            contentDiv.textContent = formattedContent;
        }

        messagesContainer.appendChild(messageElement);
        scrollToBottom();
    }

    /**
     * Format message content (handle line breaks, links, etc.)
     */
    function formatMessage(content) {
        if (!content) {
            return '';
        }

        return content
            .replace(/\r\n/g, '\n')
            .replace(/\t/g, '    ');
    }

    /**
     * Set loading state
     */
    function setLoadingState(loading) {
        isLoading = loading;
        sendButton.disabled = loading || !inputField.value.trim();
        
        if (loading) {
            showLoadingIndicator();
        } else {
            hideLoadingIndicator();
            inputField.focus();
        }
    }

    /**
     * Show loading indicator
     */
    function showLoadingIndicator() {
        if (!loadingIndicator) {
            loadingIndicator = document.createElement('div');
            loadingIndicator.className = 'ist-chatbot-message bot';
            loadingIndicator.innerHTML = `
                <div class="ist-chatbot-avatar">${CONFIG.botAvatarInside}</div>
                <div class="ist-chatbot-loading active">
                    <div class="ist-chatbot-typing">Typing</div>
                </div>
            `;
        }
        
        messagesContainer.appendChild(loadingIndicator);
        scrollToBottom();
    }

    /**
     * Hide loading indicator
     */
    function hideLoadingIndicator() {
        if (loadingIndicator && loadingIndicator.parentNode) {
            loadingIndicator.parentNode.removeChild(loadingIndicator);
        }
    }

    /**
     * Scroll chat to bottom
     */
    function scrollToBottom() {
        setTimeout(() => {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }, 100);
    }

    /**
     * Check if API is available
     */
    async function checkAPIStatus() {
        try {
            const response = await fetch(CONFIG.apiUrl.replace('/api/chat', '/health'));
            return response.ok;
        } catch (error) {
            console.warn('IST Chatbot API is not available:', error);
            return false;
        }
    }

    async function showBotStatus() {
        const statusEl = document.getElementById('ist-chatbot-status');
        if (!statusEl) return;
        const ok = await checkAPIStatus();
        if (ok) {
            statusEl.style.display = 'block';
        } else {
            statusEl.style.display = 'none';
        }
    }

    /**
     * Show chatbot popup
     */
    function showChatbotPopup() {
        // Try to play sound (may be blocked by browser)
        const audio = new Audio('assets/sounds/popup.mp3');
        audio.volume = 0.1;
        audio.play().catch(() => {
            // If blocked, play on first user interaction
            const playOnInteraction = () => {
                audio.play();
                document.removeEventListener('click', playOnInteraction);
            };
            document.addEventListener('click', playOnInteraction);
        });

        // Create popup element
        const popup = document.createElement('div');
        popup.className = 'ist-chatbot-popup ist-chatbot-popup-animate';
        popup.textContent = 'Hey, how can I help you?';

        // Position near the toggle button
        popup.style.position = 'fixed';
        popup.style.bottom = '80px';
        popup.style.right = '30px';
        popup.style.background = 'linear-gradient(135deg, #e67c1e 0%, #b92c2c 100%)';
        popup.style.color = '#fff';
        popup.style.padding = '12px 20px';
        popup.style.borderRadius = '18px';
        popup.style.boxShadow = '0 4px 16px rgba(185,44,44,0.15)';
        popup.style.fontSize = '15px';
        popup.style.zIndex = '10001';
        popup.style.transition = 'opacity 0.4s';

        // Store reference globally so we can close it later
        window.istChatbotActivePopup = popup;

        document.body.appendChild(popup);

        // Hide after 4 seconds
        setTimeout(() => {
            popup.style.opacity = '0';
            setTimeout(() => {
                if (popup.parentNode) popup.parentNode.removeChild(popup);
                window.istChatbotActivePopup = null;
            }, 400);
        }, 4000);
    }

    /**
     * Type message with typing effect
     */
    function typeMessage(element, text, speed = 20, callback) {
        let i = 0;
        element.textContent = '';
        function type() {
            if (i < text.length) {
                element.textContent += text.charAt(i);
                i++;
                setTimeout(type, speed);
            } else if (callback) {
                callback();
            }
        }
        type();
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeChatbot);
    } else {
        initializeChatbot();
    }

    // Show popup on first user click as well
    let popupShownOnClick = false;
    document.addEventListener('click', function onFirstClick(e) {
        // If the first click is on the chatbot toggle button, do NOT show the popup
        if (toggleButton && e.target === toggleButton) {
            popupShownOnClick = true;
            document.removeEventListener('click', onFirstClick);
            return;
        }
        if (!popupShownOnClick) {
            showChatbotPopup();
            popupShownOnClick = true;
            document.removeEventListener('click', onFirstClick);
        }
    });

    // Expose public methods (optional)
    window.ISTChatbot = {
        open: openWidget,
        close: closeWidget,
        toggle: toggleWidget,
        sendMessage: function(message) {
            inputField.value = message;
            handleSendMessage();
        }
    };

})();
