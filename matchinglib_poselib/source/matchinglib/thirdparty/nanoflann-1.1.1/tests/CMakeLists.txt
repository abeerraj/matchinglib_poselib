# ----------------------------------------------------------------------------
#   TESTS
# ----------------------------------------------------------------------------
PROJECT(tests)

SET(EXECUTABLE_OUTPUT_PATH "${${PROJECT_NAME}_BINARY_DIR}")

# -----------------------------
# Add the "make test" target:
# -----------------------------
ADD_CUSTOM_TARGET(test)

# Tests based on Google gtest:
# -----------------------------

# If using system library, add C++ flags:
IF (UNIX)
	SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -pthread")
ENDIF (UNIX)

# Test project:
ADD_EXECUTABLE(unit_tests test_main.cpp)

# Add the required libraries for linking:
TARGET_LINK_LIBRARIES(unit_tests gtest)

# Run it:
GET_TARGET_PROPERTY(GENERATED_EXE unit_tests LOCATION)
ADD_CUSTOM_TARGET(run_tests COMMAND "${GENERATED_EXE}" "${${PROJECT_NAME}__SOURCE_DIR}")
ADD_DEPENDENCIES(run_tests unit_tests)
ADD_DEPENDENCIES(test run_tests)


