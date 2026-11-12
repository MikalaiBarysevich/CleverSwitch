from enum import StrEnum


class Edge(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


# In a corner, horizontal edges win.
EDGE_PRIORITY = (Edge.LEFT, Edge.RIGHT, Edge.TOP, Edge.BOTTOM)
