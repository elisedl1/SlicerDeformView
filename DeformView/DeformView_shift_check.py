"""
DeformView vs. known deformation: is a peak-displacement gap from DeformView or the registration?

Run in the 3D Slicer Python console:
    exec(open(r"/path/to/deformview_shift_check.py").read())
    part1()                       # ground truth only, no registration
    # ...register in the GUI (see printed instructions)...
    part2("ANTsTransform")        # compare the registration result with the truth

Part 1 builds a smooth, brain-shift-like displacement field with a known analytic peak,
loads it into Slicer as a grid transform and runs DeformView on it. Any gap here comes from
DeformView itself, from sampling on the voxel grid, or from the display range.
It also writes a synthetic "intraoperative" image by warping MRHead with that field.

Part 2 takes the transform from your registration (fixed = SyntheticIntraop,
moving = MRHead) and compares it with the truth: peak values, peak locations and
voxel-wise vector error. Any gap here that was not present in Part 1 comes from the registration.
"""
import os
import tempfile
import numpy as np
import SimpleITK as sitk
import sitkUtils
import slicer

# ---------------------------------------------------------------- settings
PEAK_MM = 5.0                            # analytic peak displacement
SIGMA_MM = 12.0                          # spatial extent of the shift (Gaussian width)
DIRECTION_LPS = np.array([0.3, 0.0, -1.0])  # mostly inferior "sinking", slightly lateral
CENTRE_OFFSET_LPS = np.array([0.37, 0.21, 35.0])  # from volume centre; off-grid on purpose
BRAIN_THRESHOLD = 40                     # MRHead intensity used for a rough head mask


# ---------------------------------------------------------------- pure helpers (no Slicer)
def physical_points(image):
    """LPS coordinates of every voxel centre, shape (k, j, i, 3)."""
    ni, nj, nk = image.GetSize()
    k, j, i = np.meshgrid(np.arange(nk), np.arange(nj), np.arange(ni), indexing="ij")
    scaled = np.stack([i, j, k], axis=-1).astype(np.float64) * np.array(image.GetSpacing())
    return np.array(image.GetOrigin()) + scaled @ np.array(image.GetDirection()).reshape(3, 3).T


def gaussian_shift(points, centre, peak=PEAK_MM, sigma=SIGMA_MM, direction=DIRECTION_LPS):
    """Resampling displacement u(x) = peak * exp(-|x-c|^2 / 2 sigma^2) * d.  Analytic max = peak at x = c."""
    d = direction / np.linalg.norm(direction)
    r2 = np.sum((points - centre) ** 2, axis=-1)
    return (peak * np.exp(-r2 / (2.0 * sigma ** 2)))[..., None] * d


def field_image(displacement, reference):
    field = sitk.GetImageFromArray(displacement.astype(np.float64), isVector=True)
    field.SetOrigin(reference.GetOrigin())
    field.SetSpacing(reference.GetSpacing())
    field.SetDirection(reference.GetDirection())
    return field


def sampled_field(transform, reference):
    """Displacement vectors of any SimpleITK transform at the reference voxel centres (as DeformView samples)."""
    f = sitk.TransformToDisplacementField(transform, sitk.sitkVectorFloat64, reference.GetSize(),
                                          reference.GetOrigin(), reference.GetSpacing(), reference.GetDirection())
    return sitk.GetArrayFromImage(f)


def colour_bar_range(display_node):
    w, l = display_node.GetWindow(), display_node.GetLevel()
    return l - w / 2.0, l + w / 2.0


# ---------------------------------------------------------------- Slicer glue
def _save_and_load(sitk_transform, name):
    path = os.path.join(tempfile.gettempdir(), name + ".h5")
    sitk.WriteTransform(sitk_transform, path)
    node = slicer.util.loadTransform(path)
    node.SetName(name)
    return node


def _node_to_sitk(transform_node):
    """Exactly how DeformView reads a transform: save to .h5, read back with SimpleITK."""
    path = os.path.join(tempfile.gettempdir(), "_deformview_check_tmp.h5")
    slicer.util.saveNode(transform_node, path)
    tx = sitk.ReadTransform(path)
    os.remove(path)
    return tx


def _deformview_displacement(reference_node, transform_node):
    import DeformView
    color = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLColorTableNode")
    volume = DeformView.DeformViewLogic().computeDisplacementMagnitude(
        reference_node, transform_node, color.GetID(), scale=1.0)
    return volume, slicer.util.arrayFromVolume(volume).astype(np.float64)


_state = {}


def part1():
    import SampleData
    source = slicer.util.getFirstNodeByName("MRHead") or SampleData.SampleDataLogic().downloadMRHead()
    ref = sitkUtils.PullVolumeFromSlicer(source)
    points = physical_points(ref)
    centre = points.reshape(-1, 3).mean(axis=0) + CENTRE_OFFSET_LPS

    truth = gaussian_shift(points, centre)
    truth_node = _save_and_load(sitk.DisplacementFieldTransform(field_image(truth, ref)), "TruthTransform")

    # Synthetic intraoperative image: what the source looks like after the known shift.
    warp = _node_to_sitk(truth_node)
    target = sitk.Resample(ref, ref, warp, sitk.sitkLinear, 0.0)
    target_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "SyntheticIntraop")
    sitkUtils.PushVolumeToSlicer(target, target_node)

    # DeformView on the ground-truth transform (reference = the fixed/intraop image, as in normal use).
    dv_volume, dv = _deformview_displacement(target_node, truth_node)
    truth_mag = np.linalg.norm(truth, axis=-1)
    nearest = np.min(np.linalg.norm(points - centre, axis=-1))
    lo, hi = colour_bar_range(dv_volume.GetDisplayNode())

    print("\n=== PART 1: DeformView on the known field (no registration) ===")
    print(f"Analytic peak (continuous)                : {PEAK_MM:.4f} mm")
    print(f"Peak sampled on the voxel grid            : {truth_mag.max():.4f} mm "
          f"(nearest voxel is {nearest:.2f} mm from the true peak)")
    print(f"DeformView peak (max of data)             : {dv.max():.4f} mm")
    print(f"DeformView vs grid-sampled truth, max diff: {np.abs(dv - truth_mag).max():.2e} mm")
    print(f"Colour bar range shown by default         : {lo:.3f} to {hi:.3f} mm")
    print("  -> If the colour bar top differs from the data max, reading the peak off the colour bar is misleading.")

    _state.update(ref=ref, points=points, centre=centre, truth=truth, target_node=target_node)
    print("\nNext: register in the GUI with FIXED = 'SyntheticIntraop', MOVING = 'MRHead', using the same")
    print("ANTs settings as the reporter. Name the output transform, then run part2('<that name>').")


def part2(registration_transform_name):
    if not _state:
        raise RuntimeError("Run part1() first.")
    ref, points, centre, truth = _state["ref"], _state["points"], _state["centre"], _state["truth"]
    reg_node = slicer.util.getNode(registration_transform_name)

    reg = sampled_field(_node_to_sitk(reg_node), ref)        # full vectors, same sampling as DeformView
    _, dv = _deformview_displacement(_state["target_node"], reg_node)
    truth_mag, reg_mag = np.linalg.norm(truth, axis=-1), np.linalg.norm(reg, axis=-1)
    vector_error = np.linalg.norm(reg - truth, axis=-1)
    head = sitk.GetArrayFromImage(ref) > BRAIN_THRESHOLD
    shifted = truth_mag > 0.1 * PEAK_MM                      # where the simulated shift is non-trivial

    t_peak = np.unravel_index(np.argmax(truth_mag), truth_mag.shape)
    r_peak = np.unravel_index(np.argmax(reg_mag), reg_mag.shape)
    peak_distance = np.linalg.norm(points[t_peak] - points[r_peak])

    print("\n=== PART 2: registration result vs. the known field ===")
    print(f"DeformView reproduces the registration transform: max diff {np.abs(dv - reg_mag).max():.2e} mm")
    print(f"Peak |u|  truth: {truth_mag.max():.3f} mm    registration: {reg_mag.max():.3f} mm    "
          f"difference: {reg_mag.max() - truth_mag.max():+.3f} mm")
    print(f"Peak locations are {peak_distance:.1f} mm apart")
    print(f"Registration |u| at the TRUE peak voxel: {reg_mag[t_peak]:.3f} mm")
    print(f"Vector error in the shifted region : mean {vector_error[shifted].mean():.3f} mm, "
          f"95th pct {np.percentile(vector_error[shifted], 95):.3f} mm, max {vector_error[shifted].max():.3f} mm")
    print(f"Vector error elsewhere in the head : mean {vector_error[head & ~shifted].mean():.3f} mm")
    print("\nReading the result:")
    print("  - Part 1 gap ~0 and Part 2 gap ~0.3 mm  -> the registration under-/over-recovers the peak, not DeformView.")
    print("  - Large peak-location distance or error outside the shifted region -> registration settings or")
    print("    fixed/moving swapped (the transform would then be the inverse of the truth).")