"""Self-tests for the DeformView module.

This file is imported at the bottom of DeformView.py so that Slicer's
"Reload and Test" button works. It is also run by the Slicer Continuous Integration system, so it must not require any external data or network access. 
"""

import logging
import os
import tempfile

import numpy as np
import SimpleITK as sitk
import sitkUtils
import slicer
from slicer.ScriptedLoadableModule import ScriptedLoadableModuleTest
import vtk


class DeformViewTest(ScriptedLoadableModuleTest):
    """Self-test for DeformView.

    Uses only synthetic, in-memory data, so no downloads are needed. Each
    test builds a transform whose displacement field and Jacobian determinant
    are known in closed form, runs DeformView's logic on it, and checks the
    output at every voxel against the analytic value.

    Cases:
      * Pure translation t: |u| = |t| everywhere, volume change = 0 %.
      * Affine scaling A about centre c (uniform expansion, uniform
        compression, and a per-axis stretch/compress): u(x) = (A - I)(x - c),
        so |u| = |(A - I)(x - c)| and volume change = (det(A) - 1) * 100 %.
      * Increment Transform: resampling with a half-scaled transform
        reproduces an exact one-voxel shift of the source image.

    The reference volume uses anisotropic spacing and Slicer's default RAS
    orientation (an LPS direction matrix of diag(-1, -1, 1) on the ITK side),
    so errors in spacing or direction handling are caught.
        * Oblique volume: the reference volume is tilted 30° about S and 15° about R. 
        Run two cases on it: the per-axis stretch, and a general affine with shear (volume change +25.5%).
        
        * Non-linear transform (grid transform) the same general 
        affine field is sampled onto a 2 mm displacement grid and loaded as 
        a non-linear transform, once on a default volume and once on a tilted 
        one. The test also confirms that Slicer loaded it as non-linear. 
        Linear interpolation reproduces a linear field exactly, so the expected values are still exact.

    Maximum errors are logged so they can be reported.
    """

    # Tolerances. The computations are exact up to floating point for these transforms
    DISPLACEMENT_TOL_MM = 1e-3
    JACOBIAN_TOL_PERCENT = 1e-2
    INTENSITY_TOL = 1e-3

    def setUp(self):
        slicer.mrmlScene.Clear()
        self.maxErrors = {}

    def runTest(self):
        self.setUp()
        self.test_LogicApiPresent()
        self.setUp()
        self.test_DisplacementAndJacobian()
        self.setUp()
        self.test_TranslationAnalytic()
        self.setUp()
        self.test_AffineScalingAnalytic()
        self.setUp()
        self.test_IncrementalTransformShift()
        self.setUp()
        self.test_AffineScalingObliqueVolume()
        self.setUp()
        self.test_GridTransformAnalytic()
        self.setUp()
        self.test_NonLinearGridTransform()
        self.setUp()
        self.test_NonLinearBSplineTransform()
        self.setUp()
        self.test_NonLinearThinPlateSplineTransform()

    # ------------------------------------------------------------------ helpers

    def _makeReferenceVolume(self, name, shapeKJI=(20, 24, 28), spacing=(0.8, 1.0, 1.5), seed=0):
        """Random-intensity volume with anisotropic spacing and default RAS orientation."""
        voxels = (np.random.RandomState(seed).rand(*shapeKJI) * 100.0).astype(np.float32)
        volumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", name)
        slicer.util.updateVolumeFromArray(volumeNode, voxels)
        volumeNode.SetSpacing(*spacing)
        volumeNode.SetOrigin(0.0, 0.0, 0.0)
        volumeNode.CreateDefaultDisplayNodes()
        return volumeNode, voxels

    def _loadSitkTransform(self, sitkTransform):
        """Load a SimpleITK transform into the scene the same way a user would (from an .h5 file)."""
        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
            txPath = tmp.name
        try:
            sitk.WriteTransform(sitkTransform, txPath)
            transformNode = slicer.util.loadTransform(txPath)
        finally:
            os.remove(txPath)
        self.assertIsNotNone(transformNode)
        return transformNode

    def _physicalPointsLPS(self, volumeNode):
        """LPS physical coordinates of every voxel centre, shape (k, j, i, 3).

        The transform file and DeformView's computations are both in ITK's LPS
        space, so expected values are computed there too.
        """
        image = sitkUtils.PullVolumeFromSlicer(volumeNode)
        ni, nj, nk = image.GetSize()
        k, j, i = np.meshgrid(np.arange(nk), np.arange(nj), np.arange(ni), indexing="ij")
        scaledIndex = np.stack([i, j, k], axis=-1).astype(np.float64) * np.array(image.GetSpacing())
        direction = np.array(image.GetDirection()).reshape(3, 3)
        return np.array(image.GetOrigin()) + scaledIndex @ direction.T

    def _logic(self):
        """Import the logic to avoid a circular import with DeformView.py."""
        from DeformView import DeformViewLogic
        return DeformViewLogic()

    def _colorId(self):
        colorNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLColorTableNode")
        if colorNode is None:
            colorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", "TestColors")
            colorNode.SetTypeToRainbow()
        return colorNode.GetID()

    def _checkVolume(self, volumeNode, referenceShape):
        """Common checks: output exists, geometry preserved, all values finite."""
        self.assertIsNotNone(volumeNode)
        array = slicer.util.arrayFromVolume(volumeNode).astype(np.float64)
        self.assertEqual(array.shape, referenceShape)
        self.assertTrue(np.all(np.isfinite(array)), "Output contains NaN or inf")
        return array

    def _assertMaxError(self, actual, expected, tol, label):
        maxError = float(np.max(np.abs(actual - expected)))
        self.maxErrors[label] = maxError
        logging.info(f"DeformViewTest {label}: max abs error = {maxError:.3e}")
        self.assertLessEqual(
            maxError, tol,
            f"{label}: max abs error {maxError:.3e} exceeds tolerance {tol:.1e}")

    # -------------------------------------------------------------------- tests


    def test_LogicApiPresent(self):
        """Smoke test: module loads and the logic API is intact."""
        self.delayDisplay("Starting: logic API presence")
        logic = self._logic()
        self.assertIsNotNone(logic)
        for name in ("computeDisplacementMagnitude", "computeJacobianMagnitude",
                     "createIncrementalTransform", "countUniqueValues"):
            self.assertTrue(callable(getattr(logic, name, None)),
                            f"DeformViewLogic is missing method: {name}")
        self.delayDisplay("Passed: logic API presence")

    def test_TranslationAnalytic(self):
        """Oblique pure translation: |u| = |t| and 0 % volume change at every voxel."""
        self.delayDisplay("Starting: translation (analytic)")
        referenceVolume, voxels = self._makeReferenceVolume("TranslationReference")
        translationMm = np.array([1.5, -2.0, 0.5])
        transformNode = self._loadSitkTransform(
            sitk.TranslationTransform(3, tuple(translationMm)))
        logic = self._logic()
        colorId = self._colorId()

        disp = self._checkVolume(
            logic.computeDisplacementMagnitude(referenceVolume, transformNode, colorId, scale=1.0),
            voxels.shape)
        self._assertMaxError(disp, np.linalg.norm(translationMm),
                             self.DISPLACEMENT_TOL_MM, "translation displacement (mm)")

        # A constant displacement field has zero gradient, so this holds at the
        # image border too.
        jac = self._checkVolume(
            logic.computeJacobianMagnitude(referenceVolume, transformNode, colorId),
            voxels.shape)
        self._assertMaxError(jac, 0.0, self.JACOBIAN_TOL_PERCENT, "translation volume change (%)")

        self.delayDisplay("Passed: translation (analytic)")

    def test_AffineScalingAnalytic(self):
        """Affine scaling about the volume centre: u(x) = (A - I)(x - c).

        Expected displacement magnitude is |(A - I)(x - c)|; expected volume
        change is (det(A) - 1) * 100 %, constant over the volume.
        """
        self.delayDisplay("Starting: affine scaling (analytic)")
        cases = {
            "uniform expansion": np.diag([1.2, 1.2, 1.2]),    # +72.8 %
            "uniform compression": np.diag([0.9, 0.9, 0.9]),  # -27.1 %
            "per-axis stretch": np.diag([1.2, 1.0, 0.9]),     # +8.0 %; catches axis sign errors
        }
        logic = self._logic()

        for caseName, matrix in cases.items():
            slicer.mrmlScene.Clear()
            referenceVolume, voxels = self._makeReferenceVolume("ScalingReference")
            points = self._physicalPointsLPS(referenceVolume)
            centre = points.reshape(-1, 3).mean(axis=0)

            affine = sitk.AffineTransform(3)
            affine.SetMatrix(tuple(matrix.ravel()))
            affine.SetCenter(tuple(centre))
            transformNode = self._loadSitkTransform(affine)
            colorId = self._colorId()

            disp = self._checkVolume(
                logic.computeDisplacementMagnitude(referenceVolume, transformNode, colorId, scale=1.0),
                voxels.shape)
            expectedDisp = np.linalg.norm((points - centre) @ (matrix - np.eye(3)).T, axis=-1)
            self._assertMaxError(disp, expectedDisp, self.DISPLACEMENT_TOL_MM,
                                 f"{caseName} displacement (mm)")

            jac = self._checkVolume(
                logic.computeJacobianMagnitude(referenceVolume, transformNode, colorId),
                voxels.shape)
            expectedJac = (np.linalg.det(matrix) - 1.0) * 100.0
            # The Jacobian filter uses finite differences, which are one-sided
            # at the image border, so only interior voxels are compared.
            self._assertMaxError(jac[1:-1, 1:-1, 1:-1], expectedJac, self.JACOBIAN_TOL_PERCENT,
                                 f"{caseName} volume change (%)")

        self.delayDisplay("Passed: affine scaling (analytic)")

    def test_IncrementalTransformShift(self):
        """Increment Transform: half of a 2-voxel shift is exactly a 1-voxel shift.

        A 4 mm translation along S on a grid with 2 mm slice spacing, applied at
        scale 0.5, must shift the image by exactly one slice. Linear
        interpolation is exact at whole-voxel offsets.
        """
        self.delayDisplay("Starting: incremental transform")
        backgroundVolume, voxels = self._makeReferenceVolume(
            "IncrementBackground", shapeKJI=(12, 10, 8), spacing=(1.0, 1.0, 2.0), seed=1)
        # Translation along the third (S) axis, which has the same sign in RAS and LPS.
        transformNode = self._loadSitkTransform(sitk.TranslationTransform(3, (0.0, 0.0, 4.0)))
        logic = self._logic()

        outputVolume = logic.createIncrementalTransform(
            backgroundVolume, transformNode, 0.5, "IncrementTest")
        output = self._checkVolume(outputVolume, voxels.shape)

        # Resampling samples the source at x + u(x), so output slice k equals
        # source slice k + 1. The last slice samples outside the image.
        self._assertMaxError(output[:-1], voxels[1:].astype(np.float64),
                             self.INTENSITY_TOL, "incremental 50% shift (intensity)")

        self.delayDisplay("Passed: incremental transform")



    def test_DisplacementAndJacobian(self):
        """Functional test: run both maps on a synthetic translation."""
        self.delayDisplay("Starting: displacement + Jacobian")

        # 1. Synthetic reference volume (array shape is k, j, i).
        voxels = (np.random.RandomState(0).rand(20, 24, 28) * 100.0).astype(np.float32)
        referenceVolume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode", "TestReference")
        slicer.util.updateVolumeFromArray(referenceVolume, voxels)
        referenceVolume.SetSpacing(1.0, 1.0, 1.0)
        referenceVolume.SetOrigin(0.0, 0.0, 0.0)

        # 2. Synthetic transform: a pure 2 mm translation.
        translationMm = 2.0
        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
            txPath = tmp.name
        sitk.WriteTransform(sitk.TranslationTransform(3, (translationMm, 0.0, 0.0)), txPath)
        transformNode = slicer.util.loadTransform(txPath)
        os.remove(txPath)
        self.assertIsNotNone(transformNode)

        # 3. A colour table node; the compute methods want its ID *string*.
        colorNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLColorTableNode")
        if colorNode is None:
            colorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", "TestColors")
            colorNode.SetTypeToRainbow()
        colorId = colorNode.GetID()

        logic = self._logic()

        # 4. Displacement magnitude.
        dispVol = logic.computeDisplacementMagnitude(referenceVolume, transformNode, colorId, scale=1.0)
        self.assertIsNotNone(dispVol)
        disp = slicer.util.arrayFromVolume(dispVol)
        self.assertEqual(disp.shape, voxels.shape)        # geometry preserved
        self.assertTrue(np.all(np.isfinite(disp)))        # no NaN / inf
        self.assertTrue(np.all(disp >= 0.0))              # magnitude is non-negative
        self.assertAlmostEqual(float(np.median(disp)), translationMm, delta=0.5)  # tune if needed

        # 5. Jacobian determinant (percentage volume change).
        jacVol = logic.computeJacobianMagnitude(referenceVolume, transformNode, colorId)
        self.assertIsNotNone(jacVol)
        jac = slicer.util.arrayFromVolume(jacVol)
        self.assertEqual(jac.shape, voxels.shape)
        self.assertTrue(np.all(np.isfinite(jac)))
        self.assertLess(abs(float(np.median(jac))), 1.0)  # translation is volume-preserving; tune if needed

        self.delayDisplay("Passed: displacement + Jacobian")

    # A general affine matrix (stretch, compression and shear), det = 1.2550.
    # Used by both tests below so the expected values are identical. - Should we add numerous matrices to test more cases -IJZF
    GENERAL_AFFINE = np.array([[1.10, 0.20, 0.00],
                               [0.00, 0.95, 0.10],
                               [0.05, 0.00, 1.20]])

    def _setObliqueOrientation(self, volumeNode, degreesAboutS=30.0, degreesAboutR=15.0):
        """Tilt the volume's IJK axes relative to RAS, like an oblique clinical acquisition."""
        a, b = np.deg2rad(degreesAboutS), np.deg2rad(degreesAboutR)
        aboutS = np.array([[np.cos(a), -np.sin(a), 0.0],
                           [np.sin(a),  np.cos(a), 0.0],
                           [0.0,        0.0,       1.0]])
        aboutR = np.array([[1.0, 0.0,        0.0],
                           [0.0, np.cos(b), -np.sin(b)],
                           [0.0, np.sin(b),  np.cos(b)]])
        directions = aboutS @ aboutR
        matrix = vtk.vtkMatrix4x4()
        for row in range(3):
            for col in range(3):
                matrix.SetElement(row, col, directions[row, col])
        volumeNode.SetIJKToRASDirectionMatrix(matrix)

    def _affineTransform(self, matrix, centre):
        affine = sitk.AffineTransform(3)
        affine.SetMatrix(tuple(matrix.ravel()))
        affine.SetCenter(tuple(centre))
        return affine

    def _gridTransform(self, matrix, centre, points, gridSpacingMm=2.0, marginMm=4.0):
        """The same field u(x) = (A - I)(x - c), sampled on a displacement grid.

        The grid covers the reference volume plus a margin. Linear
        interpolation reproduces a linear field exactly, so the expected
        values are the same as for the affine transform.
        """
        flat = points.reshape(-1, 3)
        low = flat.min(axis=0) - marginMm
        high = flat.max(axis=0) + marginMm
        size = np.ceil((high - low) / gridSpacingMm).astype(int) + 1
        k, j, i = np.meshgrid(np.arange(size[2]), np.arange(size[1]), np.arange(size[0]), indexing="ij")
        gridPoints = low + np.stack([i, j, k], axis=-1) * gridSpacingMm
        displacement = (gridPoints - centre) @ (matrix - np.eye(3)).T
        field = sitk.GetImageFromArray(displacement.astype(np.float64), isVector=True)
        field.SetOrigin(tuple(low))
        field.SetSpacing((gridSpacingMm,) * 3)
        return sitk.DisplacementFieldTransform(field)

    def _checkAffineField(self, referenceVolume, voxels, transformNode, matrix, centre, points, label):
        """Compare both maps with u(x) = (A - I)(x - c) and det(A)."""
        logic = self._logic()
        colorId = self._colorId()

        disp = self._checkVolume(
            logic.computeDisplacementMagnitude(referenceVolume, transformNode, colorId, scale=1.0),
            voxels.shape)
        expectedDisp = np.linalg.norm((points - centre) @ (matrix - np.eye(3)).T, axis=-1)
        self._assertMaxError(disp, expectedDisp, self.DISPLACEMENT_TOL_MM, f"{label} displacement (mm)")

        jac = self._checkVolume(
            logic.computeJacobianMagnitude(referenceVolume, transformNode, colorId),
            voxels.shape)
        expectedJac = (np.linalg.det(matrix) - 1.0) * 100.0
        self._assertMaxError(jac[1:-1, 1:-1, 1:-1], expectedJac, self.JACOBIAN_TOL_PERCENT,
                             f"{label} volume change (%)")

    def test_AffineScalingObliqueVolume(self):
        """Affine scaling on a reference volume tilted relative to the scanner axes.

        Real scans are often acquired obliquely. This checks that orientation
        is handled correctly when the volume axes are not aligned with RAS.
        """
        self.delayDisplay("Starting: affine scaling on oblique volume")
        cases = {
            "oblique per-axis stretch": np.diag([1.2, 1.0, 0.9]),
            "oblique general affine": self.GENERAL_AFFINE,
        }
        for caseName, matrix in cases.items():
            slicer.mrmlScene.Clear()
            referenceVolume, voxels = self._makeReferenceVolume("ObliqueReference")
            self._setObliqueOrientation(referenceVolume)
            points = self._physicalPointsLPS(referenceVolume)
            centre = points.reshape(-1, 3).mean(axis=0)
            transformNode = self._loadSitkTransform(self._affineTransform(matrix, centre))
            self._checkAffineField(referenceVolume, voxels, transformNode, matrix, centre, points, caseName)
        self.delayDisplay("Passed: affine scaling on oblique volume")

    def test_GridTransformAnalytic(self):
        """The same analytic field loaded as a grid (displacement-field) transform.

        Exercises the non-linear transform loading path used for real
        registration results, with exact expected values.
        """
        self.delayDisplay("Starting: grid transform (analytic)")
        cases = {
            "grid general affine": (self.GENERAL_AFFINE, False),
            "grid general affine, oblique volume": (self.GENERAL_AFFINE, True),
        }
        for caseName, (matrix, oblique) in cases.items():
            slicer.mrmlScene.Clear()
            referenceVolume, voxels = self._makeReferenceVolume("GridReference")
            if oblique:
                self._setObliqueOrientation(referenceVolume)
            points = self._physicalPointsLPS(referenceVolume)
            centre = points.reshape(-1, 3).mean(axis=0)
            transformNode = self._loadSitkTransform(self._gridTransform(matrix, centre, points))
            self.assertFalse(transformNode.IsLinear(),
                             "Transform was loaded as linear; expected a grid transform")
            self._checkAffineField(referenceVolume, voxels, transformNode, matrix, centre, points, caseName)
        self.delayDisplay("Passed: grid transform (analytic)")


    
    # DeformView computes the Jacobian with
    # central finite differences on the voxel grid. For a linear field these
    # are exact, but for a curved field the derivative along axis j has a
    # truncation error of at most (h_j^2 / 6) * max|d^3 u_i / dx_j^3|, where
    # h_j is the voxel spacing. That per-entry error is propagated to the
    # determinant with Hadamard's inequality:
    #     |det(G + E) - det(G)| <= prod_j(|g_j| + |e_j|) - prod_j |g_j|
    # (g_j, e_j = columns of the true gradient G and of the error bound E).
    # The resulting bound is proportional to h^2. Each field is tested at two
    # resolutions, and halving the spacing must cut the error by about 4x.
    # ======================================================================

    NONLINEAR_EXTENT_MM = 40.0
    NONLINEAR_SPACINGS = ((1.0, 1.2, 1.5), (0.5, 0.6, 0.75))  # coarse, then half
    TRUNCATION_SAFETY = 1.5         # margin on numerically estimated third derivatives
    REFERENCE_SLACK_PERCENT = 1e-4  # reference-Jacobian and ITK-vs-VTK round-off
    IMPLEMENTATION_TOL_MM = 1e-4    # DeformView (ITK) vs Slicer (VTK) displacement
    H2_RATIO_RANGE = (3.0, 5.0)     # error(h) / error(h/2); exactly 4 for pure h^2

    # Smooth field shared by the tests: amplitudes (mm) and wavenumbers (1/mm).
    SINE_AMPLITUDE = np.array([2.0, 1.5, 1.0])
    SINE_WAVENUMBER = 2.0 * np.pi / np.array([40.0, 36.0, 44.0])
    LPS_TO_RAS = np.array([-1.0, -1.0, 1.0])  # same flip in both directions

    # ------------------------------------------------------------ helpers

    def _makeCubeVolume(self, name, spacing):
        """Reference volume covering the same ~40 mm cube at any spacing."""
        dims = [int(round(self.NONLINEAR_EXTENT_MM / s)) + 1 for s in spacing]  # i, j, k
        return self._makeReferenceVolume(name, shapeKJI=tuple(dims[::-1]), spacing=spacing)

    def _fromParentLPS(self, transformNode, pointsLPS):
        """Evaluate Slicer's own (VTK) resampling transform at LPS points.

        This is an implementation independent of DeformView's ITK path, used as
        the reference for transforms without a closed-form expression.
        """
        from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
        flatRAS = np.ascontiguousarray(pointsLPS.reshape(-1, 3) * self.LPS_TO_RAS, dtype=np.float64)
        inPoints = vtk.vtkPoints()
        inPoints.SetData(numpy_to_vtk(flatRAS, deep=True))
        outPoints = vtk.vtkPoints()
        outPoints.SetDataTypeToDouble()  # single precision would ruin the finite differences
        transformNode.GetTransformFromParent().TransformPoints(inPoints, outPoints)
        outRAS = vtk_to_numpy(outPoints.GetData())
        return (outRAS * self.LPS_TO_RAS).reshape(pointsLPS.shape)

    @staticmethod
    def _finiteDifferenceGradient(evaluate, points, delta=1e-3):
        """Gradient G[..., i, j] = dT_i/dx_j by fine central differences (delta in mm)."""
        columns = [(evaluate(points + delta * e) - evaluate(points - delta * e)) / (2.0 * delta)
                   for e in np.eye(3)]
        return np.stack(columns, axis=-1)

    @staticmethod
    def _thirdDerivativeMax(evaluate, points, delta=0.25):
        """M[i, j] = max over the volume of |d^3 u_i / dx_j^3|, by finite differences."""
        result = np.zeros((3, 3))
        for j, e in enumerate(np.eye(3)):
            f = lambda s: evaluate(points + s * delta * e)
            third = (f(2) - 2.0 * f(1) + 2.0 * f(-1) - f(-2)) / (2.0 * delta ** 3)
            result[:, j] = np.abs(third).reshape(-1, 3).max(axis=0)
        return result

    @staticmethod
    def _truncationBound(gradient, thirdMax, spacing, safety):
        """Per-voxel bound on |det(finite-difference gradient) - det(true gradient)|.

        Entry bound e_ij = safety * (h_j^2 / 6) * M_ij, propagated through the
        determinant with Hadamard's inequality (see comment at the top).
        """
        entryBound = safety * thirdMax * (np.asarray(spacing, dtype=np.float64) ** 2 / 6.0)[None, :]
        gradientColumnNorms = np.linalg.norm(gradient, axis=-2)
        errorColumnNorms = np.linalg.norm(entryBound, axis=0)
        return (np.prod(gradientColumnNorms + errorColumnNorms, axis=-1)
                - np.prod(gradientColumnNorms, axis=-1))

    def _sineField(self, points, centre):
        """u_i(x) = a_i sin(k_i (x_i - c_i)), with its exact gradient and third-derivative maxima."""
        a, k = self.SINE_AMPLITUDE, self.SINE_WAVENUMBER
        displacement = a * np.sin(k * (points - centre))
        gradient = np.zeros(points.shape + (3,))
        for i in range(3):
            gradient[..., i, i] = 1.0 + a[i] * k[i] * np.cos(k[i] * (points[..., i] - centre[i]))
        return displacement, gradient, np.diag(a * k ** 3)

    def _checkNonLinearCase(self, caseName, buildTransform):
        """Run DeformView on a non-linear field at two resolutions and check both maps.

        buildTransform(referenceVolume, points, centre) returns
        (transformNode, analytic). analytic is None when the reference comes
        from Slicer's own evaluation of the transform, or a dict with
        'displacement', 'gradient', 'thirdMax' and optionally 'discreteJacobian'.
        """
        logic = self._logic()
        inner = (slice(1, -1),) * 3  # central differences are one-sided at the border
        maxJacobianErrors = []

        for level, spacing in enumerate(self.NONLINEAR_SPACINGS):
            slicer.mrmlScene.Clear()
            referenceVolume, voxels = self._makeCubeVolume(f"NonLinearReference{level}", spacing)
            points = self._physicalPointsLPS(referenceVolume)
            centre = points.reshape(-1, 3).mean(axis=0)
            transformNode, analytic = buildTransform(referenceVolume, points, centre)
            label = f"{caseName}, spacing {spacing}"

            if analytic is None:
                evaluate = lambda q: self._fromParentLPS(transformNode, q)
                expectedDisplacement = evaluate(points) - points
                gradient = self._finiteDifferenceGradient(evaluate, points)
                thirdMax = self._thirdDerivativeMax(evaluate, points)
                displacementTol = self.IMPLEMENTATION_TOL_MM
            else:
                expectedDisplacement = analytic["displacement"]
                gradient = analytic["gradient"]
                thirdMax = analytic["thirdMax"]
                displacementTol = self.DISPLACEMENT_TOL_MM

            colorId = self._colorId()
            try:
                displacementVolume = logic.computeDisplacementMagnitude(
                    referenceVolume, transformNode, colorId, scale=1.0)
                jacobianVolume = logic.computeJacobianMagnitude(referenceVolume, transformNode, colorId)
            except Exception as error:
                self.fail(f"{caseName}: DeformView could not process this transform type: {error}")

            # Displacement is sampled exactly at voxel centres: no truncation error.
            displacement = self._checkVolume(displacementVolume, voxels.shape)
            self._assertMaxError(displacement, np.linalg.norm(expectedDisplacement, axis=-1),
                                 displacementTol, f"{label} displacement (mm)")

            # Jacobian: error must stay within the h^2 truncation bound at every interior voxel.
            jacobian = self._checkVolume(jacobianVolume, voxels.shape)
            expectedJacobian = (np.linalg.det(gradient) - 1.0) * 100.0
            bound = 100.0 * self._truncationBound(gradient, thirdMax, spacing, self.TRUNCATION_SAFETY)
            error = np.abs(jacobian[inner] - expectedJacobian[inner])
            allowed = bound[inner] + self.REFERENCE_SLACK_PERCENT
            worstFraction = float(np.max(error / allowed))
            maxJacobianErrors.append(float(error.max()))
            self.maxErrors[f"{label} volume change (%)"] = float(error.max())
            logging.info(f"DeformViewTest {label} volume change (%): max abs error = {error.max():.3e}, "
                         f"max h^2 bound = {bound[inner].max():.3e}, worst error/bound = {worstFraction:.2f}")
            self.assertLessEqual(
                worstFraction, 1.0,
                f"{label}: volume-change error exceeds the h^2 truncation bound "
                f"(worst error/bound = {worstFraction:.2f})")

            # Optional exact check: the result must equal the central-difference formula itself.
            if analytic is not None and "discreteJacobian" in analytic:
                self._assertMaxError(jacobian[inner], analytic["discreteJacobian"][inner], 1e-6,
                                     f"{label} volume change vs exact central-difference value (%)")

        ratio = maxJacobianErrors[0] / maxJacobianErrors[1]
        logging.info(f"DeformViewTest {caseName}: error ratio when spacing is halved = {ratio:.2f} "
                     f"(4.0 expected for second-order accuracy)")
        low, high = self.H2_RATIO_RANGE
        self.assertTrue(low <= ratio <= high,
                        f"{caseName}: halving the spacing changed the error by {ratio:.2f}x; "
                        f"expected about 4x for second-order accuracy")

    # -------------------------------------------------------------- tests

    def test_NonLinearGridTransform(self):
        """Sinusoidal field as a grid (displacement-field) transform.

        The field is sampled on the reference grid, so displacement is exact at
        every voxel. The Jacobian has a closed form, and so does its
        central-difference approximation (each derivative is scaled by
        sin(k h) / (k h)), which DeformView must reproduce exactly.
        """
        self.delayDisplay("Starting: non-linear grid transform")

        def build(referenceVolume, points, centre):
            displacement, gradient, thirdMax = self._sineField(points, centre)
            image = sitkUtils.PullVolumeFromSlicer(referenceVolume)
            field = sitk.GetImageFromArray(displacement.astype(np.float64), isVector=True)
            field.SetOrigin(image.GetOrigin())
            field.SetSpacing(image.GetSpacing())
            field.SetDirection(image.GetDirection())
            transformNode = self._loadSitkTransform(sitk.DisplacementFieldTransform(field))
            self.assertFalse(transformNode.IsLinear(), "Grid transform was loaded as linear")

            a, k = self.SINE_AMPLITUDE, self.SINE_WAVENUMBER
            h = np.array(image.GetSpacing())  # default orientation: index axis i <-> physical axis i
            sinc = np.sin(k * h) / (k * h)
            discrete = 100.0 * (np.prod(1.0 + a * k * np.cos(k * (points - centre)) * sinc, axis=-1) - 1.0)
            return transformNode, {"displacement": displacement, "gradient": gradient,
                                   "thirdMax": thirdMax, "discreteJacobian": discrete}

        self._checkNonLinearCase("non-linear grid", build)
        self.delayDisplay("Passed: non-linear grid transform")

    def test_NonLinearBSplineTransform(self):
        """Cubic B-spline transform with smooth, sinusoidal control-point coefficients.

        The control grid covers the same physical cube at both resolutions, so
        the same continuous field is tested at each spacing. The reference is
        Slicer's own (VTK) evaluation of the transform.
        """
        self.delayDisplay("Starting: non-linear B-spline transform")

        def build(referenceVolume, points, centre):
            image = sitkUtils.PullVolumeFromSlicer(referenceVolume)
            box = sitk.Image([5, 5, 5], sitk.sitkFloat32)  # 40 mm cube, independent of voxel spacing
            box.SetSpacing((10.0, 10.0, 10.0))
            box.SetOrigin(image.GetOrigin())
            box.SetDirection(image.GetDirection())
            bspline = sitk.BSplineTransformInitializer(box, [4, 4, 4], order=3)

            fixed = np.array(bspline.GetFixedParameters())
            meshSize, gridOrigin, gridSpacing = fixed[0:3].astype(int), fixed[3:6], fixed[6:9]
            gridDirection = fixed[9:18].reshape(3, 3)
            counts = meshSize + 3  # control points per axis for a cubic B-spline
            k, j, i = np.meshgrid(*[np.arange(n) for n in counts[::-1]], indexing="ij")
            controlPoints = gridOrigin + (np.stack([i, j, k], axis=-1) * gridSpacing) @ gridDirection.T
            coefficients = 0.6 * self.SINE_AMPLITUDE * np.sin(
                self.SINE_WAVENUMBER * (controlPoints - centre) + np.array([0.3, 1.1, 2.0]))
            bspline.SetParameters(tuple(np.concatenate([coefficients[..., d].ravel() for d in range(3)])))

            transformNode = self._loadSitkTransform(bspline)
            self.assertFalse(transformNode.IsLinear(), "B-spline transform was loaded as linear")
            return transformNode, None

        self._checkNonLinearCase("non-linear B-spline", build)
        self.delayDisplay("Passed: non-linear B-spline transform")

    def test_NonLinearThinPlateSplineTransform(self):
        """Thin-plate spline transform built from landmarks in Slicer.

        26 landmarks sit on a shell 15 mm outside the volume, so the spline is
        smooth everywhere inside it. The reference is Slicer's own (VTK)
        evaluation of the transform.
        """
        self.delayDisplay("Starting: non-linear thin-plate spline transform")

        def build(referenceVolume, points, centre):
            flat = points.reshape(-1, 3)
            low, high = flat.min(axis=0) - 15.0, flat.max(axis=0) + 15.0
            axes = [[low[d], 0.5 * (low[d] + high[d]), high[d]] for d in range(3)]
            lattice = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
            source = np.delete(lattice, 13, axis=0)  # drop the centre point: no landmark inside the volume
            target = source + 1.5 * np.sin(self.SINE_WAVENUMBER * (source - centre) + np.array([0.5, 1.3, 2.1]))

            sourcePoints, targetPoints = vtk.vtkPoints(), vtk.vtkPoints()
            for s, t in zip(source * self.LPS_TO_RAS, target * self.LPS_TO_RAS):
                sourcePoints.InsertNextPoint(*s)
                targetPoints.InsertNextPoint(*t)
            tps = vtk.vtkThinPlateSplineTransform()
            tps.SetBasisToR()  # the 3D thin-plate spline kernel, as used by ITK
            tps.SetSourceLandmarks(sourcePoints)
            tps.SetTargetLandmarks(targetPoints)

            transformNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTransformNode", "ThinPlateSpline")
            transformNode.SetAndObserveTransformFromParent(tps)
            self.assertFalse(transformNode.IsLinear(), "Thin-plate spline transform reported as linear")
            return transformNode, None

        self._checkNonLinearCase("non-linear thin-plate spline", build)
        self.delayDisplay("Passed: non-linear thin-plate spline transform")