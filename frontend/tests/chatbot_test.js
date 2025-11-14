/**
 * @jest-environment jsdom
 */

// Mock fetch
global.fetch = jest.fn();

// Import your chatbot class
const ISTChatbot = require('../assets/js/chatbot.js');

describe('IST Chatbot Widget', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        fetch.mockClear();
    });

    test('Widget creates proper DOM structure', () => {
        const chatbot = new ISTChatbot();
        
        expect(document.querySelector('.ist-chatbot-widget')).toBeTruthy();
        expect(document.querySelector('#chat-input')).toBeTruthy();
        expect(document.querySelector('#send-btn')).toBeTruthy();
        expect(document.querySelector('.chat-messages')).toBeTruthy();
        
        console.log('✅ DOM structure test passed');
    });

    test('Send message functionality', async () => {
        // Mock successful API response
        fetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                response: 'Test response from API',
                sources: ['test.pdf'],
                session_id: 'test123'
            })
        });

        const chatbot = new ISTChatbot();
        const input = document.querySelector('#chat-input');
        input.value = 'Test message';
        
        await chatbot.sendMessage();
        
        expect(fetch).toHaveBeenCalledWith(
            expect.stringContaining('/api/chat'),
            expect.objectContaining({
                method: 'POST'
            })
        );
        
        console.log('✅ Message sending test passed');
    });

    test('Error handling', async () => {
        // Mock API failure
        fetch.mockRejectedValueOnce(new Error('API Error'));

        const chatbot = new ISTChatbot();
        const input = document.querySelector('#chat-input');
        input.value = 'Test message';
        
        await chatbot.sendMessage();
        
        // Check if error message is displayed
        const messages = document.querySelectorAll('.message');
        const hasErrorMessage = Array.from(messages).some(msg => 
            msg.textContent.includes('error') || msg.textContent.includes('try again')
        );
        
        expect(hasErrorMessage).toBeTruthy();
        console.log('✅ Error handling test passed');
    });
});