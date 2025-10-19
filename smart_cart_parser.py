#!/usr/bin/env python3
"""
Advanced Cart Parser using NLP
Handles complex order parsing and cart management
"""

import re
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

class SmartCartParser:
    """Advanced cart parser using NLP techniques"""
    
    def __init__(self, menu):
        self.menu = menu
        self.quantity_map = {
            'zero': 0, 'no': 0, 'none': 0,
            'one': 1, 'a': 1, 'an': 1, 'single': 1,
            'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'dozen': 12
        }
        
        # Item patterns with more flexible matching
        self.item_patterns = [
            # Coffee patterns
            (r'(zero|no|none|one|a|an|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)?\s*(large|medium|small)?\s*regular\s+brewed\s+coffee[s]?', 'Regular Brewed Coffee'),
            (r'(zero|no|none|one|a|an|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)?\s*(large|medium|small)?\s*pumpkin\s+spice\s+latte[s]?', 'Pumpkin Spice Latte'),
            (r'(zero|no|none|one|a|an|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)?\s*(large|medium|small)?\s*latte[s]?(?!\s*(?:pumpkin|spice))', 'Latte'),
            # Donut patterns  
            (r'(zero|no|none|one|a|an|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)?\s*pumpkin\s+spice\s+iced\s+doughnut[s]?', 'Pumpkin Spice Iced Doughnut'),
            (r'(zero|no|none|one|a|an|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)?\s*chocolate\s+iced\s+doughnut[s]?', 'Chocolate Iced Doughnut'),
            (r'(zero|no|none|one|a|an|single|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)?\s*raspberry\s+filled\s+doughnut[s]?', 'Raspberry Filled Doughnut'),
        ]
    
    def parse_agent_text(self, text: str) -> Tuple[List[Dict], bool]:
        """Parse agent text and return items and whether it's a removal"""
        text_lower = text.lower()
        is_removal = any(phrase in text_lower for phrase in [
            "removed", "removing", "taking out", "now you just have", 
            "only have", "took off", "deleted"
        ])
        
        # Check for final state indicators
        is_final_state = any(phrase in text_lower for phrase in [
            "now you just have", "now you have", "your order is now",
            "you only have", "that leaves you with"
        ])
        
        items = []
        
        if is_final_state:
            # Extract text after the final state phrase
            for phrase in ["now you just have", "now you have", "your order is now", "you only have", "that leaves you with"]:
                if phrase in text_lower:
                    remaining_text = text_lower.split(phrase)[1]
                    items = self._extract_items_from_text(remaining_text)
                    break
        else:
            # Parse all items mentioned
            items = self._extract_items_from_text(text_lower)
        
        return items, is_removal
    
    def _extract_items_from_text(self, text: str) -> List[Dict]:
        """Extract items from text using patterns"""
        items = []
        
        for pattern, item_name in self.item_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    quantity_str = match[0] if match[0] else 'one'
                    size = match[1] if len(match) > 1 and match[1] else 'regular'
                else:
                    quantity_str = 'one'
                    size = 'regular'
                
                # Convert quantity
                if quantity_str.isdigit():
                    quantity = int(quantity_str)
                else:
                    quantity = self.quantity_map.get(quantity_str, 1)
                
                # Skip zero quantities
                if quantity <= 0:
                    continue
                
                # Find matching menu item
                for menu_item in self.menu.items:
                    if item_name.lower() in menu_item.name.lower():
                        items.append({
                            'name': menu_item.name,
                            'quantity': quantity,
                            'price': menu_item.price,
                            'size': size if size in ['small', 'medium', 'large'] else 'regular',
                            'modifiers': []
                        })
                        logger.info(f"🔍 Parsed: {quantity}x {size} {menu_item.name}")
                        break
        
        return items

if __name__ == "__main__":
    # Test the parser
    from menu_data import get_menu
    
    menu = get_menu('small')
    parser = SmartCartParser(menu)
    
    test_texts = [
        "I've removed the large Regular Brewed Coffee from your order, so now you just have a Pumpkin Spice Latte.",
        "So I'm updating your order to two small regular brewed coffees, two medium regular brewed coffees, and one large regular brewed coffee.",
        "You now have a Pumpkin Spice Latte and one large Regular Brewed Coffee."
    ]
    
    for text in test_texts:
        print(f"\nTesting: {text}")
        items, is_removal = parser.parse_agent_text(text)
        print(f"Items: {items}")
        print(f"Is removal: {is_removal}")