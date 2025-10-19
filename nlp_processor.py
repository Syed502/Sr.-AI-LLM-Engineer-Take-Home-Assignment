#!/usr/bin/env python3
"""
Robust NLP/NLU Processor for Voice Ordering
Handles intent detection, entity extraction, and cart operations
"""

import re
import logging
from typing import Dict, List, Tuple, Optional
from cart_engine import Cart, CartItem
from menu_data import Menu

logger = logging.getLogger(__name__)

class IntentType:
    """Intent types for user utterances"""
    ADD = "add"
    REMOVE = "remove"
    MODIFY = "modify"
    QUERY = "query"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    UNKNOWN = "unknown"

class NLPProcessor:
    """Advanced NLP processor for understanding user intent and extracting cart operations"""
    
    def __init__(self, menu: Menu):
        self.menu = menu
        self._setup_patterns()
    
    def _setup_patterns(self):
        """Setup regex patterns for intent detection"""
        
        # Add intent patterns
        self.add_patterns = [
            r'\b(add|get|give|want|like|need|order|have|take)\b',
            r'\b(I\'d like|I would like|I want|I need|I\'ll take|I\'ll have)\b',
            r'\b(can I get|could I get|may I have)\b',
        ]
        
        # Remove intent patterns
        self.remove_patterns = [
            r'\b(remove|delete|take out|take off|don\'t want|don\'t need|cancel|scratch)\b',
            r'\b(no|not|without)\b',
            r'\b(change my mind|never mind|forget)\b',
        ]
        
        # Modify intent patterns
        self.modify_patterns = [
            r'\b(change|modify|update|switch|replace|instead)\b',
            r'\b(make it|make that)\b',
        ]
        
        # Query intent patterns
        self.query_patterns = [
            r'\b(what|how much|how many|total|price|cost)\b',
            r'\b(do I have|what\'s in|show me)\b',
        ]
        
        # Confirm intent patterns
        self.confirm_patterns = [
            r'\b(yes|yeah|yep|correct|right|that\'s right|sounds good|perfect)\b',
            r'\b(confirm|proceed|go ahead|place order)\b',
            r'\b(confirm my order|confirm the order|place the order|finalize|pay)\b',
        ]
        
        # Cancel intent patterns
        self.cancel_patterns = [
            r'\b(cancel|stop|abort|never mind|forget it)\b',
        ]
        
        # Quantity patterns
        self.quantity_patterns = [
            r'\b(one|two|three|four|five|six|seven|eight|nine|ten)\b',
            r'\b(\d+)\b',
        ]
        
        # Size patterns
        self.size_patterns = [
            r'\b(small|medium|large|regular|venti|grande)\b',
        ]
    
    def detect_intent(self, text: str) -> Tuple[str, float]:
        """
        Detect the intent of the user utterance
        Returns: (intent_type, confidence)
        """
        text_lower = text.lower()
        
        # PRIORITY CHECK: Look for explicit remove keywords first
        # This prevents "I would like to remove" from being detected as "add"
        if any(keyword in text_lower for keyword in ["remove", "delete", "take out", "take off", "don't want", "don't need", "cancel", "scratch"]):
            # Double-check it's not a false positive
            if "remove" in text_lower or "delete" in text_lower or "take out" in text_lower:
                logger.info(f"🎯 Priority match: REMOVE detected (keyword found)")
                return IntentType.REMOVE, 0.95
        
        # PRIORITY CHECK: Look for explicit add keywords
        if any(keyword in text_lower for keyword in ["add", "get", "want", "need", "order", "have", "take"]):
            # Make sure it's not "don't want" or "don't need"
            if not any(phrase in text_lower for phrase in ["don't want", "don't need", "don't have"]):
                logger.info(f"🎯 Priority match: ADD detected (keyword found)")
                return IntentType.ADD, 0.90
        
        # PRIORITY CHECK: Look for explicit confirm keywords
        if any(keyword in text_lower for keyword in ["confirm", "yes", "yeah", "correct", "right", "that's right"]):
            logger.info(f"🎯 Priority match: CONFIRM detected (keyword found)")
            return IntentType.CONFIRM, 0.85
        
        # Check each intent type and calculate confidence
        intent_scores = {
            IntentType.ADD: self._calculate_intent_score(text_lower, self.add_patterns),
            IntentType.REMOVE: self._calculate_intent_score(text_lower, self.remove_patterns),
            IntentType.MODIFY: self._calculate_intent_score(text_lower, self.modify_patterns),
            IntentType.QUERY: self._calculate_intent_score(text_lower, self.query_patterns),
            IntentType.CONFIRM: self._calculate_intent_score(text_lower, self.confirm_patterns),
            IntentType.CANCEL: self._calculate_intent_score(text_lower, self.cancel_patterns),
        }
        
        # Get the highest scoring intent
        best_intent = max(intent_scores.items(), key=lambda x: x[1])
        
        # Log all scores for debugging
        logger.info(f"📊 Intent scores: {intent_scores}")
        
        # If confidence is too low, return unknown
        if best_intent[1] < 0.3:
            logger.warning(f"⚠️ Low confidence intent: {best_intent[0]} ({best_intent[1]:.2f})")
            return IntentType.UNKNOWN, best_intent[1]
        
        return best_intent
    
    def _calculate_intent_score(self, text: str, patterns: List[str]) -> float:
        """Calculate confidence score for an intent based on pattern matches"""
        matches = 0
        for pattern in patterns:
            if re.search(pattern, text):
                matches += 1
        return matches / len(patterns) if patterns else 0.0
    
    def extract_quantity(self, text: str) -> int:
        """Extract quantity from text"""
        text_lower = text.lower()
        
        # Number words to digits
        number_map = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        
        # Check for number words
        for word, num in number_map.items():
            if word in text_lower:
                return num
        
        # Check for digits
        digit_match = re.search(r'\b(\d+)\b', text)
        if digit_match:
            return int(digit_match.group(1))
        
        # Default to 1 if no quantity mentioned
        return 1
    
    def extract_size(self, text: str) -> Optional[str]:
        """Extract size from text"""
        text_lower = text.lower()
        
        size_map = {
            'small': 'small',
            'medium': 'medium',
            'large': 'large',
            'regular': 'medium',
            'venti': 'large',
            'grande': 'large'
        }
        
        for keyword, size in size_map.items():
            if keyword in text_lower:
                return size
        
        return None
    
    def extract_menu_item(self, text: str) -> Optional[Dict]:
        """Extract menu item from text"""
        text_lower = text.lower()
        
        # Try to match against menu items
        for item in self.menu.items:
            # Check exact name match
            if item.name.lower() in text_lower:
                return {
                    'sku': item.sku,
                    'name': item.name,
                    'price': item.price,
                    'aliases': item.aliases
                }
            
            # Check aliases
            for alias in item.aliases:
                if alias.lower() in text_lower:
                    return {
                        'sku': item.sku,
                        'name': item.name,
                        'price': item.price,
                        'aliases': item.aliases
                    }
        
        return None
    
    def process_cart_operation(self, text: str, current_cart: Cart) -> Dict:
        """
        Process a cart operation based on user utterance
        Returns: {
            'operation': 'add' | 'remove' | 'modify' | 'query',
            'items': [CartItem],
            'message': str,
            'success': bool
        }
        """
        intent, confidence = self.detect_intent(text)
        
        logger.info(f"🔍 Intent detected: {intent} (confidence: {confidence:.2f})")
        logger.info(f"📝 Processing text: '{text}'")
        
        if intent == IntentType.REMOVE:
            return self._process_remove(text, current_cart)
        elif intent == IntentType.ADD:
            return self._process_add(text, current_cart)
        elif intent == IntentType.MODIFY:
            return self._process_modify(text, current_cart)
        elif intent == IntentType.QUERY:
            return self._process_query(current_cart)
        elif intent == IntentType.CONFIRM:
            return {'operation': 'confirm', 'success': True, 'message': 'Order confirmed'}
        elif intent == IntentType.CANCEL:
            return {'operation': 'cancel', 'success': True, 'message': 'Order cancelled'}
        else:
            return {'operation': 'unknown', 'success': False, 'message': f'Could not understand: {text}'}
    
    def _process_add(self, text: str, current_cart: Cart) -> Dict:
        """Process add operation"""
        try:
            menu_item = self.extract_menu_item(text)
            if not menu_item:
                return {
                    'operation': 'add',
                    'success': False,
                    'message': 'Could not identify the menu item',
                    'items': []
                }
            
            quantity = self.extract_quantity(text)
            size = self.extract_size(text) or 'medium'
            
            # Create cart item
            cart_item = CartItem(
                sku=menu_item['sku'],
                name=menu_item['name'],
                quantity=quantity,
                price=menu_item['price'],
                size=size,
                modifiers=[]
            )
            
            logger.info(f"➕ Adding item: {quantity}x {menu_item['name']} ({size})")
            
            return {
                'operation': 'add',
                'success': True,
                'message': f'Added {quantity}x {menu_item["name"]}',
                'items': [cart_item]
            }
            
        except Exception as e:
            logger.error(f"Error processing add operation: {e}")
            return {
                'operation': 'add',
                'success': False,
                'message': f'Error adding item: {str(e)}',
                'items': []
            }
    
    def _process_remove(self, text: str, current_cart: Cart) -> Dict:
        """Process remove operation with enhanced logic"""
        try:
            text_lower = text.lower()
            
            # Check for "remove all" or "remove all X"
            if "remove all" in text_lower or "take out all" in text_lower or "delete all" in text_lower:
                menu_item = self.extract_menu_item(text)
                if menu_item:
                    # Remove all instances of this item
                    items_to_remove = [item for item in current_cart.items if item.name == menu_item['name']]
                    for item in items_to_remove:
                        current_cart.items.remove(item)
                    
                    if items_to_remove:
                        logger.info(f"➖ Removed all {menu_item['name']} from cart")
                        return {
                            'operation': 'remove',
                            'success': True,
                            'message': f'Removed all {menu_item["name"]}',
                            'items': []
                        }
            
            # Check for "just keep one" or "keep only one"
            if "just keep" in text_lower or "keep only" in text_lower or "only keep" in text_lower:
                menu_item = self.extract_menu_item(text)
                if menu_item:
                    # Find all instances of this item
                    items_to_adjust = [item for item in current_cart.items if item.name == menu_item['name']]
                    
                    if items_to_adjust:
                        # Keep only the first one, remove the rest
                        total_quantity = sum(item.quantity for item in items_to_adjust)
                        
                        # Remove all instances
                        for item in items_to_adjust:
                            current_cart.items.remove(item)
                        
                        # Add back just one
                        if items_to_adjust:
                            first_item = items_to_adjust[0]
                            first_item.quantity = 1
                            current_cart.items.append(first_item)
                        
                        logger.info(f"➖ Reduced {menu_item['name']} from {total_quantity} to 1")
                        return {
                            'operation': 'remove',
                            'success': True,
                            'message': f'Kept only 1 {menu_item["name"]}',
                            'items': []
                        }
            
            # Regular remove operation
            menu_item = self.extract_menu_item(text)
            if not menu_item:
                return {
                    'operation': 'remove',
                    'success': False,
                    'message': 'Could not identify the menu item to remove',
                    'items': []
                }
            
            quantity = self.extract_quantity(text)
            size = self.extract_size(text)
            
            # Find matching items in cart
            items_to_remove = []
            for item in current_cart.items:
                if (item.name == menu_item['name'] and 
                    (size is None or item.size == size)):
                    
                    if item.quantity > quantity:
                        # Reduce quantity
                        item.quantity -= quantity
                        logger.info(f"➖ Removed {quantity}x {menu_item['name']} (now {item.quantity} remaining)")
                        return {
                            'operation': 'remove',
                            'success': True,
                            'message': f'Removed {quantity}x {menu_item["name"]}',
                            'items': []
                        }
                    else:
                        # Remove all of this item
                        logger.info(f"➖ Removed all {item.quantity}x {menu_item['name']}")
                        items_to_remove.append(item)
            
            # Remove items that have zero quantity
            for item in items_to_remove:
                current_cart.items.remove(item)
            
            if items_to_remove:
                return {
                    'operation': 'remove',
                    'success': True,
                    'message': f'Removed {menu_item["name"]}',
                    'items': []
                }
            else:
                return {
                    'operation': 'remove',
                    'success': False,
                    'message': f'{menu_item["name"]} not found in cart',
                    'items': []
                }
            
        except Exception as e:
            logger.error(f"Error processing remove operation: {e}")
            import traceback
            traceback.print_exc()
            return {
                'operation': 'remove',
                'success': False,
                'message': f'Error removing item: {str(e)}',
                'items': []
            }
    
    def _process_modify(self, text: str, current_cart: Cart) -> Dict:
        """Process modify operation"""
        # For now, treat modify as remove + add
        return {
            'operation': 'modify',
            'success': False,
            'message': 'Modify operation not yet implemented',
            'items': []
        }
    
    def _process_query(self, current_cart: Cart) -> Dict:
        """Process query operation"""
        if not current_cart.items:
            return {
                'operation': 'query',
                'success': True,
                'message': 'Your cart is empty',
                'items': []
            }
        
        items_summary = []
        for item in current_cart.items:
            items_summary.append(f"{item.quantity}x {item.name}")
        
        message = f"Your order: {', '.join(items_summary)}. Total: ${current_cart.total:.2f}"
        
        return {
            'operation': 'query',
            'success': True,
            'message': message,
            'items': []
        }

