"""
Cart normalization engine for Dr. Donut drive-thru ordering system.
Implements alias resolution, size mapping, modifier normalization, and cart state management.
Version 2: Simplified and more robust approach.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from menu_data import Menu, MenuItem, get_menu


logger = logging.getLogger(__name__)


@dataclass
class CartItem:
    """Represents a single item in the cart."""
    sku: str
    name: str
    quantity: int = 1
    size: Optional[str] = None
    modifiers: List[str] = field(default_factory=list)
    price: float = 0.0
    
    def __hash__(self):
        """Make CartItem hashable for duplicate detection."""
        return hash((self.sku, self.size, tuple(sorted(self.modifiers))))
    
    def __eq__(self, other):
        """Check if two cart items are identical."""
        if not isinstance(other, CartItem):
            return False
        return (self.sku == other.sku and 
                self.size == other.size and 
                set(self.modifiers) == set(other.modifiers))


@dataclass
class Cart:
    """Shopping cart with items and total."""
    items: List[CartItem] = field(default_factory=list)
    total: float = 0.0
    
    def add_item(self, item: CartItem):
        """Add an item to the cart."""
        self.items.append(item)
        self.total += item.price * item.quantity
    
    def remove_item(self, index: int):
        """Remove an item from the cart."""
        if 0 <= index < len(self.items):
            item = self.items.pop(index)
            self.total -= item.price * item.quantity
    
    def update_item(self, index: int, item: CartItem):
        """Update an item in the cart."""
        if 0 <= index < len(self.items):
            old_item = self.items[index]
            self.total -= old_item.price * old_item.quantity
            self.items[index] = item
            self.total += item.price * item.quantity
    
    def merge_duplicates(self):
        """Merge duplicate items in the cart."""
        merged = {}
        for item in self.items:
            key = (item.sku, item.size, tuple(sorted(item.modifiers)))
            if key in merged:
                merged[key].quantity += item.quantity
            else:
                merged[key] = CartItem(
                    sku=item.sku,
                    name=item.name,
                    quantity=item.quantity,
                    size=item.size,
                    modifiers=item.modifiers.copy(),
                    price=item.price
                )
        self.items = list(merged.values())
        self.total = sum(item.price * item.quantity for item in self.items)
    
    def to_dict(self) -> Dict:
        """Convert cart to dictionary for JSON serialization."""
        return {
            "items": [
                {
                    "sku": item.sku,
                    "name": item.name,
                    "quantity": item.quantity,
                    "size": item.size,
                    "modifiers": item.modifiers,
                    "price": item.price
                }
                for item in self.items
            ],
            "total": round(self.total, 2)
        }


class CartNormalizer:
    """
    Normalizes user input into structured cart items.
    Handles aliases, size synonyms, modifiers, and quantities.
    """
    
    def __init__(self, menu: Menu):
        self.menu = menu
        self._build_indexes()
    
    def _build_indexes(self):
        """Build search indexes for fast lookup."""
        # Alias to item mapping
        self.alias_map: Dict[str, MenuItem] = {}
        for item in self.menu.items:
            # Add canonical name
            self.alias_map[item.name.lower()] = item
            # Add aliases
            for alias in item.aliases:
                self.alias_map[alias.lower()] = item
        
        # Size synonym mapping
        self.size_map = self.menu.size_synonyms.copy()
        
        # Modifier synonym mapping
        self.modifier_map: Dict[str, str] = {}
        for item in self.menu.items:
            for synonym, canonical in item.modifier_synonyms.items():
                self.modifier_map[synonym.lower()] = canonical
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize input text for better matching.
        Removes punctuation, normalizes whitespace, converts to lowercase.
        """
        # Remove punctuation except hyphens and apostrophes
        text = re.sub(r'[^\w\s\-\']', ' ', text)
        # Normalize whitespace
        text = ' '.join(text.split())
        return text.lower()
    
    def parse_order(self, text: str) -> Cart:
        """
        Parse a complete order text into a cart.
        Handles in-turn corrections like "make that medium" or "cancel the fries".
        """
        logger.info(f"Parsing order: {text}")
        
        # Handle corrections
        text = self._handle_corrections(text)
        
        # Normalize text
        normalized = self.normalize_text(text)
        
        cart = Cart()
        
        # Find all items in the order
        items_found = self._find_all_items(normalized)
        
        for item_info in items_found:
            cart.add_item(item_info)
            logger.info(f"Added to cart: {item_info}")
        
        # Merge duplicates
        cart.merge_duplicates()
        logger.info(f"Final cart: {cart.to_dict()}")
        
        return cart
    
    def _handle_corrections(self, text: str) -> str:
        """
        Handle in-turn corrections in the text.
        Examples: "make that medium", "cancel the fries", "switch Coke to Diet"
        """
        # Remove correction phrases that don't affect item identification
        corrections = [
            r'\bactually\b',
            r'\binstead\b',
            r'\bchange\b',
            r'\bmake that\b',
            r'\bswitch\b',
        ]
        
        for pattern in corrections:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text
    
    def _find_all_items(self, text: str) -> List[CartItem]:
        """Find all items mentioned in the text."""
        items = []
        
        # Find all potential item mentions with their positions
        found_mentions = []
        for alias, item in self.alias_map.items():
            # Find all occurrences of this alias
            for match in re.finditer(r'\b' + re.escape(alias) + r'\b', text):
                found_mentions.append((match.start(), match.end(), alias, item))
        
        # Sort by position
        found_mentions.sort(key=lambda x: x[0])
        
        # Remove overlapping mentions (keep the longest)
        filtered_mentions = []
        for i, mention in enumerate(found_mentions):
            start, end, alias, item = mention
            # Check if this mention overlaps with any previous
            overlaps = False
            for prev_start, prev_end, prev_alias, prev_item in filtered_mentions:
                if not (end <= prev_start or start >= prev_end):
                    # Overlaps - keep the longer one
                    if len(alias) > len(prev_alias):
                        filtered_mentions.remove((prev_start, prev_end, prev_alias, prev_item))
                    else:
                        overlaps = True
                        break
            if not overlaps:
                filtered_mentions.append(mention)
        
        # For each mention, extract its context and create a cart item
        for start, end, alias, item in filtered_mentions:
            # Get context around this mention (look backwards for quantity, forwards for modifiers)
            context_start = max(0, start - 50)
            context_end = min(len(text), end + 100)
            context = text[context_start:context_end]
            
            # Extract quantity (look before the item)
            quantity = self._extract_quantity(context, alias)
            
            # Extract size
            size = self._extract_size(context, item)
            
            # Extract modifiers
            modifiers = self._extract_modifiers(context, item)
            
            # Calculate price
            price = self._calculate_price(item, size, modifiers)
            
            # Create cart item
            cart_item = CartItem(
                sku=item.sku,
                name=item.name,
                quantity=quantity,
                size=size,
                modifiers=modifiers,
                price=price
            )
            
            items.append(cart_item)
        
        return items
    
    def _extract_quantity(self, context: str, alias: str) -> int:
        """Extract quantity from context."""
        # Number words
        number_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "a": 1, "an": 1
        }
        
        # Find the position of the alias in context
        alias_pos = context.find(alias)
        if alias_pos == -1:
            return 1
        
        # Look backwards from alias for quantity
        before_alias = context[:alias_pos]
        words = before_alias.split()
        
        # Check last few words for quantity
        for word in reversed(words[-5:]):
            if word in number_words:
                return number_words[word]
            if word.isdigit():
                return int(word)
        
        return 1
    
    def _extract_size(self, context: str, item: MenuItem) -> Optional[str]:
        """Extract size from context."""
        if not item.size_variations:
            return None
        
        # Look for size synonyms in context with word boundaries
        for size_word, canonical_size in self.size_map.items():
            if re.search(r'\b' + re.escape(size_word) + r'\b', context):
                return canonical_size
        
        # Apply default size
        return self.menu.default_sizes.get(item.category, "medium")
    
    def _extract_modifiers(self, context: str, item: MenuItem) -> List[str]:
        """Extract modifiers from context."""
        modifiers = []
        found = set()
        
        # Check for modifier synonyms
        for synonym, canonical in self.modifier_map.items():
            if synonym in context and canonical not in found:
                modifiers.append(canonical)
                found.add(canonical)
        
        # Check for explicit modifiers
        for modifier in item.modifiers:
            if modifier.lower() in context and modifier not in found:
                modifiers.append(modifier)
                found.add(modifier)
        
        return modifiers
    
    def _calculate_price(self, item: MenuItem, size: Optional[str], modifiers: List[str]) -> float:
        """Calculate the final price for an item."""
        price = item.base_price
        
        # Add size variation
        if size and size in item.size_variations:
            price += item.size_variations[size]
        
        return price


class CartEvaluator:
    """
    Evaluates cart correctness against expected results.
    """
    
    @staticmethod
    def exact_match(actual: Cart, expected: Cart) -> bool:
        """Check if two carts are exactly the same."""
        if len(actual.items) != len(expected.items):
            return False
        
        actual_items = sorted(actual.items, key=lambda x: (x.sku, x.size, tuple(x.modifiers)))
        expected_items = sorted(expected.items, key=lambda x: (x.sku, x.size, tuple(x.modifiers)))
        
        for a, e in zip(actual_items, expected_items):
            if (a.sku != e.sku or 
                a.quantity != e.quantity or
                a.size != e.size or
                set(a.modifiers) != set(e.modifiers)):
                return False
        
        return True
    
    @staticmethod
    def calculate_f1(actual: Cart, expected: Cart) -> float:
        """
        Calculate F1 score for cart items.
        Treats each item as a separate entity (SKU + size + modifiers).
        """
        actual_items = set()
        for item in actual.items:
            for _ in range(item.quantity):
                actual_items.add((item.sku, item.size, tuple(sorted(item.modifiers))))
        
        expected_items = set()
        for item in expected.items:
            for _ in range(item.quantity):
                expected_items.add((item.sku, item.size, tuple(sorted(item.modifiers))))
        
        if not expected_items:
            return 1.0 if not actual_items else 0.0
        
        true_positives = len(actual_items & expected_items)
        false_positives = len(actual_items - expected_items)
        false_negatives = len(expected_items - actual_items)
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return f1
    
    @staticmethod
    def calculate_item_accuracy(actual: Cart, expected: Cart) -> float:
        """Calculate accuracy for item SKUs only (ignoring size and modifiers)."""
        actual_skus = []
        for item in actual.items:
            actual_skus.extend([item.sku] * item.quantity)
        
        expected_skus = []
        for item in expected.items:
            expected_skus.extend([item.sku] * item.quantity)
        
        if not expected_skus:
            return 1.0 if not actual_skus else 0.0
        
        correct = sum(1 for a, e in zip(sorted(actual_skus), sorted(expected_skus)) if a == e)
        return correct / len(expected_skus)

