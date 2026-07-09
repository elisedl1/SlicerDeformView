cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(DeformView)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/elisedl1/SlicerDeformView")
set(EXTENSION_CONTRIBUTORS "Isabel Frolick (McGill University), Elise Donszelmann-Lund (McGill University)")
set(EXTENSION_DESCRIPTION "Dense, quantitative visualization and analysis of non-linear deformation fields, including per-voxel displacement magnitude and Jacobian determinant maps.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/elisedl1/DeformView/main/DeformView/Resources/Icons/DeformView.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/elisedl1/DeformView/main/exampleImages/main_UI.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(DeformView)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
