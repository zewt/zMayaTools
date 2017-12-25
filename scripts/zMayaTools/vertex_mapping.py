from pymel import core as pm
from maya import cmds
from zMayaTools import kdtree

class PointWithIndex(object):
    """
    A helper for storing vertex indices along with vertices in kdtree.
    """

    def __init__(self, point, idx):
        self.coords = point
        self.idx = idx

    def __len__(self):
        return len(self.coords)

    def __getitem__(self, i):
        return self.coords[i]

    def __repr__(self):
        return 'Item({}, {}, {})'.format(self.coords[0], self.coords[1], self.idx)

def make_vertex_symmetry_map(shape, threshold=0.01, axis_of_symmetry='x', positive_to_negative=True):
    """
    Given a shape, make a mapping from vertices on one side to matching vertices on the
    other side.

    Return a map of {dst: src} vertex indices and a list of target vertices that weren't matched.
    """
    axes = {'x': 0, 'y': 1, 'z': 2}
    axis_of_symmetry = axes[axis_of_symmetry]
    
    vertices = cmds.xform('%s.vtx[*]' % shape, q=True, ws=True, t=True)
    vertices = [(x, y, z) for x, y, z in zip(vertices[0::3], vertices[1::3], vertices[2::3])]
    vertices = [PointWithIndex(vtx, idx) for idx, vtx in enumerate(vertices)]

    def is_destination_vertex(idx):
        if positive_to_negative and p[axis_of_symmetry] >= -0.0001:
            return False
        if not positive_to_negative and p[axis_of_symmetry] <= +0.0001:
            return False
        return True

    # Make a tree of the vertex positions.
    tree = kdtree.create(vertices)

    index_mapping = {}
    unmapped_dst_vertices = set()
    for dst_idx, p in enumerate(vertices):
        # If this vertex is on the wrong side, skip it.
        if not is_destination_vertex(dst_idx):
            continue
            
        p = (-p[0], p[1], p[2])
        node, distance = tree.search_nn(p)
        src_idx = node.data.idx

        if distance > threshold:
            # We don't have a match.  Remember that this vertex was unmatched.
            unmapped_dst_vertices.add(dst_idx)
        else:
            index_mapping[dst_idx] = src_idx
            
    return index_mapping, unmapped_dst_vertices
    
def make_vertex_map(src_shape, dst_shape, threshold=0.01):
    """
    Given two shape, make a mapping from vertices on the first shape to matching vertices
    on the second shape.  Unmatched vertices will be mapped to -1.
    
    Return a map of {dst: src} vertex indices and a list of vertices that weren't matched.
    """
    shapes = (src_shape, dst_shape)
    shape_vertices = []
    for shape in shapes:
        vertices = cmds.xform('%s.vtx[*]' % shape, q=True, ws=True, t=True)
        vertices = [(x, y, z) for x, y, z in zip(vertices[0::3], vertices[1::3], vertices[2::3])]
        vertices = [PointWithIndex(vtx, idx) for idx, vtx in enumerate(vertices)]
        shape_vertices.append(vertices)

    # Make a tree of the vertex positions in the first (source) shape.
    src_tree = kdtree.create(shape_vertices[0])

    index_mapping = {}
    unmapped_dst_vertices = set()
    for dst_vtx in shape_vertices[1]:
        node, distance = src_tree.search_nn(dst_vtx)

        src_idx = node.data.idx
        dst_idx = dst_vtx.idx
        if distance > threshold:
            # We don't have a match.  Remember that this vertex was unmatched.
            unmapped_dst_vertices.add(dst_idx)
            index_mapping[dst_idx] = -1
        else:
            index_mapping[dst_idx] = src_idx
            
    return index_mapping, unmapped_dst_vertices
    

