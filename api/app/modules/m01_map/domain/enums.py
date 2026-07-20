import enum


class Preset(enum.Enum):
    drive = "drive"
    tonight = "tonight"
    work = "work"
    fuel = "fuel"


class NavProvider(enum.Enum):
    google = "google"
    apple = "apple"
    hammer = "hammer"
    copilot = "copilot"
