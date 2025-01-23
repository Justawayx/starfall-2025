from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Tuple, List
from items.divine_weapons import TIER_1_WEAPONS, TIER_2_WEAPONS, TIER_3_WEAPONS
import os
from io import BytesIO

class WeaponNode:
    def __init__(self, weapon_id: str, name: str, x: int, y: int, cp: int):
        self.id = weapon_id
        self.name = name
        self.x = x
        self.y = y
        self.cp = cp
        self.connections: List['WeaponNode'] = []

def generate_divine_weapon_tree(output_path: str = "temp/divine_tree") -> None:
    # Create base image with a darker background
    base = Image.new(mode="RGB", size=(1920, 1080), color=(40, 44, 52))
    draw = ImageDraw.Draw(base)
    
    # Load fonts
    try:
        title_font = ImageFont.truetype("./media/Rank/edosz.ttf", 48)
        weapon_font = ImageFont.truetype("./media/Rank/edosz.ttf", 32)
        cp_font = ImageFont.truetype("./media/Rank/edosz.ttf", 24)
    except OSError:
        title_font = weapon_font = cp_font = ImageFont.load_default()

    # Calculate positions for each tier
    weapon_nodes: Dict[str, WeaponNode] = {}
    tier_spacing = 300
    
    # Draw title
    draw.text((960, 50), "Divine Weapons Evolution Tree", 
              fill=(255, 255, 255), anchor="mm", font=title_font)

    # Position nodes for each tier
    for tier, weapons, y_pos in [
        (1, TIER_1_WEAPONS, 200),
        (2, TIER_2_WEAPONS, 500),
        (3, TIER_3_WEAPONS, 800)
    ]:
        # Draw tier label
        draw.text((100, y_pos), f"Tier {tier}", 
                 fill=(200, 200, 200), anchor="lm", font=title_font)
        
        # Position weapons
        x_spacing = 1720 // (len(weapons) + 1)
        for i, (weapon_id, weapon) in enumerate(weapons.items(), 1):
            x_pos = 100 + (i * x_spacing)
            weapon_nodes[weapon_id] = WeaponNode(
                weapon_id, weapon['name'], x_pos, y_pos, weapon['cp']
            )

    # Draw connections first (so they appear behind nodes)
    for tier_weapons in [TIER_1_WEAPONS, TIER_2_WEAPONS]:
        for weapon_id, weapon in tier_weapons.items():
            start_node = weapon_nodes[weapon_id]
            for evolution in weapon['evolution_paths']:
                end_node = weapon_nodes[evolution]
                # Draw curved path
                points = _get_curve_points(start_node.x, start_node.y, 
                                        end_node.x, end_node.y)
                # Draw glow effect
                for offset in range(3, 0, -1):
                    draw.line(points, fill=(100, 100, 100), width=5+offset)
                # Draw main line
                draw.line(points, fill=(150, 150, 150), width=5)

    # Draw weapon nodes
    for node in weapon_nodes.values():
        # Draw node background glow
        for offset in range(5, 0, -1):
            draw.ellipse(
                [node.x-80-offset, node.y-40-offset, 
                 node.x+80+offset, node.y+40+offset],
                fill=(60, 64, 72)
            )
        
        # Draw node
        draw.rectangle(
            [node.x-80, node.y-40, node.x+80, node.y+40],
            fill=(80, 84, 92),
            outline=(200, 200, 200),
            width=2
        )
        
        # Draw weapon name
        draw.text((node.x, node.y-10), node.name, 
                 fill=(255, 255, 255), anchor="mm", font=weapon_font)
        # Draw CP value
        draw.text((node.x, node.y+20), f"CP: {node.cp:,}", 
                 fill=(200, 200, 200), anchor="mm", font=cp_font)

    # Save with antialiasing
    base = base.resize((1920, 1080), Image.LANCZOS)
    base.save(f"{output_path}.png", quality=95)

def _get_curve_points(x1: int, y1: int, x2: int, y2: int) -> List[Tuple[int, int]]:
    """Generate points for a curved line between two positions"""
    points = []
    steps = 50
    for i in range(steps + 1):
        t = i / steps
        # Quadratic bezier curve
        mid_y = (y1 + y2) / 2
        cx = (x1 + x2) / 2
        x = (1-t)**2 * x1 + 2*(1-t)*t*cx + t**2 * x2
        y = (1-t)**2 * y1 + 2*(1-t)*t*mid_y + t**2 * y2
        points.append((int(x), int(y)))
    return points