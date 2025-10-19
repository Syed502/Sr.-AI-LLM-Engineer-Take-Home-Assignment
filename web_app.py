#!/usr/bin/env python3
"""
Dr. Donut Voice Ordering Web Application
A Flask web app that provides a browser-based interface for voice ordering
Uses Ultravox API for ASR and voice processing
"""

import asyncio
import json
import logging
import os
import aiohttp
import datetime
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import uuid
import base64
import threading
from websockets.asyncio import client as ws_client
import websockets
import concurrent.futures
import queue

# Import cart engine
from cart_engine import Cart, CartNormalizer
from menu_data import get_menu
from smart_cart_parser import SmartCartParser

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dr-donut-secret-key-' + str(uuid.uuid4())
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
user_sessions = {}

# Ultravox API configuration
ULTRAVOX_API_KEY = os.getenv("ULTRAVOX_API_KEY", "eOkGyqc9.wTCRS3JnMLAJ0k5GY49sSV9tLu4YpADg")

class UltravoxVoiceSession:
    """Manages a voice session with Ultravox WebSocket"""
    
    def __init__(self, session_id: str, menu_name: str = "small"):
        self.session_id = session_id
        self.menu = get_menu(menu_name)
        self.cart_normalizer = CartNormalizer(self.menu)
        self.smart_parser = SmartCartParser(self.menu)  # Add smart parser
        self.cart = Cart()
        self.order_history = []
        self.websocket = None
        self.join_url = None
        self.is_connected = False
        self.user_transcripts = []
        self.room_id = None  # Store the room ID for socket emissions
        self._loop = None
        self._loop_thread = None
        self._audio_queue = queue.Queue()
        self._running = False
        self._pending_user_input = ""  # Initialize pending user input
        self._pending_agent_output = ""  # Initialize pending agent output
        
    def _start_event_loop(self):
        """Start a dedicated event loop in a separate thread"""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_forever()
            finally:
                self._loop.close()
        
        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
        
        # Wait for loop to be ready
        while self._loop is None:
            threading.Event().wait(0.01)
    
    def _stop_event_loop(self):
        """Stop the event loop"""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread:
            self._loop_thread.join(timeout=1.0)
        
    async def create_ultravox_call(self):
        """Create a new Ultravox call and get join URL"""
        try:
            target = "https://api.ultravox.ai/api/calls"
            
            # Get current cart state for the system prompt
            cart_summary = self._get_cart_summary()
            
            system_prompt = f"""
You are a drive-thru order taker for a donut shop called "Dr. Donut". Local time is currently: {datetime.now().isoformat()}
The user is talking to you over voice on their phone, and your response will be read out loud with realistic text-to-speech (TTS) technology.

IMPORTANT: The current order in the cart is:
{cart_summary}

You MUST reference this cart when responding. If the user asks to remove something, check if it's actually in the cart above before saying it's not there.

Follow every direction here when crafting your response:

1. Use natural, conversational language that is clear and easy to follow (short sentences, simple words).
1a. Be concise and relevant: Most of your responses should be a sentence or two, unless you're asked to go deeper. Don't monopolize the conversation.
1b. Use discourse markers to ease comprehension. Never use the list format.

2. Keep the conversation flowing.
2a. Clarify: when there is ambiguity, ask clarifying questions, rather than make assumptions.
2b. Don't implicitly or explicitly try to end the chat (i.e. do not end a response with "Talk soon!", or "Enjoy!").
2c. Sometimes the user might just want to chat. Ask them relevant follow-up questions.
2d. Don't ask them if there's anything else they need help with (e.g. don't say things like "How can I assist you further?").

3. Remember that this is a voice conversation:
3a. Don't use lists, markdown, bullet points, or other formatting that's not typically spoken.
3b. Type out numbers in words (e.g. 'twenty twelve' instead of the year 2012)
3c. If something doesn't make sense, it's likely because you misheard them. There wasn't a typo, and the user didn't mispronounce anything.

When talking with the user, use the following script:
1. Take their order, acknowledging each item as it is ordered. If it's not clear which menu item the user is ordering, ask them to clarify.
   DO NOT add an item to the order unless it's one of the items on the menu below.
2. Once the order is complete, repeat back the order.
3. Total up the price of all ordered items and inform the user.
4. Ask the user to pull up to the drive thru window.

The menu of available items is as follows:

# DONUTS
PUMPKIN SPICE ICED DOUGHNUT $1.29
CHOCOLATE ICED DOUGHNUT $1.09
RASPBERRY FILLED DOUGHNUT $1.09

# COFFEE & DRINKS
PUMPKIN SPICE LATTE $4.59
REGULAR BREWED COFFEE $1.79
LATTE $3.49
"""

            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"X-API-Key": ULTRAVOX_API_KEY}
                body = {
                    "systemPrompt": system_prompt,
                    "temperature": 0.8,
                    "medium": {
                        "serverWebSocket": {
                            "inputSampleRate": 48000,
                            "outputSampleRate": 48000,
                            "clientBufferSizeMs": 30000,
                        }
                    },
                }
                
                async with session.post(target, headers=headers, json=body) as response:
                    response.raise_for_status()
                    response_json = await response.json()
                    self.join_url = response_json["joinUrl"]
                    logger.info(f"Created Ultravox call: {self.join_url}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to create Ultravox call: {e}")
            return False
    
    async def connect_websocket(self):
        """Connect to Ultravox WebSocket"""
        if not self.join_url:
            logger.info("🔗 Creating Ultravox call...")
            if not await self.create_ultravox_call():
                logger.error("❌ Failed to create Ultravox call")
                return False
        
        try:
            # Start dedicated event loop if not already running
            if not self._loop:
                logger.info("🔄 Starting dedicated event loop...")
                self._start_event_loop()
            
            # Schedule the connection in the dedicated loop with timeout
            logger.info("⏱️ Scheduling WebSocket connection...")
            future = asyncio.run_coroutine_threadsafe(
                self._connect_websocket_async(), 
                self._loop
            )
            
            # Wait for connection with timeout
            result = future.result(timeout=20.0)  # 20 second total timeout
            
            if result:
                # Start the audio processor AFTER successful connection
                logger.info("🎵 Starting audio processor...")
                asyncio.run_coroutine_threadsafe(
                    self._process_audio_queue(), 
                    self._loop
                )
                logger.info("✅ Audio processor started successfully")
            else:
                logger.error("❌ WebSocket connection failed")
            
            return result
            
        except asyncio.TimeoutError:
            logger.error("⏰ Connection timeout - taking too long to connect")
            return False
        except Exception as e:
            logger.error(f"💥 Failed to connect to Ultravox WebSocket: {e}")
            return False
    
    async def _connect_websocket_async(self):
        """Actual async WebSocket connection"""
        try:
            logger.info(f"🔌 Connecting to WebSocket: {self.join_url}")
            
            # Add connection timeout
            self.websocket = await asyncio.wait_for(
                ws_client.connect(self.join_url), 
                timeout=15.0  # 15 second timeout
            )
            
            self.is_connected = True
            self._running = True
            logger.info(f"✅ Connected to Ultravox WebSocket for session {self.session_id}")
            logger.info(f"🔗 WebSocket state: connected={self.is_connected}, running={self._running}")
            
            # Start listening for messages
            asyncio.create_task(self._listen_websocket())
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ WebSocket connection timeout for session {self.session_id}")
            return False
        except Exception as e:
            logger.error(f"💥 Failed to connect WebSocket: {e}")
            return False
    
    async def _process_audio_queue(self):
        """Process audio data from the queue"""
        logger.info(f"🎵 Audio processor started for session {self.session_id}")
        audio_chunk_count = 0
        
        while self._running:
            try:
                # Check for audio data (non-blocking)
                try:
                    audio_data = self._audio_queue.get_nowait()
                    audio_chunk_count += 1
                    
                    if audio_chunk_count <= 10 or audio_chunk_count % 50 == 0:
                        logger.info(f"⚡ Processing audio chunk #{audio_chunk_count}, size: {len(audio_data)} bytes, queue remaining: {self._audio_queue.qsize()}")
                    
                    if self.websocket and self.is_connected:
                        await self.websocket.send(audio_data)
                        if audio_chunk_count <= 5 or audio_chunk_count % 50 == 0:
                            logger.info(f"✅ Successfully sent audio chunk #{audio_chunk_count} to Ultravox")
                    else:
                        logger.warning(f"❌ Cannot send audio chunk #{audio_chunk_count}: websocket={bool(self.websocket)}, connected={self.is_connected}")
                        
                except queue.Empty:
                    # No audio data, wait a bit
                    await asyncio.sleep(0.01)
                    continue
                    
            except Exception as e:
                logger.error(f"💥 Error processing audio chunk #{audio_chunk_count}: {e}")
                await asyncio.sleep(0.1)
        
        logger.info(f"🛑 Audio processor stopped for session {self.session_id}")
    
    async def _listen_websocket(self):
        """Listen for messages from Ultravox WebSocket"""
        try:
            logger.info(f"🔊 Starting WebSocket message listener for session {self.session_id}")
            message_count = 0
            
            async for message in self.websocket:
                message_count += 1
                if message_count <= 10 or message_count % 50 == 0:
                    logger.info(f"📨 Received WebSocket message #{message_count}")
                    
                await self._handle_websocket_message(message)
                
        except Exception as e:
            logger.error(f"💥 WebSocket listening error: {e}")
            self.is_connected = False
            self._running = False
    
    async def _handle_websocket_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            if isinstance(message, str):
                data = json.loads(message)
                await self._handle_data_message(data)
            # Audio data is handled separately if needed
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    async def _handle_data_message(self, msg: dict):
        """Handle data messages from Ultravox"""
        msg_type = msg.get("type")
        
        # Only log important message types, not every single one
        if msg_type not in ["transcript"]:
            logger.info(f"📨 Received message type: {msg_type}")
        
        if msg_type == "transcript":
            role = msg.get("role")
            text = msg.get("text", "")
            delta = msg.get("delta", "")
            final = msg.get("final", False)
            
            # Only log final transcripts, not deltas
            if text and final:
                if role == "user":
                    print(f"\n� USER: {text}")
                elif role == "agent":
                    print(f"🤖 AGENT: {text}")
            
            if role == "user":
                if text:
                    # Final transcript with text
                    self.user_transcripts.append(text)
                    
                    # Emit user transcript to web client
                    socketio.emit('user_transcript', {
                        'text': text,
                        'final': True,
                        'session_id': self.session_id
                    })
                    
                    # Process the order when transcript is final
                    await self._update_cart_from_transcript(text)
                    
                elif delta:
                    # Incremental transcript with delta
                    if not hasattr(self, '_pending_user_input'):
                        self._pending_user_input = ""
                    self._pending_user_input += delta
                    
                    # Emit interim transcript without logging
                    socketio.emit('user_transcript', {
                        'text': self._pending_user_input,
                        'final': False,
                        'session_id': self.session_id
                    })
                    
                    if final:
                        # Reset pending input when final
                        self._pending_user_input = ""
                        
            elif role == "agent":
                # Handle agent transcripts - REDUCE CONSOLE SPAM
                if text:
                    # Process final agent responses
                    socketio.emit('agent_response', {
                        'text': text,
                        'final': True,
                        'session_id': self.session_id
                    })
                    
                    # Process agent confirmations for cart updates
                    if any(phrase in text.lower() for phrase in [
                        "confirm", "total order", "repeat that back", "removed", 
                        "now you have", "now you just have"
                    ]):
                        await self._update_cart_from_agent_confirmation(text)
                    
                elif delta:
                    # Handle deltas silently - only emit to client, don't log
                    if not hasattr(self, '_pending_agent_output'):
                        self._pending_agent_output = ""
                    self._pending_agent_output += delta
                    
                    # Emit to client without logging spam
                    socketio.emit('agent_response', {
                        'text': self._pending_agent_output,
                        'final': False,
                        'session_id': self.session_id
                    })
                    
                    if final:
                        self._pending_agent_output = ""
                
        elif msg_type == "state":
            state = msg.get("state")
            logger.info(f"🔄 State change: {state}")
            socketio.emit('voice_state', {
                'state': state,
                'session_id': self.session_id
            })
            
        else:
            logger.info(f"❓ Unhandled message type: {msg_type}")
    
    async def _update_cart_from_transcript(self, text: str):
        """Update cart from user transcript with NLP intent detection"""
        try:
            # Import NLP processor
            from nlp_processor import NLPProcessor
            
            # Create NLP processor for this session
            nlp = NLPProcessor(self.menu)
            
            # Detect intent
            intent, confidence = nlp.detect_intent(text)
            
            logger.info(f"🔍 Detected intent: {intent} (confidence: {confidence:.2f})")
            
            if intent == "remove":
                # Handle remove operation
                logger.info(f"➖ Processing remove operation...")
                result = nlp.process_cart_operation(text, self.cart)
                
                if result['success']:
                    logger.info(f"✅ {result['message']}")
                else:
                    logger.warning(f"⚠️ {result['message']}")
                    
            elif intent == "add":
                # Handle add operation using existing cart normalizer
                logger.info(f"➕ Processing add operation...")
                new_items_cart = self.cart_normalizer.parse_order(text)
                
                # Merge new items with existing cart instead of replacing
                for new_item in new_items_cart.items:
                    # Check if item already exists in cart
                    existing_item = None
                    for existing in self.cart.items:
                        if (existing.name == new_item.name and 
                            existing.size == new_item.size and 
                            set(existing.modifiers) == set(new_item.modifiers)):
                            existing_item = existing
                            break
                    
                    if existing_item:
                        # Increase quantity of existing item
                        existing_item.quantity += new_item.quantity
                        logger.info(f"🔄 Updated existing item: {existing_item.name} (quantity: {existing_item.quantity})")
                    else:
                        # Add new item to cart
                        self.cart.items.append(new_item)
                        logger.info(f"➕ Added new item: {new_item.name} (quantity: {new_item.quantity})")
                        
            elif intent == "query":
                # Handle query operation
                logger.info(f"❓ Processing query operation...")
                result = nlp.process_cart_operation(text, self.cart)
                logger.info(f"📋 Query result: {result['message']}")
                
            elif intent == "confirm":
                # Handle confirm operation
                logger.info(f"✅ Processing confirm operation...")
                # This will be handled by the confirm_order endpoint
                
            elif intent == "cancel":
                # Handle cancel operation
                logger.info(f"❌ Processing cancel operation...")
                self.clear_cart()
                
            else:
                # Unknown intent - try to parse as add
                logger.info(f"❓ Unknown intent, attempting to parse as add...")
                new_items_cart = self.cart_normalizer.parse_order(text)
                
                if new_items_cart.items:
                    for new_item in new_items_cart.items:
                        existing_item = None
                        for existing in self.cart.items:
                            if (existing.name == new_item.name and 
                                existing.size == new_item.size and 
                                set(existing.modifiers) == set(new_item.modifiers)):
                                existing_item = existing
                                break
                        
                        if existing_item:
                            existing_item.quantity += new_item.quantity
                            logger.info(f"🔄 Updated existing item: {existing_item.name} (quantity: {existing_item.quantity})")
                        else:
                            self.cart.items.append(new_item)
                            logger.info(f"➕ Added new item: {new_item.name} (quantity: {new_item.quantity})")
            
            # Recalculate total
            self.cart.total = sum(item.price * item.quantity for item in self.cart.items)
            
            # Emit cart update to web client
            socketio.emit('cart_update', {
                'cart': self.cart.to_dict(),
                'session_id': self.session_id
            })
            
            # Send cart update to agent to keep it in sync
            if self._loop and self.is_connected:
                asyncio.run_coroutine_threadsafe(
                    self.update_agent_cart(),
                    self._loop
                )
            
            logger.info(f"📊 Updated cart for session {self.session_id}: {len(self.cart.items)} items, total: ${self.cart.total:.2f}")
            
        except Exception as e:
            logger.error(f"Error updating cart: {e}")
            import traceback
            traceback.print_exc()
    
    async def _update_cart_from_agent_confirmation(self, text: str):
        """Update cart from agent confirmation using smart parser"""
        try:
            logger.info(f"🤖 Processing agent confirmation: '{text}'")
            
            # Use smart parser to extract items and determine if it's a removal
            items, is_removal = self.smart_parser.parse_agent_text(text)
            
            if is_removal and ("now you just have" in text.lower() or "now you have" in text.lower()):
                # Complete replacement - clear cart and add only what's mentioned
                logger.info("🔄 Complete cart replacement detected")
                self.cart = Cart()
                
                # Add the parsed items
                for item_data in items:
                    from cart_engine import CartItem
                    cart_item = CartItem(
                        name=item_data['name'],
                        quantity=item_data['quantity'],
                        price=item_data['price'],
                        size=item_data['size'],
                        modifiers=item_data['modifiers']
                    )
                    self.cart.items.append(cart_item)
                    logger.info(f"➕ Set final cart: {item_data['quantity']}x {item_data['size']} {item_data['name']}")
            
            # Recalculate total
            self.cart.total = sum(item.price * item.quantity for item in self.cart.items)
            
            # Emit cart update to web client
            socketio.emit('cart_update', {
                'cart': self.cart.to_dict(),
                'session_id': self.session_id
            })
            
            # Print clean cart summary
            self._print_cart_summary()
            
        except Exception as e:
            logger.error(f"❌ Error updating cart from agent confirmation: {e}")
    
    def clear_cart(self):
        """Clear the current cart for a new order"""
        self.cart = Cart()
        logger.info(f"🗑️ Cleared cart for session {self.session_id}")
        
        # Emit cart update to web client
        socketio.emit('cart_update', {
            'cart': self.cart.to_dict(),
            'session_id': self.session_id
        })
        
        # Send cart update to agent to keep it in sync
        if self._loop and self.is_connected:
            asyncio.run_coroutine_threadsafe(
                self.update_agent_cart(),
                self._loop
            )
    
    def confirm_order(self):
        """Confirm the current order and prepare for new one"""
        if not self.cart.items:
            return {"success": False, "message": "Cart is empty"}
        
        # Save order to history
        order_summary = {
            "timestamp": datetime.now().isoformat(),
            "items": [
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "size": item.size,
                    "modifiers": item.modifiers,
                    "total": item.price * item.quantity
                }
                for item in self.cart.items
            ],
            "total": self.cart.total,
            "status": "confirmed",
            "order_id": str(uuid.uuid4())[:8]
        }
        self.order_history.append(order_summary)
        
        # Store confirmed total before clearing
        confirmed_total = self.cart.total
        confirmed_items_count = len(self.cart.items)
        
        # Clear cart for next order
        self.clear_cart()
        
        logger.info(f"✅ Order confirmed for session {self.session_id}: ${confirmed_total:.2f}")
        
        return {
            "success": True, 
            "message": f"Order placed successfully! Total: ${confirmed_total:.2f}",
            "order": order_summary,
            "items_count": confirmed_items_count
        }
    
    def send_audio(self, audio_data: bytes):
        """Send audio data to Ultravox WebSocket (thread-safe)"""
        if self.is_connected and self._running:
            try:
                # Put audio data in queue for async processing
                self._audio_queue.put_nowait(audio_data)
                
                # Debug: Log audio stats occasionally
                if not hasattr(self, '_audio_send_count'):
                    self._audio_send_count = 0
                self._audio_send_count += 1
                
                if self._audio_send_count <= 10 or self._audio_send_count % 100 == 0:
                    logger.info(f"Queued audio chunk #{self._audio_send_count}, size: {len(audio_data)} bytes, queue size: {self._audio_queue.qsize()}")
                    
            except queue.Full:
                logger.warning("Audio queue is full, dropping audio data")
        else:
            logger.warning(f"Cannot send audio: connected={self.is_connected}, running={self._running}")
            if not hasattr(self, '_audio_reject_count'):
                self._audio_reject_count = 0
            self._audio_reject_count += 1
            if self._audio_reject_count <= 5:
                logger.warning(f"Audio rejected #{self._audio_reject_count} times")
    
    async def disconnect(self):
        """Disconnect from Ultravox WebSocket"""
        self._running = False
        if self.websocket:
            await self.websocket.close()
            self.is_connected = False
        self._stop_event_loop()
    
    def _print_cart_summary(self):
        """Print a clean cart summary to console"""
        print("\n" + "="*50)
        print("📋 CURRENT CART SUMMARY")
        print("="*50)
        if self.cart.items:
            for i, item in enumerate(self.cart.items, 1):
                print(f"{i}. {item.quantity}x {item.name} ({item.size}) - ${item.price * item.quantity:.2f}")
            print("-" * 30)
            print(f"💰 TOTAL: ${self.cart.total:.2f}")
        else:
            print("🛒 Cart is empty")
        print("="*50 + "\n")
    
    def _get_cart_summary(self):
        """Get cart summary as a string for the agent"""
        if not self.cart.items:
            return "The cart is currently empty."
        
        summary = "Current order:\n"
        for i, item in enumerate(self.cart.items, 1):
            size_str = f" ({item.size})" if item.size else ""
            modifiers_str = f" with {', '.join(item.modifiers)}" if item.modifiers else ""
            summary += f"- {item.quantity}x {item.name}{size_str}{modifiers_str} - ${item.price * item.quantity:.2f}\n"
        summary += f"Total: ${self.cart.total:.2f}"
        return summary
    
    async def update_agent_cart(self):
        """Send updated cart state to the agent"""
        try:
            if self.websocket and self.is_connected:
                cart_summary = self._get_cart_summary()
                update_message = {
                    "type": "system_message",
                    "content": f"Updated cart state:\n{cart_summary}\n\nPlease reference this cart when responding to the user."
                }
                await self.websocket.send(json.dumps(update_message))
                logger.info(f"📤 Sent cart update to agent")
        except Exception as e:
            logger.error(f"Error updating agent cart: {e}")

# Create async loop for WebSocket handling
def run_async_in_thread(coro):
    """Run async coroutine in a separate thread"""
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
        loop.close()
    
    thread = threading.Thread(target=run)
    thread.start()
    return thread

@app.route('/')
def index():
    """Main page with voice ordering interface"""
    return render_template('index_with_menu.html')

@app.route('/simple')
def simple_page():
    """Simple page without menu display"""
    return render_template('index_simple.html')

@app.route('/complex')
def complex_page():
    """Complex page with advanced features"""
    return render_template('index.html')

@app.route('/test')
def test_page():
    """Test page for debugging connection issues"""
    with open('test.html', 'r') as f:
        return f.read()

@app.route('/api/debug_sessions')
def debug_sessions():
    """Debug endpoint to check session state"""
    current_flask_session = dict(session)
    session_id = session.get('session_id')
    
    return jsonify({
        "current_flask_session": current_flask_session,
        "session_id_from_flask": session_id,
        "active_sessions": list(user_sessions.keys()),
        "session_details": {
            sid: {
                "menu": getattr(us.menu, 'name', 'unknown'),
                "cart_items": len(us.cart.items),
                "is_connected": us.is_connected,
                "join_url": us.join_url is not None,
                "order_history_count": len(us.order_history)
            }
            for sid, us in user_sessions.items()
        },
        "total_sessions": len(user_sessions)
    })

@app.route('/api/start_session')
def start_session():
    """Start a new ordering session with Ultravox"""
    # Check if we already have a session
    existing_session_id = session.get('session_id')
    menu_name = request.args.get('menu', 'small')
    
    if existing_session_id and existing_session_id in user_sessions:
        ultravox_session = user_sessions[existing_session_id]
        
        # Check if the session is still viable
        if ultravox_session.is_connected:
            logger.info(f"🔄 Reusing existing connected session: {existing_session_id}")
            return jsonify({
                "session_id": existing_session_id,
                "menu": menu_name,
                "menu_items": [
                    {
                        "sku": item.sku,
                        "name": item.name,
                        "price": item.price,
                        "category": item.category,
                        "aliases": item.aliases
                    }
                    for item in ultravox_session.menu.items
                ],
                "reused": True,
                "connected": True
            })
        else:
            # Session exists but not connected, clean it up and create new
            logger.info(f"🧹 Cleaning up disconnected session: {existing_session_id}")
            try:
                asyncio.run(ultravox_session.disconnect())
            except:
                pass
            del user_sessions[existing_session_id]
    
    # Clean up any old sessions that might be disconnected
    cleanup_old_sessions()
    
    # Create new session
    session_id = str(uuid.uuid4())
    
    # Create new Ultravox session
    ultravox_session = UltravoxVoiceSession(session_id, menu_name)
    user_sessions[session_id] = ultravox_session
    
    session['session_id'] = session_id
    
    logger.info(f"➕ Created new session: {session_id}, Total sessions: {len(user_sessions)}")
    
    return jsonify({
        "session_id": session_id,
        "menu": menu_name,
        "menu_items": [
            {
                "sku": item.sku,
                "name": item.name,
                "price": item.price,
                "category": item.category,
                "aliases": item.aliases
            }
            for item in ultravox_session.menu.items
        ],
        "reused": False,
        "connected": False
    })

@app.route('/api/connect_ultravox', methods=['POST'])
def connect_ultravox():
    """Connect to Ultravox WebSocket"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "No active session"}), 400
    
    ultravox_session = user_sessions[session_id]
    
    # Run async connection in background
    def connect_async():
        async def run():
            success = await ultravox_session.connect_websocket()
            socketio.emit('ultravox_connection', {
                'success': success,
                'session_id': session_id
            })
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run())
        loop.close()
    
    thread = threading.Thread(target=connect_async)
    thread.start()
    
    return jsonify({"success": True, "message": "Connecting to Ultravox..."})

@app.route('/api/send_audio', methods=['POST'])
def send_audio():
    """Send audio data to Ultravox"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "No active session"}), 400
    
    ultravox_session = user_sessions[session_id]
    
    if not ultravox_session.is_connected:
        return jsonify({"error": "Not connected to Ultravox"}), 400
    
    # Get audio data from request
    audio_data = request.get_json().get('audio_data')
    if not audio_data:
        return jsonify({"error": "No audio data provided"}), 400
    
    try:
        # Decode base64 audio data
        audio_bytes = base64.b64decode(audio_data)
        
        # Send to Ultravox in background
        def send_async():
            async def run():
                await ultravox_session.send_audio(audio_bytes)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run())
            loop.close()
        
        thread = threading.Thread(target=send_async)
        thread.start()
        
        return jsonify({"success": True})
        
    except Exception as e:
        logger.error(f"Error sending audio: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get_cart')
def get_cart():
    """Get current cart state"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "No active session"}), 400
    
    ultravox_session = user_sessions[session_id]
    
    return jsonify({
        "cart": ultravox_session.cart.to_dict(),
        "history": ultravox_session.order_history
    })

@app.route('/api/clear_cart', methods=['POST'])
def clear_cart():
    """Clear the current cart"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "No active session"}), 400
    
    ultravox_session = user_sessions[session_id]
    ultravox_session.clear_cart()
    
    return jsonify({"success": True, "cart": ultravox_session.cart.to_dict()})

@app.route('/api/confirm_order', methods=['POST'])
def confirm_order():
    """Confirm the current order and start fresh session"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "No active session"}), 400
    
    ultravox_session = user_sessions[session_id]
    result = ultravox_session.confirm_order()
    
    if result["success"]:
        # Emit success notification to client
        socketio.emit('order_confirmed', {
            'success': True,
            'message': result["message"],
            'order': result["order"],
            'session_id': session_id
        })
        
        # Emit order history update
        socketio.emit('order_history_update', {
            'history': ultravox_session.order_history,
            'session_id': session_id
        })
        
        # Disconnect from current Ultravox session to prepare for new order
        try:
            asyncio.run(ultravox_session.disconnect())
            ultravox_session.is_connected = False
            logger.info(f"🔄 Disconnected session {session_id} after order confirmation")
        except Exception as e:
            logger.warning(f"⚠️ Error disconnecting session after order: {e}")
        
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/update_item_quantity', methods=['POST'])
def update_item_quantity():
    """Update quantity of a specific item in cart"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "No active session"}), 400
    
    data = request.get_json()
    item_index = data.get('item_index')
    new_quantity = data.get('quantity')
    
    if item_index is None or new_quantity is None:
        return jsonify({"error": "Missing item_index or quantity"}), 400
    
    ultravox_session = user_sessions[session_id]
    
    try:
        if 0 <= item_index < len(ultravox_session.cart.items):
            if new_quantity <= 0:
                # Remove item if quantity is 0 or less
                removed_item = ultravox_session.cart.items.pop(item_index)
                logger.info(f"🗑️ Removed item: {removed_item.name}")
            else:
                # Update quantity
                ultravox_session.cart.items[item_index].quantity = new_quantity
                logger.info(f"🔄 Updated quantity: {ultravox_session.cart.items[item_index].name} = {new_quantity}")
            
            # Recalculate total
            ultravox_session.cart.total = sum(item.price * item.quantity for item in ultravox_session.cart.items)
            
            # Emit update
            socketio.emit('cart_update', {
                'cart': ultravox_session.cart.to_dict(),
                'session_id': session_id
            })
            
            return jsonify({"success": True, "cart": ultravox_session.cart.to_dict()})
        else:
            return jsonify({"error": "Invalid item index"}), 400
            
    except Exception as e:
        logger.error(f"Error updating item quantity: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get_order_history')
def get_order_history():
    """Get order history for the session"""
    session_id = session.get('session_id')
    
    if not session_id:
        # If no session, return empty history instead of error
        return jsonify({
            "history": [],
            "current_cart": {"items": [], "total": 0.0}
        })
    
    if session_id not in user_sessions:
        # If session doesn't exist in memory, return empty history
        return jsonify({
            "history": [],
            "current_cart": {"items": [], "total": 0.0}
        })
    
    ultravox_session = user_sessions[session_id]
    
    return jsonify({
        "history": ultravox_session.order_history,
        "current_cart": ultravox_session.cart.to_dict()
    })

@app.route('/api/process_transcript', methods=['POST'])
def process_transcript():
    """Process a transcript from the UI (for menu item clicks) with NLP intent detection"""
    data = request.get_json()
    session_id = data.get('session_id') or session.get('session_id')
    transcript = data.get('transcript', '')
    
    if not session_id or session_id not in user_sessions:
        return jsonify({"error": "No active session"}), 400
    
    if not transcript:
        return jsonify({"error": "No transcript provided"}), 400
    
    ultravox_session = user_sessions[session_id]
    
    try:
        # Import NLP processor
        from nlp_processor import NLPProcessor
        
        # Create NLP processor for this session
        nlp = NLPProcessor(ultravox_session.menu)
        
        # Detect intent
        intent, confidence = nlp.detect_intent(transcript)
        
        logger.info(f"🔍 Detected intent: {intent} (confidence: {confidence:.2f})")
        
        if intent == "remove":
            # Handle remove operation
            logger.info(f"➖ Processing remove operation...")
            result = nlp.process_cart_operation(transcript, ultravox_session.cart)
            
            if result['success']:
                message = result['message']
            else:
                message = result['message']
                
        elif intent == "add":
            # Handle add operation using existing cart normalizer
            logger.info(f"➕ Processing add operation...")
            new_items_cart = ultravox_session.cart_normalizer.parse_order(transcript)
            
            # Merge new items with existing cart
            for new_item in new_items_cart.items:
                # Check if item already exists in cart
                existing_item = None
                for existing in ultravox_session.cart.items:
                    if (existing.name == new_item.name and 
                        existing.size == new_item.size and 
                        set(existing.modifiers) == set(new_item.modifiers)):
                        existing_item = existing
                        break
                
                if existing_item:
                    # Increase quantity of existing item
                    existing_item.quantity += new_item.quantity
                    logger.info(f"🔄 Updated existing item: {existing_item.name} (quantity: {existing_item.quantity})")
                else:
                    # Add new item to cart
                    ultravox_session.cart.items.append(new_item)
                    logger.info(f"➕ Added new item: {new_item.name} (quantity: {new_item.quantity})")
            
            message = "Item added successfully"
            
        elif intent == "query":
            # Handle query operation
            logger.info(f"❓ Processing query operation...")
            result = nlp.process_cart_operation(transcript, ultravox_session.cart)
            message = result['message']
            
        elif intent == "confirm":
            # Handle confirm operation
            logger.info(f"✅ Processing confirm operation...")
            message = "Order confirmed"
            
        elif intent == "cancel":
            # Handle cancel operation
            logger.info(f"❌ Processing cancel operation...")
            ultravox_session.clear_cart()
            message = "Order cancelled"
            
        else:
            # Unknown intent - try to parse as add
            logger.info(f"❓ Unknown intent, attempting to parse as add...")
            new_items_cart = ultravox_session.cart_normalizer.parse_order(transcript)
            
            if new_items_cart.items:
                for new_item in new_items_cart.items:
                    existing_item = None
                    for existing in ultravox_session.cart.items:
                        if (existing.name == new_item.name and 
                            existing.size == new_item.size and 
                            set(existing.modifiers) == set(new_item.modifiers)):
                            existing_item = existing
                            break
                    
                    if existing_item:
                        existing_item.quantity += new_item.quantity
                        logger.info(f"🔄 Updated existing item: {existing_item.name} (quantity: {existing_item.quantity})")
                    else:
                        ultravox_session.cart.items.append(new_item)
                        logger.info(f"➕ Added new item: {new_item.name} (quantity: {new_item.quantity})")
            
            message = "Item processed"
        
        # Recalculate total
        ultravox_session.cart.total = sum(item.price * item.quantity for item in ultravox_session.cart.items)
        
        # Emit cart update to web client
        socketio.emit('cart_update', {
            'cart': ultravox_session.cart.to_dict(),
            'session_id': session_id
        })
        
        # Send cart update to agent to keep it in sync
        if ultravox_session._loop and ultravox_session.is_connected:
            asyncio.run_coroutine_threadsafe(
                ultravox_session.update_agent_cart(),
                ultravox_session._loop
            )
        
        logger.info(f"📊 Updated cart for session {session_id}: {len(ultravox_session.cart.items)} items, total: ${ultravox_session.cart.total:.2f}")
        
        return jsonify({
            "success": True,
            "message": message,
            "cart": ultravox_session.cart.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error processing transcript: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/reset_sessions', methods=['POST'])
def reset_sessions():
    """Reset all sessions and clean up connections"""
    try:
        # Disconnect all sessions
        for session_id, ultravox_session in list(user_sessions.items()):
            try:
                asyncio.run(ultravox_session.disconnect())
            except:
                pass
            
        # Clear all sessions
        user_sessions.clear()
        
        # Clear Flask session
        session.clear()
        
        logger.info("🔄 All sessions reset successfully")
        
        return jsonify({
            "success": True,
            "message": "All sessions reset successfully",
            "active_sessions": 0
        })
        
    except Exception as e:
        logger.error(f"❌ Error resetting sessions: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('status', {'msg': 'Connected to Dr. Donut Voice Ordering'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('start_ultravox')
def handle_start_ultravox(data):
    """Handle request to start Ultravox connection"""
    # Get session_id from the data payload instead of Flask session
    session_id = data.get('session_id')
    
    logger.info(f"🚀 Received start_ultravox request for session: {session_id}")
    logger.info(f"📊 Available sessions: {list(user_sessions.keys())}")
    
    if not session_id or session_id not in user_sessions:
        error_msg = f'❌ No active session found for {session_id}. Available sessions: {list(user_sessions.keys())}'
        logger.error(error_msg)
        emit('error', {'msg': error_msg})
        return
    
    ultravox_session = user_sessions[session_id]
    
    emit('status', {'msg': '🔄 Connecting to Ultravox...'})
    
    # Run async connection in background thread with proper error handling
    def connect_async():
        try:
            logger.info(f"🔧 Starting connection thread for session {session_id}")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def run():
                logger.info(f"🎯 Attempting WebSocket connection for {session_id}")
                success = await ultravox_session.connect_websocket()
                logger.info(f"📡 Connection result for {session_id}: {success}")
                return success
            
            success = loop.run_until_complete(run())
            
            logger.info(f"✅ Ultravox connection result for {session_id}: {success}")
            
            # Emit the result
            with app.app_context():
                if success:
                    socketio.emit('ultravox_connection', {
                        'success': True,
                        'session_id': session_id,
                        'message': 'Connected to Ultravox! You can now start speaking.'
                    })
                else:
                    socketio.emit('error', {
                        'msg': 'Failed to connect to Ultravox. Please try again.'
                    })
                
        except Exception as e:
            logger.error(f"💥 Error in connect_async for {session_id}: {e}")
            with app.app_context():
                socketio.emit('error', {'msg': f'Connection failed: {str(e)}'})
        finally:
            if 'loop' in locals():
                loop.close()
                logger.info(f"🔚 Closed event loop for session {session_id}")
    
    thread = threading.Thread(target=connect_async, daemon=True)
    thread.start()
    logger.info(f"🧵 Started connection thread for session {session_id}")

@socketio.on('audio_data')
def handle_audio_data(data):
    """Handle audio data from client"""
    # Get session_id from the data payload
    session_id = data.get('session_id')
    
    # Debug: Log audio occasionally, not every time
    if not hasattr(handle_audio_data, 'audio_count'):
        handle_audio_data.audio_count = 0
    handle_audio_data.audio_count += 1
    
    # Only log every 100th audio chunk
    if handle_audio_data.audio_count % 100 == 0:
        logger.info(f"📡 Processed {handle_audio_data.audio_count} audio chunks for session: {session_id}")
    
    # Validate session
    if not session_id:
        logger.error('❌ No session_id provided in audio data')
        emit('error', {'msg': 'No session_id provided'})
        return
        
    if session_id not in user_sessions:
        # Try to get from Flask session as fallback
        fallback_session_id = session.get('session_id')
        if fallback_session_id and fallback_session_id in user_sessions:
            session_id = fallback_session_id
            logger.info(f"🔄 Using fallback session: {session_id}")
        else:
            logger.error(f'❌ No active session found for {session_id}. Available: {list(user_sessions.keys())}')
            emit('error', {'msg': f'Session {session_id} not found. Please refresh and try again.'})
            return
    
    ultravox_session = user_sessions[session_id]
    
    if not ultravox_session.is_connected:
        logger.error(f'❌ Session {session_id} not connected to Ultravox')
        emit('error', {'msg': 'Not connected to Ultravox'})
        return
    
    try:
        # Get and decode audio data
        audio_data_b64 = data.get('audio')
        if not audio_data_b64:
            emit('error', {'msg': 'No audio data provided'})
            return
        
        audio_bytes = base64.b64decode(audio_data_b64)
        
        # Send audio using the thread-safe method
        ultravox_session.send_audio(audio_bytes)
        
    except Exception as e:
        logger.error(f"❌ Error handling audio data: {e}")
        emit('error', {'msg': f'Error processing audio: {str(e)}'})

def cleanup_old_sessions():
    """Clean up old disconnected sessions"""
    to_remove = []
    for session_id, ultravox_session in user_sessions.items():
        try:
            # Check if session is still viable
            if not ultravox_session.is_connected and ultravox_session.join_url is None:
                logger.info(f"🧹 Marking session for cleanup: {session_id}")
                to_remove.append(session_id)
            elif not ultravox_session.is_connected:
                # Try to reconnect if we have a join_url
                logger.info(f"⚠️ Session {session_id} has join_url but not connected")
        except Exception as e:
            logger.warning(f"⚠️ Error checking session {session_id}: {e}")
            to_remove.append(session_id)
    
    # Remove old sessions
    for session_id in to_remove:
        try:
            if session_id in user_sessions:
                ultravox_session = user_sessions[session_id]
                asyncio.run(ultravox_session.disconnect())
                del user_sessions[session_id]
                logger.info(f"🗑️ Cleaned up session: {session_id}")
        except Exception as e:
            logger.warning(f"⚠️ Error cleaning up session {session_id}: {e}")
    
    if to_remove:
        logger.info(f"🧹 Cleaned up {len(to_remove)} old sessions, {len(user_sessions)} remaining")

if __name__ == '__main__':
    # Set up environment
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print(f"""
🍩 Dr. Donut Voice Ordering System (Ultravox Powered)
=====================================================
🌐 Web Interface: http://localhost:{port}
🎤 Voice-enabled cart normalization via Ultravox API
📱 Real-time cart updates
🔊 Real-time ASR and TTS
    """)
    
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)