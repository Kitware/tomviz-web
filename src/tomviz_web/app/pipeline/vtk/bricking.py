"""Split an image too large for one GPU 3D texture into bricks, as the
desktop's ``VolumeBricking`` does, for ``vtkMultiBlockVolumeMapper``.

Neighboring bricks share a one-voxel boundary so the interpolation is
seamless across them. Each brick holds a copy of its voxels."""

from __future__ import annotations

from vtkmodules.vtkCommonDataModel import vtkImageData, vtkMultiBlockDataSet
from vtkmodules.vtkImagingCore import vtkExtractVOI
from vtkmodules.vtkRenderingOpenGL2 import vtkTextureObject

# The smallest GL_MAX_3D_TEXTURE_SIZE to expect: bricking to it is always
# safe, used while the GPU cannot be asked.
FALLBACK_TEXTURE_SIZE = 2048


def maximum_texture_size(render_window) -> int:
    """The GPU's 3D texture size limit, or the fallback while the window
    has no current context to ask."""
    try:
        if not render_window.GetNeverRendered():
            render_window.MakeCurrent()
            size = vtkTextureObject.GetMaximumTextureSize3D(render_window)
            if size > 0:
                return size
    except (AttributeError, TypeError):
        pass
    return FALLBACK_TEXTURE_SIZE


def exceeds_texture_limit(image: vtkImageData, limit: int) -> bool:
    return any(n > limit for n in image.GetDimensions())


def block_count(length: int, limit: int) -> int:
    """Bricks along an axis of ``length`` points: each brick of at most
    ``limit`` points advances by ``limit - 1`` (the shared boundary)."""
    if limit < 2:
        return max(1, length)
    if length <= limit:
        return 1
    return -(-(length - 1) // (limit - 1))


def axis_cuts(first: int, last: int, count: int) -> list[int]:
    """``count + 1`` boundaries from ``first`` to ``last``, as even as the
    integers allow; consecutive bricks share one."""
    return [first + round((last - first) * k / count) for k in range(count + 1)]


def brick_volume(image: vtkImageData, limit: int) -> vtkMultiBlockDataSet:
    blocks = vtkMultiBlockDataSet()
    extent = image.GetExtent()
    cuts = [
        axis_cuts(
            extent[2 * a],
            extent[2 * a + 1],
            block_count(extent[2 * a + 1] - extent[2 * a] + 1, limit),
        )
        for a in range(3)
    ]
    for kz in range(len(cuts[2]) - 1):
        for ky in range(len(cuts[1]) - 1):
            for kx in range(len(cuts[0]) - 1):
                voi = vtkExtractVOI()
                voi.SetInputData(image)
                voi.SetVOI(
                    cuts[0][kx],
                    cuts[0][kx + 1],
                    cuts[1][ky],
                    cuts[1][ky + 1],
                    cuts[2][kz],
                    cuts[2][kz + 1],
                )
                voi.Update()
                brick = vtkImageData()
                brick.ShallowCopy(voi.GetOutput())
                blocks.SetBlock(blocks.GetNumberOfBlocks(), brick)
    return blocks
