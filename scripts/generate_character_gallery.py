import json
import os

def create_buddy_robot():
    """1. Buddy Robot (Friendly): Cheerful robot with bouncing antenna, blinking cyan eyes, and smiling mouth."""
    return {
        "v": "5.7.4",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 200,
        "h": 200,
        "nm": "Buddy Robot",
        "ddd": 0,
        "assets": [],
        "layers": [
            # Antenna Ball
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Antenna Ball", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 36, 0]}, {"t": 30, "s": [100, 30, 0]}, {"t": 60, "s": [100, 36, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 1, "k": [{"t": 0, "s": [100, 100, 100]}, {"t": 30, "s": [125, 125, 100]}, {"t": 60, "s": [100, 100, 100]}]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [16, 16]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Ball"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.24, 0.51, 0.96, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Antenna Stem
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Antenna Stem", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 48, 0]}, {"t": 30, "s": [100, 44, 0]}, {"t": 60, "s": [100, 48, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [6, 18]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 3}, "nm": "Stem"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.55, 0.65, 0.8, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Blinking Cyan Eyes
            {
                "ddd": 0, "ind": 3, "ty": 4, "nm": "Blinking Eyes", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 100, 0]}, {"t": 30, "s": [100, 96, 0]}, {"t": 60, "s": [100, 100, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 24, "s": [100, 100, 100]},
                            {"t": 27, "s": [100, 15, 100]},
                            {"t": 31, "s": [100, 100, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [18, 18]}, "p": {"a": 0, "k": [-26, -4]}, "nm": "Eye L"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [18, 18]}, "p": {"a": 0, "k": [26, -4]}, "nm": "Eye R"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.05, 0.85, 0.95, 1]}, "o": {"a": 0, "k": 100}, "nm": "Cyan Glow"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Smile
            {
                "ddd": 0, "ind": 4, "ty": 4, "nm": "Smile", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 118, 0]}, {"t": 30, "s": [100, 114, 0]}, {"t": 60, "s": [100, 118, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [26, 8]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 4}, "nm": "Mouth"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.05, 0.85, 0.95, 1]}, "o": {"a": 0, "k": 90}, "nm": "Fill"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Robot Face Plate
            {
                "ddd": 0, "ind": 5, "ty": 4, "nm": "Face Screen", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 106, 0]}, {"t": 30, "s": [100, 102, 0]}, {"t": 60, "s": [100, 106, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [90, 60]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 16}, "nm": "Screen"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.08, 0.12, 0.22, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Robot Outer Head
            {
                "ddd": 0, "ind": 6, "ty": 4, "nm": "Head Shell", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 106, 0]}, {"t": 30, "s": [100, 102, 0]}, {"t": 60, "s": [100, 106, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [116, 86]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 26}, "nm": "Shell"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.88, 0.92, 0.98, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"},
                    {"ty": "st", "c": {"a": 0, "k": [0.24, 0.51, 0.96, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Stroke"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_happy_assistant():
    """2. Happy Assistant (Friendly): Cheerful smiling circular mascot with blush cheeks and playful floating bob."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Happy Assistant", "ddd": 0, "assets": [],
        "layers": [
            # Blush Cheeks
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Blush", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 85}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 108, 0]}, {"t": 30, "s": [100, 102, 0]}, {"t": 60, "s": [100, 108, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [22, 14]}, "p": {"a": 0, "k": [-34, 0]}, "nm": "Cheek L"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [22, 14]}, "p": {"a": 0, "k": [34, 0]}, "nm": "Cheek R"},
                    {"ty": "fl", "c": {"a": 0, "k": [1.0, 0.45, 0.60, 1]}, "o": {"a": 0, "k": 80}, "nm": "Pink"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Eyes
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Eyes", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 96, 0]}, {"t": 30, "s": [100, 90, 0]}, {"t": 60, "s": [100, 96, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 22, "s": [100, 100, 100]},
                            {"t": 25, "s": [100, 10, 100]},
                            {"t": 29, "s": [100, 100, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [16, 20]}, "p": {"a": 0, "k": [-24, 0]}, "nm": "Eye L"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [16, 20]}, "p": {"a": 0, "k": [24, 0]}, "nm": "Eye R"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.12, 0.15, 0.25, 1]}, "o": {"a": 0, "k": 100}, "nm": "Dark"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Smiling Open Mouth
            {
                "ddd": 0, "ind": 3, "ty": 4, "nm": "Big Smile", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 118, 0]}, {"t": 30, "s": [100, 112, 0]}, {"t": 60, "s": [100, 118, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [28, 20]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Mouth"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.92, 0.25, 0.35, 1]}, "o": {"a": 0, "k": 100}, "nm": "Red"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Head Circle
            {
                "ddd": 0, "ind": 4, "ty": 4, "nm": "Head Base", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 100, 0]}, {"t": 30, "s": [100, 94, 0]}, {"t": 60, "s": [100, 100, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [116, 116]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Circle"},
                    {"ty": "fl", "c": {"a": 0, "k": [1.0, 0.84, 0.28, 1]}, "o": {"a": 0, "k": 100}, "nm": "Warm Yellow"},
                    {"ty": "st", "c": {"a": 0, "k": [0.95, 0.65, 0.12, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Outline"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_professional_bot():
    """3. Professional Bot (Professional): Sleek dark slate enterprise bot with glowing cyan scanner visor."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Professional Bot", "ddd": 0, "assets": [],
        "layers": [
            # Scanning Light Beam inside Visor
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Scan Light", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [70, 98, 0]},
                            {"t": 30, "s": [130, 98, 0]},
                            {"t": 60, "s": [70, 98, 0]}
                        ]
                    },
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [22, 14]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 4}, "nm": "Glow Block"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.05, 0.88, 0.98, 1]}, "o": {"a": 0, "k": 100}, "nm": "Cyan"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Dark Visor Shield
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Visor Band", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 98, 0]}, {"t": 30, "s": [100, 94, 0]}, {"t": 60, "s": [100, 98, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [96, 22]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 8}, "nm": "Visor"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.06, 0.09, 0.16, 1]}, "o": {"a": 0, "k": 100}, "nm": "Dark"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Slate Head Body
            {
                "ddd": 0, "ind": 3, "ty": 4, "nm": "Head Structure", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 100, 0]}, {"t": 30, "s": [100, 96, 0]}, {"t": 60, "s": [100, 100, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [118, 92]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 20}, "nm": "Hex Head"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.15, 0.20, 0.32, 1]}, "o": {"a": 0, "k": 100}, "nm": "Slate Blue"},
                    {"ty": "st", "c": {"a": 0, "k": [0.38, 0.48, 0.65, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Border"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_smart_assistant():
    """4. Smart Assistant (Professional): Analytical assistant with dual concentric data rings and pulsating core."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Smart Assistant", "ddd": 0, "assets": [],
        "layers": [
            # Pulsing Neural Core
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Neural Core", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 1, "k": [{"t": 0, "s": [85, 85, 100]}, {"t": 30, "s": [120, 120, 100]}, {"t": 60, "s": [85, 85, 100]}]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [36, 36]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Core"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.35, 0.40, 0.98, 1]}, "o": {"a": 0, "k": 100}, "nm": "Indigo"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Inner Rotating Ring
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Inner Ring", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 90},
                    "r": {"a": 1, "k": [{"t": 0, "s": [0]}, {"t": 60, "s": [360]}]},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [72, 72]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Ring"},
                    {"ty": "st", "c": {"a": 0, "k": [0.55, 0.45, 0.95, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Dash"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Outer Rotating Ring (Counter)
            {
                "ddd": 0, "ind": 3, "ty": 4, "nm": "Outer Ring", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 80},
                    "r": {"a": 1, "k": [{"t": 0, "s": [360]}, {"t": 60, "s": [0]}]},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [112, 112]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Ring 2"},
                    {"ty": "st", "c": {"a": 0, "k": [0.25, 0.75, 0.95, 1]}, "w": {"a": 0, "k": 3}, "o": {"a": 0, "k": 80}, "nm": "Stroke"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_care_companion():
    """5. Care Companion (Healthcare): Coral heart companion with rhythmic heartbeat pulse and white medical cross."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Care Companion", "ddd": 0, "assets": [],
        "layers": [
            # White Cross Emblem
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Cross", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [90, 90, 100]},
                            {"t": 10, "s": [115, 115, 100]},
                            {"t": 18, "s": [95, 95, 100]},
                            {"t": 28, "s": [120, 120, 100]},
                            {"t": 40, "s": [90, 90, 100]},
                            {"t": 60, "s": [90, 90, 100]}
                        ]
                    }
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [14, 38]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 4}, "nm": "V Bar"},
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [38, 14]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 4}, "nm": "H Bar"},
                    {"ty": "fl", "c": {"a": 0, "k": [1, 1, 1, 1]}, "o": {"a": 0, "k": 100}, "nm": "White"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Heart Pulsing Base
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Heart Body", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [90, 90, 100]},
                            {"t": 10, "s": [115, 115, 100]},
                            {"t": 18, "s": [95, 95, 100]},
                            {"t": 28, "s": [120, 120, 100]},
                            {"t": 40, "s": [90, 90, 100]},
                            {"t": 60, "s": [90, 90, 100]}
                        ]
                    }
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [110, 110]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Circle Body"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.95, 0.32, 0.38, 1]}, "o": {"a": 0, "k": 100}, "nm": "Coral Red"},
                    {"ty": "st", "c": {"a": 0, "k": [1.0, 0.65, 0.70, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Glow Border"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_healthcare_buddy():
    """6. Healthcare Buddy (Healthcare): Emerald medical mascot with smiling face and soothing floating aura."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Healthcare Buddy", "ddd": 0, "assets": [],
        "layers": [
            # Cute Eyes & Smile
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Facial Features", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 100, 0]}, {"t": 30, "s": [100, 94, 0]}, {"t": 60, "s": [100, 100, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 20, "s": [100, 100, 100]},
                            {"t": 23, "s": [100, 15, 100]},
                            {"t": 27, "s": [100, 100, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [12, 12]}, "p": {"a": 0, "k": [-20, -4]}, "nm": "Eye L"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [12, 12]}, "p": {"a": 0, "k": [20, -4]}, "nm": "Eye R"},
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [18, 6]}, "p": {"a": 0, "k": [0, 10]}, "r": {"a": 0, "k": 3}, "nm": "Smile"},
                    {"ty": "fl", "c": {"a": 0, "k": [1, 1, 1, 1]}, "o": {"a": 0, "k": 100}, "nm": "White"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Emerald Shield/Cross
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Emerald Shield", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 100, 0]}, {"t": 30, "s": [100, 94, 0]}, {"t": 60, "s": [100, 100, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [40, 104]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 16}, "nm": "V Bar"},
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [104, 40]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 16}, "nm": "H Bar"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.08, 0.65, 0.48, 1]}, "o": {"a": 0, "k": 100}, "nm": "Emerald"},
                    {"ty": "st", "c": {"a": 0, "k": [0.45, 0.90, 0.75, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Glow Stroke"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_learning_mate():
    """7. Learning Mate (Education): Academic guide with graduation cap and swaying golden tassel."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Learning Mate", "ddd": 0, "assets": [],
        "layers": [
            # Swaying Golden Tassel
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Tassel", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 1, "k": [{"t": 0, "s": [-12]}, {"t": 30, "s": [16]}, {"t": 60, "s": [-12]}]},
                    "p": {"a": 0, "k": [135, 60, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [6, 24]}, "p": {"a": 0, "k": [0, 10]}, "r": {"a": 0, "k": 3}, "nm": "Tassel Line"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.98, 0.78, 0.15, 1]}, "o": {"a": 0, "k": 100}, "nm": "Gold"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Mortarboard Diamond Cap
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Cap Top", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 52, 0]}, {"t": 30, "s": [100, 48, 0]}, {"t": 60, "s": [100, 52, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [90, 20]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 4}, "nm": "Board"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.15, 0.20, 0.35, 1]}, "o": {"a": 0, "k": 100}, "nm": "Navy"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Scholar Eyes
            {
                "ddd": 0, "ind": 3, "ty": 4, "nm": "Eyes", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 105, 0]}, {"t": 30, "s": [100, 101, 0]}, {"t": 60, "s": [100, 105, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 24, "s": [100, 100, 100]},
                            {"t": 27, "s": [100, 15, 100]},
                            {"t": 31, "s": [100, 100, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [14, 14]}, "p": {"a": 0, "k": [-22, 0]}, "nm": "Eye L"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [14, 14]}, "p": {"a": 0, "k": [22, 0]}, "nm": "Eye R"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.12, 0.16, 0.25, 1]}, "o": {"a": 0, "k": 100}, "nm": "Dark"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Scholar Head
            {
                "ddd": 0, "ind": 4, "ty": 4, "nm": "Head Base", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 110, 0]}, {"t": 30, "s": [100, 106, 0]}, {"t": 60, "s": [100, 110, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [96, 96]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Circle"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.94, 0.96, 1.0, 1]}, "o": {"a": 0, "k": 100}, "nm": "Light Blue"},
                    {"ty": "st", "c": {"a": 0, "k": [0.25, 0.45, 0.85, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Outline"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_study_companion():
    """8. Study Companion (Education): Curious wise owl assistant with big glasses and head tilt."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Study Companion", "ddd": 0, "assets": [],
        "layers": [
            # Glasses & Eyes
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Glasses", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 1, "k": [{"t": 0, "s": [-4]}, {"t": 30, "s": [5]}, {"t": 60, "s": [-4]}]},
                    "p": {"a": 0, "k": [100, 94, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 22, "s": [100, 100, 100]},
                            {"t": 25, "s": [100, 15, 100]},
                            {"t": 29, "s": [100, 100, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [36, 36]}, "p": {"a": 0, "k": [-24, 0]}, "nm": "Glass L"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [36, 36]}, "p": {"a": 0, "k": [24, 0]}, "nm": "Glass R"},
                    {"ty": "st", "c": {"a": 0, "k": [0.85, 0.45, 0.15, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Frames"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [14, 14]}, "p": {"a": 0, "k": [-24, 0]}, "nm": "Pupil L"},
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [14, 14]}, "p": {"a": 0, "k": [24, 0]}, "nm": "Pupil R"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.15, 0.12, 0.20, 1]}, "o": {"a": 0, "k": 100}, "nm": "Dark"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Owl Beak
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Beak", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 114, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [12, 16]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 4}, "nm": "Beak"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.98, 0.65, 0.12, 1]}, "o": {"a": 0, "k": 100}, "nm": "Orange"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Owl Head Base
            {
                "ddd": 0, "ind": 3, "ty": 4, "nm": "Owl Body", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 100, 0]}, {"t": 30, "s": [100, 94, 0]}, {"t": 60, "s": [100, 100, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [112, 112]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Circle Body"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.45, 0.28, 0.20, 1]}, "o": {"a": 0, "k": 100}, "nm": "Warm Brown"},
                    {"ty": "st", "c": {"a": 0, "k": [0.85, 0.55, 0.25, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Outline"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_minimal_orb():
    """9. Minimal Orb (Minimal): Elegant floating AI sphere with shimmering orbital aura."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Minimal Orb", "ddd": 0, "assets": [],
        "layers": [
            # Rotating Orbital Ring
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Orbit", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 85},
                    "r": {"a": 1, "k": [{"t": 0, "s": [0]}, {"t": 60, "s": [360]}]},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 1, "k": [{"t": 0, "s": [100, 40, 100]}, {"t": 30, "s": [100, 50, 100]}, {"t": 60, "s": [100, 40, 100]}]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [110, 110]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Ring"},
                    {"ty": "st", "c": {"a": 0, "k": [0.45, 0.85, 1.0, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 90}, "nm": "Glow Stroke"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Sphere Center
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Orb Core", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 1, "k": [{"t": 0, "s": [90, 90, 100]}, {"t": 30, "s": [105, 105, 100]}, {"t": 60, "s": [90, 90, 100]}]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [78, 78]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Sphere"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.28, 0.42, 0.95, 1]}, "o": {"a": 0, "k": 100}, "nm": "Deep Blue"},
                    {"ty": "st", "c": {"a": 0, "k": [0.75, 0.88, 1.0, 1]}, "w": {"a": 0, "k": 3}, "o": {"a": 0, "k": 80}, "nm": "Highlight"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

def create_floating_mascot():
    """10. Floating Mascot (Minimal): Modern geometric diamond companion with subtle tilt and breathing shadow."""
    return {
        "v": "5.7.4", "fr": 30, "ip": 0, "op": 60, "w": 200, "h": 200, "nm": "Floating Mascot", "ddd": 0, "assets": [],
        "layers": [
            # Shadow below
            {
                "ddd": 0, "ind": 1, "ty": 4, "nm": "Ground Shadow", "sr": 1,
                "ks": {
                    "o": {"a": 1, "k": [{"t": 0, "s": [25]}, {"t": 30, "s": [50]}, {"t": 60, "s": [25]}]},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 160, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 1, "k": [{"t": 0, "s": [80, 50, 100]}, {"t": 30, "s": [120, 70, 100]}, {"t": 60, "s": [80, 50, 100]}]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [50, 16]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Shadow"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.1, 0.15, 0.25, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            },
            # Floating Diamond
            {
                "ddd": 0, "ind": 2, "ty": 4, "nm": "Diamond Body", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 1, "k": [{"t": 0, "s": [45]}, {"t": 30, "s": [48]}, {"t": 60, "s": [45]}]},
                    "p": {"a": 1, "k": [{"t": 0, "s": [100, 95, 0]}, {"t": 30, "s": [100, 85, 0]}, {"t": 60, "s": [100, 95, 0]}]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 1, "k": [{"t": 0, "s": [95, 95, 100]}, {"t": 30, "s": [105, 105, 100]}, {"t": 60, "s": [95, 95, 100]}]}
                },
                "shapes": [
                    {"ty": "rc", "d": 1, "s": {"a": 0, "k": [68, 68]}, "p": {"a": 0, "k": [0, 0]}, "r": {"a": 0, "k": 16}, "nm": "Diamond"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.12, 0.72, 0.62, 1]}, "o": {"a": 0, "k": 100}, "nm": "Teal"},
                    {"ty": "st", "c": {"a": 0, "k": [0.45, 0.95, 0.85, 1]}, "w": {"a": 0, "k": 4}, "o": {"a": 0, "k": 100}, "nm": "Border"}
                ],
                "ip": 0, "op": 60, "st": 0, "bm": 0
            }
        ]
    }

CHARACTER_GENERATORS = {
    "buddy-robot": create_buddy_robot,
    "happy-assistant": create_happy_assistant,
    "professional-bot": create_professional_bot,
    "smart-assistant": create_smart_assistant,
    "care-companion": create_care_companion,
    "healthcare-buddy": create_healthcare_buddy,
    "learning-mate": create_learning_mate,
    "study-companion": create_study_companion,
    "minimal-orb": create_minimal_orb,
    "floating-mascot": create_floating_mascot,
}

def main():
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "widget_assets", "characters"))
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "characters"))
    
    os.makedirs(backend_dir, exist_ok=True)
    os.makedirs(frontend_dir, exist_ok=True)
    
    for char_id, gen_fn in CHARACTER_GENERATORS.items():
        data = gen_fn()
        filename = f"{char_id}.json"
        
        b_path = os.path.join(backend_dir, filename)
        with open(b_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        f_path = os.path.join(frontend_dir, filename)
        with open(f_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        print(f"Generated {char_id}: {b_path} and {f_path}")

if __name__ == "__main__":
    main()
