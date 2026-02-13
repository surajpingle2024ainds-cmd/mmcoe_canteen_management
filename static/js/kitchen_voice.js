/**
 * Kitchen Voice Assistant
 * Provides voice recognition, synthesis, and command handling for kitchen staff
 */

class KitchenVoiceAssistant {
    constructor() {
        this.recognition = null;
        this.synthesis = window.speechSynthesis;
        this.isListening = false;
        this.isEnabled = false;
        this.knownOrders = new Set(); // Track orders we've already announced
        this.lastOrderCount = 0;
        this.token = localStorage.getItem('authToken') || '';
        
        this.initSpeechRecognition();
        this.initSpeechSynthesis();
    }

    initSpeechRecognition() {
        // Check for browser support
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            console.warn('Speech recognition not supported in this browser');
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = false;
        this.recognition.lang = 'en-US';

        this.recognition.onresult = (event) => {
            const transcript = event.results[event.results.length - 1][0].transcript.trim().toLowerCase();
            console.log('Voice command:', transcript);
            this.handleVoiceCommand(transcript);
        };

        this.recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            if (event.error === 'no-speech') {
                // Restart listening if no speech detected
                if (this.isListening) {
                    this.recognition.stop();
                    setTimeout(() => {
                        if (this.isListening) this.recognition.start();
                    }, 500);
                }
            }
        };

        this.recognition.onend = () => {
            // Auto-restart if still listening
            if (this.isListening) {
                setTimeout(() => {
                    if (this.isListening) this.recognition.start();
                }, 100);
            }
        };
    }

    initSpeechSynthesis() {
        // Set default voice settings
        const voices = this.synthesis.getVoices();
        if (voices.length > 0) {
            this.availableVoices = voices;
            console.log('[Voice] Loaded', voices.length, 'voices');
        } else {
            // Wait for voices to load
            this.synthesis.onvoiceschanged = () => {
                this.availableVoices = this.synthesis.getVoices();
                console.log('[Voice] Voices loaded:', this.availableVoices.length);
            };
        }
    }

    speak(text, priority = false) {
        // Temporarily remove the isEnabled check for testing - we'll enforce it in UI
        // if (!this.isEnabled) {
        //     console.log('[Voice] Speak called but assistant is not enabled');
        //     return;
        // }

        if (!text || text.trim() === '') {
            console.log('[Voice] Empty text provided to speak');
            return;
        }

        // Check if speech synthesis is available
        if (!('speechSynthesis' in window)) {
            console.error('[Voice] Speech synthesis not supported in this browser');
            alert('Text-to-speech is not supported in your browser.');
            return;
        }

        console.log('[Voice] Speaking:', text);
        console.log('[Voice] isEnabled:', this.isEnabled);
        console.log('[Voice] synthesis.speaking:', this.synthesis.speaking);

        // Cancel previous speech if it's not priority
        if (priority && this.synthesis.speaking) {
            this.synthesis.cancel();
        }

        // Cancel any existing speech
        if (this.synthesis.speaking) {
            console.log('[Voice] Cancelling previous speech');
            this.synthesis.cancel();
            // Wait a moment for cancellation
            setTimeout(() => {
                this.doSpeak(text);
            }, 100);
        } else {
            this.doSpeak(text);
        }
    }

    doSpeak(text) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 1.0; // Max volume

        // Error handling
        utterance.onerror = (event) => {
            console.error('[Voice] Speech synthesis error:', event.error, event);
            alert('Speech error: ' + event.error + '. Please check your system audio settings.');
        };

        utterance.onstart = () => {
            console.log('[Voice] Speech started successfully');
        };

        utterance.onend = () => {
            console.log('[Voice] Speech completed');
        };

        // Try to use a female English voice
        if (this.availableVoices && this.availableVoices.length > 0) {
            const preferredVoice = this.availableVoices.find(v => 
                v.lang.includes('en') && (v.name.includes('Female') || v.name.includes('Zira') || v.name.includes('Samantha'))
            ) || this.availableVoices.find(v => v.lang.includes('en'));
            if (preferredVoice) {
                utterance.voice = preferredVoice;
                console.log('[Voice] Using voice:', preferredVoice.name);
            }
        } else {
            // Load voices if not loaded
            const voices = this.synthesis.getVoices();
            if (voices.length > 0) {
                this.availableVoices = voices;
                const preferredVoice = voices.find(v => 
                    v.lang.includes('en') && (v.name.includes('Female') || v.name.includes('Zira'))
                ) || voices.find(v => v.lang.includes('en'));
                if (preferredVoice) {
                    utterance.voice = preferredVoice;
                    console.log('[Voice] Using voice:', preferredVoice.name);
                }
            } else {
                console.log('[Voice] Voices not loaded yet, using default');
            }
        }

        try {
            this.synthesis.speak(utterance);
            console.log('[Voice] speak() called on synthesis');
        } catch (e) {
            console.error('[Voice] Error speaking:', e);
            alert('Error playing audio: ' + e.message + '. Please check your browser settings.');
        }
    }

    startListening() {
        if (!this.recognition) {
            alert('Voice recognition is not supported in your browser. Please use Chrome or Edge.');
            return;
        }

        if (!this.isListening) {
            try {
                this.recognition.start();
                this.isListening = true;
                this.updateListeningIndicator(true);
                // Update UI indicator as well
                const indicator = document.getElementById('voice-listening-indicator');
                if (indicator) {
                    indicator.textContent = '🎤 Listening...';
                    indicator.classList.add('active');
                }
                this.speak('Voice assistant activated. I am listening.');
            } catch (e) {
                console.error('Error starting recognition:', e);
            }
        }
    }

    stopListening() {
        if (this.isListening) {
            this.recognition.stop();
            this.isListening = false;
            this.updateListeningIndicator(false);
            // Update UI indicator as well
            const indicator = document.getElementById('voice-listening-indicator');
            if (indicator) {
                indicator.textContent = '🔇 Not listening';
                indicator.classList.remove('active');
            }
            this.speak('Voice assistant deactivated.');
        }
    }

    toggleListening() {
        if (this.isListening) {
            this.stopListening();
        } else {
            this.startListening();
        }
    }

    enable() {
        this.isEnabled = true;
        this.speak('Kitchen voice assistant enabled. Say "start listening" to activate voice commands.');
    }

    disable() {
        this.isEnabled = false;
        if (this.isListening) {
            this.stopListening();
        }
        this.speak('Kitchen voice assistant disabled.');
    }

    async handleVoiceCommand(transcript) {
        // Normalize the transcript
        const cmd = transcript.toLowerCase().trim();

        // Command patterns
        if (cmd.includes('stop listening') || cmd.includes('deactivate')) {
            this.stopListening();
            return;
        }

        if (cmd.includes('what orders') || cmd.includes('show orders') || cmd.includes('list orders')) {
            await this.speakOrders();
            return;
        }

        if (cmd.includes('how many orders') || cmd.includes('order count')) {
            await this.speakOrderCount();
            return;
        }

        // Match order numbers (e.g., "show order 123", "order 456")
        const orderMatch = cmd.match(/order\s*(\d+)/);
        if (orderMatch) {
            const orderId = parseInt(orderMatch[1]);
            await this.speakOrderDetails(orderId);
            return;
        }

        // Status updates (e.g., "mark order 123 as ready", "order 456 ready")
        const statusMatch = cmd.match(/(mark|set|make)\s*order\s*(\d+)\s*(as\s*)?(pending|preparing|ready|completed|delivered)/i);
        if (statusMatch) {
            const orderId = parseInt(statusMatch[2]);
            const status = statusMatch[4].toLowerCase();
            await this.updateOrderStatus(orderId, status);
            return;
        }

        // Short status updates (e.g., "order 123 ready")
        const shortStatusMatch = cmd.match(/order\s*(\d+)\s*(pending|preparing|ready|completed|delivered)/i);
        if (shortStatusMatch) {
            const orderId = parseInt(shortStatusMatch[1]);
            const status = shortStatusMatch[2].toLowerCase();
            await this.updateOrderStatus(orderId, status);
            return;
        }

        // Help command
        if (cmd.includes('help') || cmd.includes('what can you do')) {
            this.speakHelp();
            return;
        }

        // Default: ask for clarification
        this.speak('I did not understand that command. Say "help" for available commands.');
    }

    async speakOrders() {
        try {
            const response = await fetch('/api/kitchen/orders/live', {
                headers: { 'Authorization': this.token ? 'Bearer ' + this.token : '' }
            });
            const orders = await response.json();
            
            if (!Array.isArray(orders) || orders.length === 0) {
                this.speak('There are no pending orders at the moment.');
                return;
            }

            const pending = orders.filter(o => ['pending', 'accepted'].includes(o.status?.toLowerCase()));
            const preparing = orders.filter(o => o.status?.toLowerCase() === 'preparing');
            const ready = orders.filter(o => o.status?.toLowerCase() === 'ready');

            let message = `You have ${orders.length} active orders. `;
            if (pending.length > 0) message += `${pending.length} pending, `;
            if (preparing.length > 0) message += `${preparing.length} in preparation, `;
            if (ready.length > 0) message += `${ready.length} ready for pickup. `;

            // Mention VIP orders
            const vipOrders = orders.filter(o => o.is_vip);
            if (vipOrders.length > 0) {
                message += `You have ${vipOrders.length} VIP order${vipOrders.length > 1 ? 's' : ''}. `;
            }

            this.speak(message);
        } catch (e) {
            console.error('Error fetching orders:', e);
            this.speak('Sorry, I could not fetch the orders at this time.');
        }
    }

    async speakOrderCount() {
        try {
            const response = await fetch('/api/kitchen/orders/live', {
                headers: { 'Authorization': this.token ? 'Bearer ' + this.token : '' }
            });
            const orders = await response.json();
            
            if (!Array.isArray(orders)) {
                this.speak('Unable to get order count.');
                return;
            }

            const pending = orders.filter(o => ['pending', 'accepted'].includes(o.status?.toLowerCase())).length;
            const preparing = orders.filter(o => o.status?.toLowerCase() === 'preparing').length;
            const ready = orders.filter(o => o.status?.toLowerCase() === 'ready').length;

            this.speak(`You have ${pending} pending orders, ${preparing} in preparation, and ${ready} ready for pickup.`);
        } catch (e) {
            console.error('Error fetching order count:', e);
            this.speak('Sorry, I could not get the order count.');
        }
    }

    async speakOrderDetails(orderId) {
        try {
            const response = await fetch('/api/kitchen/orders/live', {
                headers: { 'Authorization': this.token ? 'Bearer ' + this.token : '' }
            });
            const orders = await response.json();
            
            if (!Array.isArray(orders)) {
                this.speak('Unable to fetch orders.');
                return;
            }

            const order = orders.find(o => o.db_id === orderId || o.id === orderId);
            if (!order) {
                this.speak(`Order ${orderId} not found in active orders.`);
                return;
            }

            const items = (order.items || []).map(i => `${i.quantity} ${i.name}`).join(', ');
            const status = order.status || 'unknown';
            const total = order.total || 0;
            const vip = order.is_vip ? ' This is a VIP order.' : '';

            this.speak(`Order ${orderId}. Status: ${status}. Items: ${items}. Total: ${total} rupees.${vip}`);
        } catch (e) {
            console.error('Error fetching order details:', e);
            this.speak(`Sorry, I could not get details for order ${orderId}.`);
        }
    }

    async updateOrderStatus(orderId, status) {
        // Map voice commands to actual status values
        const statusMap = {
            'pending': 'pending',
            'preparing': 'preparing',
            'ready': 'ready',
            'completed': 'ready',
            'delivered': 'delivered'
        };

        const actualStatus = statusMap[status] || status;

        try {
            const response = await fetch(`/api/kitchen/orders/${orderId}/status`, {
                method: 'PUT',
                headers: {
                    'Authorization': this.token ? 'Bearer ' + this.token : '',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ status: actualStatus })
            });

            if (response.ok) {
                this.speak(`Order ${orderId} status updated to ${actualStatus}.`);
                // Trigger page refresh via custom event
                window.dispatchEvent(new CustomEvent('orderStatusUpdated'));
            } else {
                this.speak(`Failed to update order ${orderId}.`);
            }
        } catch (e) {
            console.error('Error updating order status:', e);
            this.speak(`Sorry, I could not update order ${orderId}.`);
        }
    }

    speakHelp() {
        console.log('[Voice] speakHelp called, isEnabled:', this.isEnabled);
        const helpText = `I can help you with kitchen operations. You can say: What orders to list all orders, How many orders to get the order count, Show order 123 to get details of a specific order, Mark order 123 as ready to update order status, Stop listening to deactivate voice commands. Available statuses are: pending, preparing, ready, and delivered.`;
        this.speak(helpText);
    }

    async checkForNewOrders() {
        if (!this.isEnabled) return;

        try {
            const response = await fetch('/api/kitchen/orders/live', {
                headers: { 'Authorization': this.token ? 'Bearer ' + this.token : '' }
            });
            const orders = await response.json();
            
            if (!Array.isArray(orders)) return;

            const currentOrderCount = orders.length;
            
            // Initialize on first run
            if (this.lastOrderCount === 0) {
                const currentOrderIds = new Set(orders.map(o => o.db_id || o.id));
                this.knownOrders = currentOrderIds;
                this.lastOrderCount = currentOrderCount;
                return;
            }
            
            // Check for new orders
            if (currentOrderCount > this.lastOrderCount) {
                const currentOrderIds = new Set(orders.map(o => o.db_id || o.id));
                orders.forEach(order => {
                    const orderId = order.db_id || order.id;
                    if (!this.knownOrders.has(orderId)) {
                        // New order detected
                        this.announceNewOrder(order);
                        this.knownOrders.add(orderId);
                    }
                });
            }

            // Update known orders set and count
            const currentOrderIds = new Set(orders.map(o => o.db_id || o.id));
            this.knownOrders = currentOrderIds;
            this.lastOrderCount = currentOrderCount;
        } catch (e) {
            console.error('Error checking for new orders:', e);
        }
    }

    announceNewOrder(order) {
        const items = (order.items || []).map(i => `${i.quantity} ${i.name}`).join(', ');
        const total = order.total || 0;
        const vip = order.is_vip ? ' VIP order. ' : '';
        
        const announcement = `New order received. ${vip}Order number ${order.id}. Items: ${items}. Total: ${total} rupees.`;
        this.speak(announcement, true); // Priority announcement
    }

    updateListeningIndicator(isListening) {
        const indicator = document.getElementById('voice-listening-indicator');
        if (indicator) {
            indicator.textContent = isListening ? '🎤 Listening...' : '🔇 Not listening';
            indicator.className = isListening ? 'voice-status active' : 'voice-status';
        }
    }
}

// Initialize global voice assistant instance
let kitchenVoiceAssistant = null;

// Initialize when DOM is ready
function initKitchenVoiceAssistant() {
    if (!kitchenVoiceAssistant) {
        try {
            kitchenVoiceAssistant = new KitchenVoiceAssistant();
            // Dispatch event when initialized
            window.dispatchEvent(new CustomEvent('kitchenVoiceAssistantReady'));
        } catch (e) {
            console.error('Error initializing kitchen voice assistant:', e);
        }
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initKitchenVoiceAssistant);
} else {
    initKitchenVoiceAssistant();
}
