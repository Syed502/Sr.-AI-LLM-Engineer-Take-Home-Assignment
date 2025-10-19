"""
Menu data structures for Dr. Donut drive-thru ordering system.
Contains both small (baseline) and large (challenging) menus with aliases,
size mappings, and modifiers.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MenuItem:
    """Represents a single menu item with its properties."""
    sku: str
    name: str
    category: str
    price: float
    base_price: float  # For items with size variations
    aliases: List[str]
    size_variations: Dict[str, float]  # size_name -> price_delta
    modifiers: List[str]
    modifier_synonyms: Dict[str, str]  # synonym -> canonical name


@dataclass
class Menu:
    """Complete menu with normalization data."""
    name: str
    items: List[MenuItem]
    size_synonyms: Dict[str, str]  # "large" -> "L"
    default_sizes: Dict[str, str]  # category -> default size


# Small Menu - Baseline (works well)
SMALL_MENU = Menu(
    name="Small Menu",
    items=[
        MenuItem(
            sku="DON001",
            name="Pumpkin Spice Iced Doughnut",
            category="donuts",
            price=1.29,
            base_price=1.29,
            aliases=["pumpkin spice donut", "pumpkin donut", "ps donut", "pumpkin iced"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="DON002",
            name="Chocolate Iced Doughnut",
            category="donuts",
            price=1.09,
            base_price=1.09,
            aliases=["chocolate donut", "choc donut", "chocolate glazed"],
            size_variations={},
            modifiers=["sprinkles"],
            modifier_synonyms={"with sprinkles": "sprinkles", "sprinkled": "sprinkles"}
        ),
        MenuItem(
            sku="DON003",
            name="Raspberry Filled Doughnut",
            category="donuts",
            price=1.09,
            base_price=1.09,
            aliases=["raspberry donut", "raspberry filled", "rasp filled"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="COF001",
            name="Regular Brewed Coffee",
            category="coffee",
            price=1.79,
            base_price=1.79,
            aliases=["coffee", "regular coffee", "brewed coffee", "black coffee"],
            size_variations={"small": 0.0, "medium": 0.3, "large": 0.6},
            modifiers=["cream", "sugar", "milk"],
            modifier_synonyms={"with cream": "cream", "creamer": "cream", "sweet": "sugar"}
        ),
        MenuItem(
            sku="COF002",
            name="Pumpkin Spice Latte",
            category="coffee",
            price=4.59,
            base_price=4.59,
            aliases=["pumpkin spice latte", "psl", "pumpkin latte", "ps latte"],
            size_variations={"small": 0.0, "medium": 0.5, "large": 1.0},
            modifiers=["extra shot", "whip", "no whip", "almond milk", "oat milk"],
            modifier_synonyms={"whipped cream": "whip", "no whipped cream": "no whip"}
        ),
    ],
    size_synonyms={
        "small": "small", "s": "small", "sm": "small", "regular": "small",
        "medium": "medium", "m": "medium", "med": "medium",
        "large": "large", "l": "large", "lg": "large", "big": "large",
    },
    default_sizes={
        "donuts": "regular",
        "coffee": "medium",
    }
)

# Large Menu - Challenging (causes failures)
LARGE_MENU = Menu(
    name="Large Menu",
    items=[
        # DONUTS
        MenuItem(
            sku="DON001",
            name="Pumpkin Spice Iced Doughnut",
            category="donuts",
            price=1.29,
            base_price=1.29,
            aliases=["pumpkin spice donut", "pumpkin donut", "ps donut", "pumpkin iced", 
                     "pumpkin spice", "pumpkin glazed", "ps iced"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="DON002",
            name="Pumpkin Spice Cake Doughnut",
            category="donuts",
            price=1.29,
            base_price=1.29,
            aliases=["pumpkin cake donut", "pumpkin cake", "ps cake", "pumpkin spice cake",
                     "cake donut pumpkin"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="DON003",
            name="Old Fashioned Doughnut",
            category="donuts",
            price=1.29,
            base_price=1.29,
            aliases=["old fashioned", "old fashioned donut", "old fashioned doughnut",
                     "old fashion", "plain cake donut"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="DON004",
            name="Chocolate Iced Doughnut",
            category="donuts",
            price=1.09,
            base_price=1.09,
            aliases=["chocolate donut", "choc donut", "chocolate glazed", "chocolate iced",
                     "choc iced", "chocolate", "choc"],
            size_variations={},
            modifiers=["sprinkles"],
            modifier_synonyms={"with sprinkles": "sprinkles", "sprinkled": "sprinkles",
                               "rainbow sprinkles": "sprinkles", "colored sprinkles": "sprinkles"}
        ),
        MenuItem(
            sku="DON005",
            name="Raspberry Filled Doughnut",
            category="donuts",
            price=1.09,
            base_price=1.09,
            aliases=["raspberry donut", "raspberry filled", "rasp filled", "raspberry jelly",
                     "raspberry jam", "rasp", "raspberry"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="DON006",
            name="Blueberry Cake Doughnut",
            category="donuts",
            price=1.09,
            base_price=1.09,
            aliases=["blueberry donut", "blueberry cake", "blueberry", "blueberry cake donut"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="DON007",
            name="Strawberry Iced Doughnut with Sprinkles",
            category="donuts",
            price=1.09,
            base_price=1.09,
            aliases=["strawberry donut", "strawberry iced", "strawberry glazed", "strawberry",
                     "strawberry with sprinkles", "strawberry sprinkled"],
            size_variations={},
            modifiers=["sprinkles"],
            modifier_synonyms={"with sprinkles": "sprinkles", "sprinkled": "sprinkles"}
        ),
        MenuItem(
            sku="DON008",
            name="Lemon Filled Doughnut",
            category="donuts",
            price=1.09,
            base_price=1.09,
            aliases=["lemon donut", "lemon filled", "lemon jelly", "lemon jam", "lemon"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        MenuItem(
            sku="DON009",
            name="Doughnut Holes",
            category="donuts",
            price=3.99,
            base_price=3.99,
            aliases=["donut holes", "donut holes dozen", "holes", "munchkins", "donut munchkins"],
            size_variations={},
            modifiers=[],
            modifier_synonyms={}
        ),
        
        # COFFEE & DRINKS
        MenuItem(
            sku="COF001",
            name="Pumpkin Spice Coffee",
            category="coffee",
            price=2.59,
            base_price=2.59,
            aliases=["pumpkin spice coffee", "ps coffee", "pumpkin coffee", "pumpkin brew"],
            size_variations={"small": 0.0, "medium": 0.3, "large": 0.6},
            modifiers=["cream", "sugar", "milk", "extra shot"],
            modifier_synonyms={"with cream": "cream", "creamer": "cream", "sweet": "sugar"}
        ),
        MenuItem(
            sku="COF002",
            name="Pumpkin Spice Latte",
            category="coffee",
            price=4.59,
            base_price=4.59,
            aliases=["pumpkin spice latte", "psl", "pumpkin latte", "ps latte", "pumpkin spice latte"],
            size_variations={"small": 0.0, "medium": 0.5, "large": 1.0},
            modifiers=["extra shot", "whip", "no whip", "almond milk", "oat milk"],
            modifier_synonyms={"whipped cream": "whip", "no whipped cream": "no whip"}
        ),
        MenuItem(
            sku="COF003",
            name="Regular Brewed Coffee",
            category="coffee",
            price=1.79,
            base_price=1.79,
            aliases=["coffee", "regular coffee", "brewed coffee", "black coffee", "regular",
                     "house coffee", "drip coffee"],
            size_variations={"small": 0.0, "medium": 0.3, "large": 0.6},
            modifiers=["cream", "sugar", "milk"],
            modifier_synonyms={"with cream": "cream", "creamer": "cream", "sweet": "sugar"}
        ),
        MenuItem(
            sku="COF004",
            name="Decaf Brewed Coffee",
            category="coffee",
            price=1.79,
            base_price=1.79,
            aliases=["decaf", "decaf coffee", "decaffeinated", "decaf brewed"],
            size_variations={"small": 0.0, "medium": 0.3, "large": 0.6},
            modifiers=["cream", "sugar", "milk"],
            modifier_synonyms={"with cream": "cream", "creamer": "cream", "sweet": "sugar"}
        ),
        MenuItem(
            sku="COF005",
            name="Latte",
            category="coffee",
            price=3.49,
            base_price=3.49,
            aliases=["latte", "cafe latte", "coffee latte"],
            size_variations={"small": 0.0, "medium": 0.4, "large": 0.8},
            modifiers=["extra shot", "decaf", "almond milk", "oat milk", "skim milk", "whole milk"],
            modifier_synonyms={"almond": "almond milk", "oat": "oat milk", "skim": "skim milk"}
        ),
        MenuItem(
            sku="COF006",
            name="Cappuccino",
            category="coffee",
            price=3.49,
            base_price=3.49,
            aliases=["cappuccino", "capp", "cappucino"],
            size_variations={"small": 0.0, "medium": 0.4, "large": 0.8},
            modifiers=["extra shot", "decaf", "almond milk", "oat milk", "skim milk"],
            modifier_synonyms={"almond": "almond milk", "oat": "oat milk", "skim": "skim milk"}
        ),
        MenuItem(
            sku="COF007",
            name="Caramel Macchiato",
            category="coffee",
            price=3.49,
            base_price=3.49,
            aliases=["caramel macchiato", "caramel mac", "caramel mach", "macchiato"],
            size_variations={"small": 0.0, "medium": 0.4, "large": 0.8},
            modifiers=["extra shot", "decaf", "almond milk", "oat milk", "extra caramel"],
            modifier_synonyms={"almond": "almond milk", "oat": "oat milk"}
        ),
        MenuItem(
            sku="COF008",
            name="Mocha Latte",
            category="coffee",
            price=3.49,
            base_price=3.49,
            aliases=["mocha", "mocha latte", "chocolate latte", "choc latte"],
            size_variations={"small": 0.0, "medium": 0.4, "large": 0.8},
            modifiers=["extra shot", "decaf", "almond milk", "oat milk", "whip", "no whip"],
            modifier_synonyms={"almond": "almond milk", "oat": "oat milk", "whipped cream": "whip"}
        ),
        MenuItem(
            sku="COF009",
            name="Caramel Mocha Latte",
            category="coffee",
            price=3.49,
            base_price=3.49,
            aliases=["caramel mocha", "caramel mocha latte", "caramel choc latte"],
            size_variations={"small": 0.0, "medium": 0.4, "large": 0.8},
            modifiers=["extra shot", "decaf", "almond milk", "oat milk", "whip", "no whip"],
            modifier_synonyms={"almond": "almond milk", "oat": "oat milk", "whipped cream": "whip"}
        ),
    ],
    size_synonyms={
        "small": "small", "s": "small", "sm": "small", "regular": "small", "short": "small",
        "medium": "medium", "m": "medium", "med": "medium", "grande": "medium",
        "large": "large", "l": "large", "lg": "large", "big": "large", "venti": "large",
        "extra large": "large", "xl": "large", "x-large": "large",
    },
    default_sizes={
        "donuts": "regular",
        "coffee": "medium",
    }
)


def get_menu(menu_name: str = "small") -> Menu:
    """Get a menu by name."""
    menus = {
        "small": SMALL_MENU,
        "large": LARGE_MENU,
    }
    return menus.get(menu_name.lower(), SMALL_MENU)


def get_all_items(menu: Menu) -> List[MenuItem]:
    """Get all items from a menu."""
    return menu.items


def find_item_by_sku(menu: Menu, sku: str) -> Optional[MenuItem]:
    """Find a menu item by SKU."""
    for item in menu.items:
        if item.sku == sku:
            return item
    return None



