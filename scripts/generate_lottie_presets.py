import json
import os

def create_ai_sparkle():
    """Generates a clean 4-point pulsating AI sparkle star animation."""
    return {
        "v": "5.7.4",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 200,
        "h": 200,
        "nm": "AI Sparkle",
        "ddd": 0,
        "assets": [],
        "layers": [
            {
                "ddd": 0,
                "ind": 1,
                "ty": 4,
                "nm": "Center Glow",
                "sr": 1,
                "ks": {
                    "o": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [50]},
                            {"t": 30, "s": [90]},
                            {"t": 60, "s": [50]}
                        ]
                    },
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [85, 85, 100]},
                            {"t": 30, "s": [115, 115, 100]},
                            {"t": 60, "s": [85, 85, 100]}
                        ]
                    }
                },
                "shapes": [
                    {
                        "ty": "el",
                        "d": 1,
                        "s": {"a": 0, "k": [70, 70]},
                        "p": {"a": 0, "k": [0, 0]},
                        "nm": "Circle"
                    },
                    {
                        "ty": "fl",
                        "c": {"a": 0, "k": [0.38, 0.4, 0.95, 1]},
                        "o": {"a": 0, "k": 40},
                        "nm": "Fill"
                    }
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            },
            {
                "ddd": 0,
                "ind": 2,
                "ty": 4,
                "nm": "Sparkle Star",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [0]},
                            {"t": 30, "s": [180]},
                            {"t": 60, "s": [360]}
                        ]
                    },
                    "p": {"a": 0, "k": [100, 100, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [90, 90, 100]},
                            {"t": 30, "s": [110, 110, 100]},
                            {"t": 60, "s": [90, 90, 100]}
                        ]
                    }
                },
                "shapes": [
                    {
                        "ty": "sr",
                        "sy": 1,
                        "d": 1,
                        "pt": {"a": 0, "k": 4},
                        "p": {"a": 0, "k": [0, 0]},
                        "r": {"a": 0, "k": 0},
                        "ir": {"a": 0, "k": 18},
                        "is": {"a": 0, "k": 0},
                        "or": {"a": 0, "k": 65},
                        "os": {"a": 0, "k": 0},
                        "nm": "Polystar"
                    },
                    {
                        "ty": "fl",
                        "c": {"a": 0, "k": [1, 1, 1, 1]},
                        "o": {"a": 0, "k": 100},
                        "nm": "Star Fill"
                    }
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            }
        ]
    }

def create_friendly_robot():
    """Generates an animated friendly robot with blinking eyes and floating bob."""
    return {
        "v": "5.7.4",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 200,
        "h": 200,
        "nm": "Friendly Robot",
        "ddd": 0,
        "assets": [],
        "layers": [
            {
                "ddd": 0,
                "ind": 1,
                "ty": 4,
                "nm": "Antenna Tip",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 35, 0]},
                            {"t": 30, "s": [100, 31, 0]},
                            {"t": 60, "s": [100, 35, 0]}
                        ]
                    },
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 30, "s": [120, 120, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {
                        "ty": "el",
                        "d": 1,
                        "s": {"a": 0, "k": [16, 16]},
                        "p": {"a": 0, "k": [0, 0]},
                        "nm": "Antenna Ball"
                    },
                    {
                        "ty": "fl",
                        "c": {"a": 0, "k": [0.98, 0.75, 0.18, 1]},
                        "o": {"a": 0, "k": 100},
                        "nm": "Gold Glow"
                    }
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            },
            {
                "ddd": 0,
                "ind": 2,
                "ty": 4,
                "nm": "Eyes Left & Right",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 0]},
                            {"t": 30, "s": [100, 96, 0]},
                            {"t": 60, "s": [100, 100, 0]}
                        ]
                    },
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 25, "s": [100, 100, 100]},
                            {"t": 28, "s": [100, 10, 100]},
                            {"t": 32, "s": [100, 100, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {
                        "ty": "el",
                        "d": 1,
                        "s": {"a": 0, "k": [18, 18]},
                        "p": {"a": 0, "k": [-24, -6]},
                        "nm": "Eye Left"
                    },
                    {
                        "ty": "el",
                        "d": 1,
                        "s": {"a": 0, "k": [18, 18]},
                        "p": {"a": 0, "k": [24, -6]},
                        "nm": "Eye Right"
                    },
                    {
                        "ty": "fl",
                        "c": {"a": 0, "k": [0.18, 0.8, 0.95, 1]},
                        "o": {"a": 0, "k": 100},
                        "nm": "Cyan Eyes"
                    }
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            },
            {
                "ddd": 0,
                "ind": 3,
                "ty": 4,
                "nm": "Robot Head",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 105, 0]},
                            {"t": 30, "s": [100, 101, 0]},
                            {"t": 60, "s": [100, 105, 0]}
                        ]
                    },
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {
                        "ty": "rc",
                        "d": 1,
                        "s": {"a": 0, "k": [100, 85]},
                        "p": {"a": 0, "k": [0, 0]},
                        "r": {"a": 0, "k": 22},
                        "nm": "Head Base"
                    },
                    {
                        "ty": "fl",
                        "c": {"a": 0, "k": [0.95, 0.96, 0.98, 1]},
                        "o": {"a": 0, "k": 100},
                        "nm": "Head Fill"
                    },
                    {
                        "ty": "st",
                        "c": {"a": 0, "k": [0.2, 0.25, 0.4, 1]},
                        "o": {"a": 0, "k": 100},
                        "w": {"a": 0, "k": 4},
                        "nm": "Head Stroke"
                    }
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            }
        ]
    }

def create_chatty_bubble():
    """Generates an animated speech bubble with three bouncing typing dots."""
    return {
        "v": "5.7.4",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 200,
        "h": 200,
        "nm": "Chatty Bubble",
        "ddd": 0,
        "assets": [],
        "layers": [
            {
                "ddd": 0,
                "ind": 1,
                "ty": 4,
                "nm": "Dot 1",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [70, 95, 0]},
                            {"t": 15, "s": [70, 82, 0]},
                            {"t": 30, "s": [70, 95, 0]},
                            {"t": 60, "s": [70, 95, 0]}
                        ]
                    },
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [14, 14]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Dot"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.31, 0.27, 0.9, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"}
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            },
            {
                "ddd": 0,
                "ind": 2,
                "ty": 4,
                "nm": "Dot 2",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 95, 0]},
                            {"t": 10, "s": [100, 95, 0]},
                            {"t": 25, "s": [100, 82, 0]},
                            {"t": 40, "s": [100, 95, 0]},
                            {"t": 60, "s": [100, 95, 0]}
                        ]
                    },
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [14, 14]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Dot"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.31, 0.27, 0.9, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"}
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            },
            {
                "ddd": 0,
                "ind": 3,
                "ty": 4,
                "nm": "Dot 3",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [130, 95, 0]},
                            {"t": 20, "s": [130, 95, 0]},
                            {"t": 35, "s": [130, 82, 0]},
                            {"t": 50, "s": [130, 95, 0]},
                            {"t": 60, "s": [130, 95, 0]}
                        ]
                    },
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {"ty": "el", "d": 1, "s": {"a": 0, "k": [14, 14]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Dot"},
                    {"ty": "fl", "c": {"a": 0, "k": [0.31, 0.27, 0.9, 1]}, "o": {"a": 0, "k": 100}, "nm": "Fill"}
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            },
            {
                "ddd": 0,
                "ind": 4,
                "ty": 4,
                "nm": "Bubble Body",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [100, 95, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [100, 100, 100]},
                            {"t": 30, "s": [103, 103, 100]},
                            {"t": 60, "s": [100, 100, 100]}
                        ]
                    }
                },
                "shapes": [
                    {
                        "ty": "rc",
                        "d": 1,
                        "s": {"a": 0, "k": [116, 76]},
                        "p": {"a": 0, "k": [0, 0]},
                        "r": {"a": 0, "k": 22},
                        "nm": "Bubble Rect"
                    },
                    {
                        "ty": "fl",
                        "c": {"a": 0, "k": [1, 1, 1, 1]},
                        "o": {"a": 0, "k": 100},
                        "nm": "Fill"
                    },
                    {
                        "ty": "st",
                        "c": {"a": 0, "k": [0.85, 0.88, 0.95, 1]},
                        "o": {"a": 0, "k": 100},
                        "w": {"a": 0, "k": 4},
                        "nm": "Stroke"
                    }
                ],
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0
            }
        ]
    }

def ensure_keyframes(obj):
    if not isinstance(obj, (dict, list)):
        return
    if isinstance(obj, dict):
        if obj.get("a") == 1 and isinstance(obj.get("k"), list):
            for kf in obj["k"]:
                if isinstance(kf, dict):
                    if "i" not in kf:
                        kf["i"] = {"x": [0.833], "y": [0.833]}
                    if "o" not in kf:
                        kf["o"] = {"x": [0.167], "y": [0.167]}
        for v in obj.values():
            ensure_keyframes(v)
    elif isinstance(obj, list):
        for item in obj:
            ensure_keyframes(item)


def main():
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/public/animations"))
    os.makedirs(target_dir, exist_ok=True)
    
    presets = {
        "ai-sparkle.json": create_ai_sparkle(),
        "friendly-robot.json": create_friendly_robot(),
        "chatty-bubble.json": create_chatty_bubble(),
    }
    
    for filename, data in presets.items():
        ensure_keyframes(data)
        path = os.path.join(target_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Generated {path}")

if __name__ == "__main__":
    main()
