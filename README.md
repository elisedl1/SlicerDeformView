# DeformView

## Overview
**DeformView** provides **intuitive, quantitative visualization of non-linear deformation fields** within the 3D Slicer platform.  
It enables users to interpret deformations using **dense, voxel-wise maps**, given a known transformation and corresponding image data.

DeformView provides two complementary visualization maps:
1. **Displacement Magnitude Map (mm)** – shows local tissue displacement.  
2. **Jacobian Determinant Map (%)** – shows local tissue expansion or compression.

A **real-time cursor display** allows users to hover over any voxel and directly view the corresponding **displacement or Jacobian value**.

![](exampleImages/main_UI.png)

---

## Use Cases
DeformView is useful for:
- **Understanding non-linear tissue deformation**
- **Evaluation of image registration algorithms**
- **Research in brain shift modeling**
- **Quantitative interpretation of deformation fields**
- **Comparing preoperative and intraoperative scans**

---

## Installation

### Prerequisites
Download and install **3D Slicer** from the official website: [https://www.slicer.org](https://www.slicer.org)

### Installing DeformView Extension

1. **Clone the repository**
   ```bash
   git clone https://github.com/elisedl1/SlicerDeformView
   ```

2. **Open 3D Slicer**

3. **Open the Extension Wizard**
   - Navigate to: `Module Search` → `Extension Wizard`

4. **Select the extension**
   - Click **"Select Extension"**
   - Choose the **`DeformView` folder inside the cloned repository** (i.e. `SlicerDeformView/DeformView`, the folder containing `DeformView.py`) — not the repository root

5. **Restart 3D Slicer**

6. **Open DeformView**
   - Use the modules dropdown search bar and type "DeformView"

---

## Panels and Their Use

### Input Selection
- **Moving Image**  
   Source before transformation and the transform maps it onto the fixed image.
- **Fixed Image**  
  Reference image.
- **Transformation**  
  Known transformation between the fixed and moving images.

---

### Compute Displacement Field Mapping
- Computes both:
  - **Dense displacement magnitude volume (mm)**
  - **Dense Jacobian determinant volume (%)**
- Automatically:
  - Loads the fixed volume into the scene
  - Applies **100% of the transformation**
  - Overlays the corresponding displacement volume

### Increment Slider
- Controls the **step size** of the applied transformation
- Allows visualization of **0–100% of the transformation**
- Displacement magnitudes at intermediate steps are exact; **Jacobian (volume change) values at intermediate steps are a linear approximation** of the full-transform values and are only exact at 0% and 100%.
![](exampleImages/increment.gif)

---

### Color Map / Loading Function
- Switch between:
  - **Displacement volume**
  - **Jacobian volume**
- Reload required to update the color map
- Includes a selection of **intuitive, perceptually meaningful color maps**
- Color maps are:
  - **Editable for the displacement volume**
  - **Fixed for the Jacobian volume** (cannot be changed)

---

## Notes
- A valid transformation must be provided to compute deformation maps.

---
## Contributing

If you'd like to contribute, please first refer to the Slicer developer documentation https://www.slicer.org/wiki/Documentation/Nightly/Developers

Please also see the CONTRIBUTING.md file for specific information.

---

## Testing

DeformView comes with an automated self-test (`DeformViewTest`, in `DeformView/DeformViewTesting.py`) that checks the module loads and that its computations match analytic ground truth at every voxel. The tests use only synthetic, in-memory data, so no downloads or external data files are needed. Reference volumes use anisotropic voxel spacing so that errors in spacing or orientation handling are caught.

The suite covers:

- **Logic API presence:** the module loads and `DeformViewLogic` exposes its expected methods.
- **Basic displacement + Jacobian:** a 2 mm translation produces valid volumes with matching geometry, finite values, ≈2 mm displacement and ≈0% volume change.
- **Translation (analytic):** for a diagonal translation **t**, displacement magnitude equals ‖**t**‖ and volume change equals 0% at every voxel.
- **Affine scaling, default orientation:** for uniform expansion, uniform compression and a per-axis stretch **A** about centre **c**, displacement magnitude equals ‖(**A**−**I**)(**x**−**c**)‖ at every voxel, and volume change equals (det **A** − 1)×100% at every interior voxel.
- **Increment Transform:** applying 50% of a two-voxel translation reproduces an exact one-voxel shift of the source image.
- **Affine scaling, oblique orientation:** the per-axis stretch and a general affine with shear give exact displacement and volume change on a reference volume tilted relative to the scanner axes, as in oblique clinical acquisitions.
- **Grid transform (analytic):** the general affine field, loaded as a non-linear grid (displacement-field) transform on default and oblique volumes, gives exact displacement and volume change.
- **Non-linear fields (grid, B-spline, thin-plate spline):** curved fields tested at two voxel spacings. Displacement matches the analytic field (grid) or Slicer's independent evaluation of the transform (B-spline, TPS) to about 10⁻¹³ mm. Volume change stays within the theoretical central-difference truncation bound (proportional to spacing²) at every interior voxel, and the error falls by 3.7–4.0× when the spacing is halved, as expected for second-order accuracy.

Linear-field comparisons use tolerances of 10⁻³ mm for displacement, 10⁻² % for volume change and 10⁻³ for image intensity. To pass, non-linear tests require displacement to agree within 10⁻³ mm (grid) or 10⁻⁴ mm (B-spline, TPS), volume change to stay within the truncation bound (plus 10⁻⁴ % for rounding), and the error to fall by 3–5× when the spacing is halved.

**Run it in Slicer:** open the DeformView module and click **Reload and Test**. If the button is hidden, enable developer mode under *Edit → Application Settings → Developer*.

**Run it from the Python console:**

```python
import DeformView
DeformView.DeformViewTest().runTest()
```

### Viewing test results

A successful run logs `Passed:` for each test. Any failure prints an assertion traceback showing the measured error and the tolerance it exceeded. The maximum error for each analytic case is written to the Slicer log.

In practice, outputs match the analytic values to floating-point precision. Our results (3D Slicer 5.8.1, macOS Tahoe 26.6.2):

```
Starting: logic API presence
Passed: logic API presence
Starting: displacement + Jacobian
Passed: displacement + Jacobian
Starting: translation (analytic)
DeformViewTest translation displacement (mm): max abs error = 0.000e+00
DeformViewTest translation volume change (%): max abs error = 0.000e+00
Passed: translation (analytic)
Starting: affine scaling (analytic)
DeformViewTest uniform expansion displacement (mm): max abs error = 1.288e-14
DeformViewTest uniform expansion volume change (%): max abs error = 5.542e-13
DeformViewTest uniform compression displacement (mm): max abs error = 1.243e-14
DeformViewTest uniform compression volume change (%): max abs error = 2.771e-13
DeformViewTest per-axis stretch displacement (mm): max abs error = 4.441e-15
DeformViewTest per-axis stretch volume change (%): max abs error = 1.776e-13
Passed: affine scaling (analytic)
Starting: incremental transform
DeformViewTest incremental 50% shift (intensity): max abs error = 0.000e+00
Passed: incremental transform
Starting: affine scaling on oblique volume
DeformViewTest oblique per-axis stretch displacement (mm): max abs error = 9.326e-15
DeformViewTest oblique per-axis stretch volume change (%): max abs error = 2.665e-13
DeformViewTest oblique general affine displacement (mm): max abs error = 1.155e-14
DeformViewTest oblique general affine volume change (%): max abs error = 7.319e-13
Passed: affine scaling on oblique volume
Starting: grid transform (analytic)
DeformViewTest grid general affine displacement (mm): max abs error = 3.109e-15
DeformViewTest grid general affine volume change (%): max abs error = 4.654e-13
DeformViewTest grid general affine, oblique volume displacement (mm): max abs error = 4.441e-15
DeformViewTest grid general affine, oblique volume volume change (%): max abs error = 3.766e-13
Passed: grid transform (analytic)

Starting: non-linear grid transform
DeformViewTest non-linear grid, spacing (1.0, 1.2, 1.5) displacement (mm): max abs error = 4.219e-15
DeformViewTest non-linear grid, spacing (1.0, 1.2, 1.5) volume change (%): max abs error = 6.494e-01, max h^2 bound = 9.827e-01, worst error/bound = 0.66
DeformViewTest non-linear grid, spacing (1.0, 1.2, 1.5) volume change vs exact central-difference value (%): max abs error = 5.116e-13
DeformViewTest non-linear grid, spacing (0.5, 0.6, 0.75) displacement (mm): max abs error = 5.551e-15
DeformViewTest non-linear grid, spacing (0.5, 0.6, 0.75) volume change (%): max abs error = 1.634e-01, max h^2 bound = 2.456e-01, worst error/bound = 0.66
DeformViewTest non-linear grid, spacing (0.5, 0.6, 0.75) volume change vs exact central-difference value (%): max abs error = 1.442e-12
DeformViewTest non-linear grid: error ratio when spacing is halved = 3.98 (4.0 expected for second-order accuracy)
Passed: non-linear grid transform
Starting: non-linear B-spline transform
DeformViewTest non-linear B-spline, spacing (1.0, 1.2, 1.5) displacement (mm): max abs error = 9.992e-15
DeformViewTest non-linear B-spline, spacing (1.0, 1.2, 1.5) volume change (%): max abs error = 7.146e-02, max h^2 bound = 2.307e-01, worst error/bound = 0.34
DeformViewTest non-linear B-spline, spacing (0.5, 0.6, 0.75) displacement (mm): max abs error = 9.992e-15
DeformViewTest non-linear B-spline, spacing (0.5, 0.6, 0.75) volume change (%): max abs error = 1.780e-02, max h^2 bound = 5.768e-02, worst error/bound = 0.34
DeformViewTest non-linear B-spline: error ratio when spacing is halved = 4.01 (4.0 expected for second-order accuracy)
Passed: non-linear B-spline transform
Starting: non-linear thin-plate spline transform
DeformViewTest non-linear thin-plate spline, spacing (1.0, 1.2, 1.5) displacement (mm): max abs error = 6.084e-14
DeformViewTest non-linear thin-plate spline, spacing (1.0, 1.2, 1.5) volume change (%): max abs error = 4.157e-03, max h^2 bound = 8.718e-03, worst error/bound = 0.48
DeformViewTest non-linear thin-plate spline, spacing (0.5, 0.6, 0.75) displacement (mm): max abs error = 6.106e-14
DeformViewTest non-linear thin-plate spline, spacing (0.5, 0.6, 0.75) volume change (%): max abs error = 1.125e-03, max h^2 bound = 2.380e-03, worst error/bound = 0.46
DeformViewTest non-linear thin-plate spline: error ratio when spacing is halved = 3.70 (4.0 expected for second-order accuracy)
Passed: non-linear thin-plate spline transform

```

---

## Contributors
- Elise Donszelmann-Lund (@elisedl1)
- Isabel Frolick (@isabelfrolick)
- Taj Choksi (@TC2423)
- Étienne Léger (@errollgarner)
- Raphaël Christin (@raph-rc)

---

To cite this work:

Frolick, I., Donszelmann-Lund, E., Choksi, T., Léger, É., Christin, R., Siddiqi, K., & Collins, D. L. (2026). *DeformView: Quantitative Visualization of Non-Linear Deformation Fields* (Version 1.1) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.21287630

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19008733-blue.svg)](https://doi.org/10.5281/zenodo.19008733)
---
## License

DeformView is distributed under the MIT License. See [LICENSE.txt](LICENSE.txt) for details.

