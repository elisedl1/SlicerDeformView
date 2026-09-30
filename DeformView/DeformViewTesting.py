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