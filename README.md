# DeformView

## Overview
**DeformView** provides **intuitive, quantitative visualization of non-linear deformation fields** within the 3D Slicer platform.  
It enables users to interpret deformations using **dense, voxel-wise maps**, given a known transformation and corresponding image data.

DeformView provides two complementary visualization maps:
1. **Displacement Magnitude Map (mm)** – shows local tissue displacement.  
2. **Jacobian Determinant Magnitude (%)** – shows local tissue expansion or compression.

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
   git clone https://github.com/elisedl1/DeformView
   ```

2. **Open 3D Slicer**

3. **Access Extension Wizard**
   - Navigate to: `Module Search` → `Extension Wizard`

4. **Select Extension**
   - Click **"Select Extension"** to add additional module paths
   - Browse and select the folder where you cloned the DeformView repository

5. **Reload Slicer**
   - Restart 3D Slicer to load the new extension

6. **Access DeformView**
   - Use the search bar in the modules dropdown
   - Type "DeformView" to locate and launch the module

---

## Panels and Their Use

### Input Selection
- **Moving Image**  
  Image after the transformation has been applied.
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

If you'd like to contribute, please first refer to the Slicer developer documentation https://www.slicer.org/wiki/Documentation/Nightly/Developers

Please also see the CONTRIBUTING.md file for specific information.

---

## Contributors
- Elise Donszelmann-Lund (@elisedl1)
- Isabel Frolick (@isabelfrolick)

---

To cite this work:

Isabel Frolick, Elise Donszelmann-Lund, raph-rc, Étienne Léger, & TC2423. (2026). elisedl1/DeformView: DeformView (1.0). Zenodo. https://doi.org/10.5281/zenodo.19008734


[![DOI](https://zenodo.org/badge/doi/10.5281/zenodo.19008734.svg)](http://dx.doi.org/10.5281/zenodo.19008734)



