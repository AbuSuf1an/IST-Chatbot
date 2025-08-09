class ChatBot {
    constructor() {
        this.conversationHistory = [];
        this.apiUrl = 'http://localhost:8001/api/chat';
    }
    
    async sendMessage(message) {
        try {
            const response = await fetch(this.apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Store in local conversation history (optional)
            this.conversationHistory.push({
                user: message,
                bot: data.response,
                timestamp: data.timestamp
            });
            
            return data.response;
            
        } catch (error) {
            console.error('Chat error:', error);
            throw error;
        }
    }
    
    clearLocalHistory() {
        this.conversationHistory = [];
        console.log('Local conversation history cleared');
    }
    
    getLocalHistory() {
        return this.conversationHistory;
    }
}

// Initialize chatbot
const chatbot = new ChatBot();

// Optional: Clear local history when page is refreshed
window.addEventListener('beforeunload', () => {
    chatbot.clearLocalHistory();
});