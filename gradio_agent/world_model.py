from dataclasses import dataclass
from typing import Dict, Tuple

Vec3  = Tuple[float, float, float] # (x, y, z)

@dataclass
class WorldModel:
    """Runtime map"""
    def __init__(self) -> None:
        self.locations: Dict[str, Vec3] = {"user": (0.0, 0.0, 0.0)} 
        # hardcode user since user is "invisible", the rest will be appended later
        self.objects: Dict[str, Tuple[str, Vec3 | None]] = {}
        self.robot_location: Vec3 | None = None  # Robot's current location in world coordinates
    
    # helper functions to get string representations
    def _format_xyz(self, p: Vec3) -> str:
        """formatting helper (x,y,z)"""
        return f"(x={p[0]:.2f}, y={p[1]:.2f}, z={p[2]:.2f})"

    def to_string(self) -> str:
        """
        Render the entire world model into a deterministic, multi-line string
        that can be pasted as-is into an LLM prompt.
        """
        lines: list[str] = []
        # robot location
        if self.robot_location is None:
            lines.append("# Robot location: unknown")
        else:
            lines.append(f"# Robot location: world coordinates {self._format_xyz(self.robot_location)}")
            
        # locations
        lines.append("\n# Locations")
        if not self.locations:
            lines.append("- (none)")
        else:

            for loc_name, coords in sorted(self.locations.items()):
                if coords is None:
                    lines.append(f"- {loc_name}: coordinates unknown")
                else:
                    lines.append(
                        f"- {loc_name} world coordinates {self._format_xyz(coords)}"
                )

        # objects
        lines.append("\n# Objects")
        if not self.objects:
            lines.append("- (none)")
        else:

            for obj_name, (location, coords) in sorted(self.objects.items()):
                if coords is None:
                    lines.append(f"- {obj_name}: at {location}")
                else:
                    lines.append(
                        f"- {obj_name}: at {location} with world coordinates {self._format_xyz(coords)}"
                )

        print("\n".join(lines)) # debug print
        return "\n".join(lines)
